"""Prueba de concurrencia REAL para H-03 (dos aperturas de turno a la vez).

Corre contra MySQL real. Si hay un turno abierto de antes (de uso normal
del sistema), lo cierra temporalmente para la prueba y lo vuelve a dejar
como estaba -- no debe alterar el estado real del negocio.
"""
import os
import sys
import threading

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
resultados_lock = threading.Lock()


class UsuarioFalso:
    """Solo necesitamos un objeto con .id_usuario para CajaService.abrir_turno."""
    def __init__(self, id_usuario):
        self.id_usuario = id_usuario


def _abrir_turno(usuario_id, resultados, idx):
    with app.app_context():
        from app.services.caja_service import CajaService, CajaError
        try:
            CajaService.abrir_turno(UsuarioFalso(usuario_id), 500)
            with resultados_lock:
                resultados[idx] = "SUCCESS"
        except CajaError:
            db.session.rollback()
            with resultados_lock:
                resultados[idx] = "FAIL"
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            with resultados_lock:
                resultados[idx] = f"ERROR: {e}"


def main():
    with app.app_context():
        usuario_id = db.session.execute(text("SELECT id_usuario FROM usuarios LIMIT 1")).scalar()
        # Guarda cualquier turno abierto real para restaurarlo despues.
        abierto_antes = db.session.execute(
            text("SELECT id_apertura FROM aperturas_caja WHERE estado='abierta'")
        ).scalar()
        if abierto_antes:
            db.session.execute(
                text("UPDATE aperturas_caja SET estado='cerrada' WHERE id_apertura=:id"),
                {"id": abierto_antes},
            )
            db.session.commit()

    print("=== Dos hilos intentando abrir turno al mismo tiempo ===")
    resultados = {}
    hilos = [threading.Thread(target=_abrir_turno, args=(usuario_id, resultados, i)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    print("Resultados:", resultados)

    with app.app_context():
        abiertos = db.session.execute(
            text("SELECT COUNT(*) FROM aperturas_caja WHERE estado='abierta'")
        ).scalar()
        print("Turnos abiertos al final (antes de limpiar):", abiertos)

        # limpieza: cerrar cualquier turno que la prueba haya abierto, y
        # restaurar el que habia antes (si habia).
        db.session.execute(text("UPDATE aperturas_caja SET estado='cerrada' WHERE estado='abierta'"))
        if abierto_antes:
            db.session.execute(
                text("UPDATE aperturas_caja SET estado='abierta' WHERE id_apertura=:id"),
                {"id": abierto_antes},
            )
        db.session.commit()

    errores = [v for v in resultados.values() if v.startswith("ERROR")]
    exitos = sum(1 for v in resultados.values() if v == "SUCCESS")
    fallos = sum(1 for v in resultados.values() if v == "FAIL")

    assert errores == [], f"Errores inesperados: {errores}"
    assert exitos == 1, f"Se esperaba exactamente 1 turno abierto con exito, hubo {exitos}"
    assert fallos == 1, f"Se esperaba exactamente 1 rechazo, hubo {fallos}"
    assert abiertos == 1, f"Debia quedar exactamente 1 turno abierto en la BD, habia {abiertos}"
    print("PASS: exactamente 1 apertura exitosa, 1 rechazada, 1 turno abierto en la BD.")


if __name__ == "__main__":
    main()
