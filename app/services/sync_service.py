"""Sincronizacion bidireccional MySQL local <-> MySQL nube (Railway).

Estrategia:
  * La aplicacion escribe SIEMPRE en la BD local (funciona sin internet).
  * Cada operacion relevante se encola en `sync_queue`.
  * PUSH: sube las operaciones pendientes a la nube.
  * PULL: baja los cambios remotos posteriores a la marca de agua por tabla.
  * Los conflictos se delegan a ConflictService.
"""
import json
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.extensions import db
from app.models.sync import SyncQueue, ConflictLog, SyncMetadata
from app.services.network_service import NetworkService
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("sync.service")

# Cache de columnas remotas por tabla (se llena en el primer push).
_COLUMNAS_REMOTAS = {}

# Que tablas locales tienen columna estado_sync.
_CON_ESTADO_SYNC = {}

# Orden de sincronizacion: respeta dependencias de claves foraneas.
TABLAS_SYNC = [
    "roles",
    "usuarios",
    "categorias",
    "marcas",
    "unidades_medida",
    "proveedores",
    "clientes",
    "productos",
    "recetas",
    "receta_ingredientes",
    "receta_opciones_grupo",
    "receta_opciones_item",
    "inventario",
    "ventas",
    "detalle_ventas",
    "movimientos_inventario",
    "compras",
    "detalle_compras",
    "notificaciones",
]

# Clave primaria de cada tabla sincronizable.
PK_POR_TABLA = {
    "roles": "id_rol",
    "usuarios": "id_usuario",
    "categorias": "id_categoria",
    "marcas": "id_marca",
    "unidades_medida": "id_unidad",
    "proveedores": "id_proveedor",
    "clientes": "id_cliente",
    "productos": "id_producto",
    "recetas": "id_receta",
    "receta_ingredientes": "id_ingrediente",
    "receta_opciones_grupo": "id_grupo",
    "receta_opciones_item": "id_item",
    "inventario": "id_inventario",
    "ventas": "id_venta",
    "detalle_ventas": "id_detalle_venta",
    "movimientos_inventario": "id_movimiento",
    "compras": "id_compra",
    "detalle_compras": "id_detalle_compra",
    "notificaciones": "id_notificacion",
}

# Columna de marca temporal usada por el PULL.
TIMESTAMP_POR_TABLA = {
    "usuarios": "fecha_creacion",
    "productos": "fecha_actualizacion",
    "recetas": "fecha_actualizacion",
    "inventario": "fecha_actualizacion",
    "ventas": "fecha_venta",
    "movimientos_inventario": "fecha_movimiento",
    "compras": "fecha_compra",
    "notificaciones": "fecha_creacion",
}


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (bytes, bytearray)):
        return None  # las imagenes binarias no viajan en el payload
    return value


def _row_to_dict(row_mapping):
    return {k: _json_safe(v) for k, v in dict(row_mapping).items()}


def checksum(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class SyncService:
    """Motor de sincronizacion. Todos los metodos requieren app context."""

    _running = threading.Lock()

    # =================================================================
    # ENCOLADO
    # =================================================================
    @staticmethod
    def encolar(tabla, registro_id, operacion="INSERT", payload=None,
                usuario_id=None, timestamp=None, commit=True):
        """Registra una operacion local pendiente de subir a la nube."""
        from flask import current_app

        payload = payload or {}
        item = SyncQueue(
            operation_type=operacion,
            tabla_afectada=tabla,
            registro_id=registro_id,
            id_empresa=current_app.config.get("ID_EMPRESA", 1),
            timestamp_operacion=timestamp or nicaragua_now(),
            estado_sync="pendiente",
            payload=payload,
            usuario_origen=usuario_id,
            dispositivo_origen=current_app.config.get("DEVICE_ID", "local-01"),
            checksum_datos=checksum(payload) if payload else None,
        )
        db.session.add(item)
        if commit:
            db.session.commit()
        return item

    # =================================================================
    # PUSH  (local -> nube)
    # =================================================================
    @classmethod
    def push_pending_operations(cls, limite=None):
        from flask import current_app
        from app.services.conflict_service import ConflictService

        resultado = {"enviados": 0, "conflictos": 0, "errores": 0, "detalle": []}
        if not NetworkService.is_online():
            resultado["mensaje"] = "Sin conexion: push omitido"
            return resultado

        limite = limite or current_app.config.get("SYNC_BATCH_SIZE", 200)
        engine = db.engines.get("cloud")

        pendientes = (
            SyncQueue.query.filter(SyncQueue.estado_sync.in_(["pendiente", "error"]))
            .order_by(SyncQueue.timestamp_operacion.asc(), SyncQueue.id_sync_queue.asc())
            .limit(limite)
            .all()
        )

        # Ordena por prioridad de tabla para no romper llaves foraneas.
        orden = {t: i for i, t in enumerate(TABLAS_SYNC)}
        pendientes.sort(key=lambda x: (orden.get(x.tabla_afectada, 99), x.timestamp_operacion))

        for op in pendientes:
            try:
                with engine.begin() as conn:
                    if op.tabla_afectada == "ventas" and op.operation_type == "INSERT":
                        conflicto = ConflictService.verificar_venta_remota(conn, op)
                        if conflicto:
                            op.estado_sync = "en_conflicto"
                            resultado["conflictos"] += 1
                            db.session.commit()
                            continue
                    cls._aplicar_en_remoto(conn, op)

                op.estado_sync = "sinc_remoto"
                op.timestamp_sincronizacion = nicaragua_now()
                op.ultimo_error = None
                resultado["enviados"] += 1
                cls._marcar_registro_sincronizado(op)
                db.session.commit()
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                op.intentos = (op.intentos or 0) + 1
                op.ultimo_error = str(exc)[:1000]
                op.estado_sync = "error" if op.intentos < 5 else "en_conflicto"
                db.session.commit()
                resultado["errores"] += 1
                resultado["detalle"].append(
                    {"id": op.id_sync_queue, "tabla": op.tabla_afectada, "error": str(exc)[:200]}
                )
                log.warning("Push fallo (%s#%s): %s", op.tabla_afectada, op.registro_id, exc)

        cls._actualizar_metadata("push", resultado["enviados"])
        return resultado

    # -----------------------------------------------------------------
    @staticmethod
    def _columnas_remotas(conn, tabla):
        """{columna: admite_null} de la tabla remota (cache por proceso)."""
        if tabla not in _COLUMNAS_REMOTAS:
            filas = conn.execute(
                text(
                    "SELECT COLUMN_NAME, IS_NULLABLE FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                ),
                {"t": tabla},
            ).mappings().all()
            _COLUMNAS_REMOTAS[tabla] = {
                f["COLUMN_NAME"]: f["IS_NULLABLE"] == "YES" for f in filas
            }
        return _COLUMNAS_REMOTAS[tabla]

    # -----------------------------------------------------------------
    @staticmethod
    def _fila_local_actual(tabla, registro_id):
        """Estado actual completo de la fila en la base local.

        El payload encolado puede ser parcial (p. ej. un UPDATE que solo toca
        un campo). Si esa fila todavia no existe en la nube, un INSERT parcial
        falla por columnas NOT NULL. Por eso se sube siempre la fila completa.
        """
        pk = PK_POR_TABLA.get(tabla)
        if not pk:
            return None
        try:
            fila = db.session.execute(
                text("SELECT * FROM " + tabla + " WHERE " + pk + " = :pk"),
                {"pk": registro_id},
            ).mappings().first()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return None
        if not fila:
            return None
        # Las imagenes no viajan en la sincronizacion: pesan cientos de KB y
        # la conexion del local es intermitente.
        return {
            k: _json_safe(v) for k, v in dict(fila).items()
            if not isinstance(v, (bytes, bytearray))
        }

    # -----------------------------------------------------------------
    @classmethod
    def _aplicar_en_remoto(cls, conn, op):
        """Ejecuta la operacion de `op` sobre la conexion remota."""
        tabla = op.tabla_afectada
        pk = PK_POR_TABLA.get(tabla, "id")

        if op.operation_type == "DELETE":
            conn.execute(text("DELETE FROM " + tabla + " WHERE " + pk + " = :pk"),
                         {"pk": op.registro_id})
            return

        payload = cls._fila_local_actual(tabla, op.registro_id) or dict(op.payload or {})
        payload.setdefault(pk, op.registro_id)

        # Solo columnas que la nube realmente tiene.
        columnas_remotas = cls._columnas_remotas(conn, tabla)
        if columnas_remotas:
            payload = {k: v for k, v in payload.items() if k in columnas_remotas}

        # Un NULL se envia tal cual si la columna remota lo admite (asi se
        # propaga el borrado de un campo). Si es NOT NULL se omite para que
        # actue el valor por defecto de la nube en vez de fallar.
        payload = {
            k: v for k, v in payload.items()
            if v is not None or k == pk or columnas_remotas.get(k, True)
        }

        columnas = ", ".join("`" + c + "`" for c in payload)
        binds = ", ".join(":" + c for c in payload)
        updates = ", ".join("`" + c + "` = VALUES(`" + c + "`)" for c in payload if c != pk)

        sql = "INSERT INTO " + tabla + " (" + columnas + ") VALUES (" + binds + ")"
        if updates:
            sql += " ON DUPLICATE KEY UPDATE " + updates
        conn.execute(text(sql), payload)

    # -----------------------------------------------------------------
    @staticmethod
    def _tiene_estado_sync(tabla):
        """Si la tabla local tiene columna estado_sync (con cache)."""
        if tabla not in _CON_ESTADO_SYNC:
            _CON_ESTADO_SYNC[tabla] = bool(
                db.session.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
                        "AND COLUMN_NAME = 'estado_sync'"
                    ),
                    {"t": tabla},
                ).scalar()
            )
        return _CON_ESTADO_SYNC[tabla]

    # -----------------------------------------------------------------
    @classmethod
    def _marcar_registro_sincronizado(cls, op):
        """Marca estado_sync='sinc_remoto' en la fila local original.

        No todas las tablas tienen esa columna (receta_ingredientes, por
        ejemplo). Antes se intentaba igual y el rollback del error deshacia
        tambien el cambio de estado de la propia cola, dejando la operacion
        como pendiente aunque ya se hubiera subido.
        """
        tabla = op.tabla_afectada
        pk = PK_POR_TABLA.get(tabla)
        if not pk or not cls._tiene_estado_sync(tabla):
            return
        db.session.execute(
            text("UPDATE " + tabla + " SET estado_sync = 'sinc_remoto' WHERE " + pk + " = :pk"),
            {"pk": op.registro_id},
        )

    # =================================================================
    # PULL  (nube -> local)
    # =================================================================
    @classmethod
    def pull_remote_changes(cls, tablas=None):
        resultado = {"aplicados": 0, "por_tabla": {}, "errores": []}
        if not NetworkService.is_online():
            resultado["mensaje"] = "Sin conexion: pull omitido"
            return resultado

        engine = db.engines.get("cloud")
        tablas = tablas or TABLAS_SYNC

        for tabla in tablas:
            col_ts = TIMESTAMP_POR_TABLA.get(tabla)
            if not col_ts:
                continue
            meta = cls._get_metadata(tabla)
            desde = meta.ultimo_pull or (nicaragua_now() - timedelta(days=30))
            try:
                with engine.connect() as conn:
                    sql = ("SELECT * FROM " + tabla + " WHERE " + col_ts +
                           " > :desde ORDER BY " + col_ts + " ASC LIMIT 500")
                    filas = conn.execute(text(sql), {"desde": desde}).mappings().all()

                aplicados = 0
                for fila in filas:
                    datos = _row_to_dict(fila)
                    if cls._upsert_local(tabla, datos):
                        aplicados += 1

                db.session.commit()
                meta = cls._get_metadata(tabla)
                meta.ultimo_pull = nicaragua_now()
                meta.ultima_sincronizacion = meta.ultimo_pull
                meta.registros_sincronizados = (meta.registros_sincronizados or 0) + aplicados
                meta.estado = "sincronizado"
                meta.mensaje = None
                db.session.commit()

                resultado["aplicados"] += aplicados
                resultado["por_tabla"][tabla] = aplicados
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                meta = cls._get_metadata(tabla)
                meta.estado = "error"
                meta.mensaje = str(exc)[:500]
                db.session.commit()
                resultado["errores"].append({"tabla": tabla, "error": str(exc)[:200]})
                log.warning("Pull fallo en %s: %s", tabla, exc)

        return resultado

    # -----------------------------------------------------------------
    @staticmethod
    def _upsert_local(tabla, datos):
        """Inserta/actualiza una fila remota en la BD local sin re-encolarla."""
        pk = PK_POR_TABLA.get(tabla, "id")
        datos = {k: v for k, v in datos.items() if v is not None}
        if pk not in datos:
            return False
        datos["estado_sync"] = "sinc_remoto"

        def _construir(d):
            columnas = ", ".join("`" + c + "`" for c in d)
            binds = ", ".join(":" + c for c in d)
            updates = ", ".join("`" + c + "` = VALUES(`" + c + "`)" for c in d if c != pk)
            sql = "INSERT INTO " + tabla + " (" + columnas + ") VALUES (" + binds + ")"
            if updates:
                sql += " ON DUPLICATE KEY UPDATE " + updates
            return sql

        try:
            db.session.execute(text(_construir(datos)), datos)
            return True
        except Exception:
            db.session.rollback()
            datos.pop("estado_sync", None)
            db.session.execute(text(_construir(datos)), datos)
            return True

    # =================================================================
    # CICLO COMPLETO
    # =================================================================
    @classmethod
    def sync_full(cls, disparador="manual"):
        """Ejecuta PULL + PUSH + resolucion de conflictos."""
        from app.services.conflict_service import ConflictService

        if not cls._running.acquire(blocking=False):
            return {"ok": False, "mensaje": "Ya hay una sincronizacion en curso"}
        try:
            NetworkService.check_connectivity()
            if not NetworkService.is_online():
                return {
                    "ok": False,
                    "online": False,
                    "mensaje": "Sin conexion con la nube. Los datos quedan en cola local.",
                    "pendientes": cls.contar_pendientes(),
                }

            inicio = nicaragua_now()
            pull = cls.pull_remote_changes()
            push = cls.push_pending_operations()
            conflictos = ConflictService.resolver_pendientes()

            return {
                "ok": True,
                "online": True,
                "disparador": disparador,
                "inicio": inicio.isoformat(),
                "fin": nicaragua_now().isoformat(),
                "pull": pull,
                "push": push,
                "conflictos": conflictos,
                "pendientes": cls.contar_pendientes(),
            }
        finally:
            cls._running.release()

    # =================================================================
    # UTILIDADES
    # =================================================================
    @staticmethod
    def contar_pendientes():
        return SyncQueue.query.filter(
            SyncQueue.estado_sync.in_(["pendiente", "error"])
        ).count()

    @staticmethod
    def _get_metadata(tabla):
        meta = SyncMetadata.query.filter_by(tabla_nombre=tabla).first()
        if not meta:
            meta = SyncMetadata(tabla_nombre=tabla, estado="pendiente")
            db.session.add(meta)
            db.session.commit()
        return meta

    @classmethod
    def _actualizar_metadata(cls, tipo, cantidad):
        meta = cls._get_metadata("__global__")
        ahora = nicaragua_now()
        meta.ultima_sincronizacion = ahora
        if tipo == "push":
            meta.ultimo_push = ahora
        else:
            meta.ultimo_pull = ahora
        meta.registros_sincronizados = (meta.registros_sincronizados or 0) + cantidad
        meta.estado = "sincronizado"
        db.session.commit()

    @classmethod
    def estado_general(cls):
        pendientes = cls.contar_pendientes()
        conflictos = ConflictLog.query.filter_by(
            estado_resolucion="pendiente_resolucion"
        ).count()
        meta = SyncMetadata.query.filter_by(tabla_nombre="__global__").first()
        return {
            "online": NetworkService.is_online(),
            "pendientes": pendientes,
            "conflictos_pendientes": conflictos,
            "ultima_sincronizacion": meta.ultima_sincronizacion.isoformat()
            if meta and meta.ultima_sincronizacion
            else None,
            "red": NetworkService.status(),
        }
