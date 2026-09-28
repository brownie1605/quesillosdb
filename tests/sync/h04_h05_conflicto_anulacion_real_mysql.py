"""Reproduce el bug historico de H-04/H-05 contra MySQL real.

`_upsert_local` usa `INSERT ... ON DUPLICATE KEY UPDATE` (sintaxis de
MySQL), asi que esta prueba no puede correr contra el SQLite en memoria de
la suite de pytest -- necesita la BD real.

Escenario historico que reproduce (visto en vivo en esta misma sesion,
antes del fix):
  1. Se crea una venta (timestamp_local_actualizacion = T1).
  2. Se anula localmente (timestamp_local_actualizacion = T2 > T1, estado='anulada').
  3. El push de esa anulacion "no llega a tiempo" (simulado: no se hace).
  4. Llega un pull con la version vieja de la nube: estado='completada',
     con un timestamp ANTERIOR a T2 (la version de antes de anular).
  5. Antes del fix: `_upsert_local` sobreescribia sin comparar -> la venta
     "revivia" como completada.
     Despues del fix: debe quedarse anulada.

Tambien prueba el caso inverso (un cambio remoto de verdad mas nuevo si
debe aplicarse) para confirmar que no se rompio la sincronizacion normal.
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv()
os.environ["DB_LOCAL_HOST"] = os.environ.get("DB_REMOTE_HOST", os.environ.get("DB_LOCAL_HOST", ""))
os.environ["DB_LOCAL_PORT"] = os.environ.get("DB_REMOTE_PORT", os.environ.get("DB_LOCAL_PORT", ""))
os.environ["DB_LOCAL_USER"] = os.environ.get("DB_REMOTE_USER", os.environ.get("DB_LOCAL_USER", ""))
os.environ["DB_LOCAL_PASSWORD"] = os.environ.get("DB_REMOTE_PASSWORD", os.environ.get("DB_LOCAL_PASSWORD", ""))
os.environ["DB_LOCAL_NAME"] = os.environ.get("DB_REMOTE_NAME", os.environ.get("DB_LOCAL_NAME", ""))
os.environ["SCHEDULER_ENABLED"] = "false"

from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()


def _crear_venta_de_prueba():
    with app.app_context():
        usuario_id = db.session.execute(text("SELECT id_usuario FROM usuarios LIMIT 1")).scalar()
        res = db.session.execute(text(
            """INSERT INTO ventas
               (id_empresa, id_sucursal, id_usuario, numero_venta, uuid_venta,
                subtotal, total, estado, fecha_venta,
                timestamp_local_creacion, timestamp_local_actualizacion, estado_sync)
               VALUES (1, 1, :uid, :num, :uuid, 100, 100, 'completada', NOW(), NOW(), NOW(), 'pendiente')"""
        ), {"uid": usuario_id, "num": "TEST-H04H05", "uuid": "test-h04h05-uuid"})
        id_venta = res.lastrowid
        db.session.commit()
        return id_venta


def _limpiar(id_venta):
    with app.app_context():
        db.session.execute(text("DELETE FROM sync_queue WHERE tabla_afectada='ventas' AND registro_id=:id"), {"id": id_venta})
        db.session.execute(text("DELETE FROM ventas WHERE id_venta=:id"), {"id": id_venta})
        db.session.commit()


def caso_no_revive_anulacion():
    print("=== CASO 1: pull con dato viejo NO debe revivir una venta anulada ===")
    id_venta = _crear_venta_de_prueba()
    try:
        with app.app_context():
            from app.services.venta_service import VentaService
            from app.models.usuario import Usuario
            from app.services.sync_service import SyncService

            usuario = Usuario.query.first()
            VentaService.anular_venta(id_venta, usuario, "prueba H-04/H-05")

            fila = db.session.execute(
                text("SELECT estado, timestamp_local_actualizacion FROM ventas WHERE id_venta=:id"),
                {"id": id_venta},
            ).fetchone()
            assert fila.estado == "anulada", "La venta deberia quedar anulada tras anular_venta()"
            ts_anulacion = fila.timestamp_local_actualizacion
            print("Estado tras anular:", fila.estado, "| timestamp:", ts_anulacion)

            # Payload "viejo" que traeria un pull si el push de la
            # anulacion no hubiera llegado a tiempo: todavia 'completada',
            # con un timestamp ANTERIOR al de la anulacion.
            payload_viejo = {
                "id_venta": id_venta,
                "estado": "completada",
                "timestamp_local_actualizacion": (ts_anulacion - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
            }
            aplicado = SyncService._upsert_local("ventas", payload_viejo)
            db.session.commit()
            print("_upsert_local con dato viejo -> aplicado =", aplicado)

            fila2 = db.session.execute(
                text("SELECT estado FROM ventas WHERE id_venta=:id"), {"id": id_venta}
            ).fetchone()
            print("Estado final:", fila2.estado)

            assert aplicado is False, "No debia aplicarse un pull mas viejo que el local"
            assert fila2.estado == "anulada", "La venta NO debia revivir como 'completada'"
            print("PASS: la venta se quedo anulada, el pull viejo fue descartado.\n")
    finally:
        _limpiar(id_venta)


def caso_si_aplica_cambio_mas_nuevo():
    print("=== CASO 2: pull con dato de verdad mas nuevo SI debe aplicarse ===")
    id_venta = _crear_venta_de_prueba()
    try:
        with app.app_context():
            from app.services.sync_service import SyncService

            # Un pull real trae la fila COMPLETA (SELECT *) -- un payload
            # parcial fallaria al intentar el INSERT (columnas NOT NULL sin
            # valor) aun cuando en la practica termine siendo un UPDATE por
            # 'ON DUPLICATE KEY'. Se arma igual que _row_to_dict() lo haria.
            from datetime import datetime as _dt
            from decimal import Decimal as _Decimal

            fila = db.session.execute(
                text("SELECT * FROM ventas WHERE id_venta=:id"), {"id": id_venta}
            ).mappings().first()
            ts_original = fila["timestamp_local_actualizacion"]

            def _serializable(v):
                if isinstance(v, _Decimal):
                    return float(v)
                if isinstance(v, _dt):
                    return v.strftime("%Y-%m-%d %H:%M:%S")
                return v

            payload_nuevo = {k: _serializable(v) for k, v in dict(fila).items() if v is not None}
            payload_nuevo["estado"] = "anulada"
            payload_nuevo["timestamp_local_actualizacion"] = (ts_original + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
            aplicado = SyncService._upsert_local("ventas", payload_nuevo)
            db.session.commit()
            print("_upsert_local con dato mas nuevo -> aplicado =", aplicado)

            fila2 = db.session.execute(
                text("SELECT estado FROM ventas WHERE id_venta=:id"), {"id": id_venta}
            ).fetchone()
            print("Estado final:", fila2.estado)

            assert aplicado is True, "Un cambio remoto de verdad mas nuevo si debia aplicarse"
            assert fila2.estado == "anulada"
            print("PASS: el cambio remoto mas nuevo se aplico correctamente.\n")
    finally:
        _limpiar(id_venta)


if __name__ == "__main__":
    caso_no_revive_anulacion()
    caso_si_aplica_cambio_mas_nuevo()
    print("TODOS LOS CASOS DE H-04/H-05 PASARON.")
