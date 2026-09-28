"""Prueba de concurrencia REAL para H-02 (race condition de inventario).

Corre contra la BD MySQL real (no SQLite, que serializa todo y nunca
reproduciria la carrera). Crea un producto/insumo desechable, lo deja con
stock=1, y lanza dos hilos que intentan descontar 1 unidad al mismo tiempo
via InventarioService.mover(). Luego un segundo caso con stock=10 y 11
hilos concurrentes.

Limpia todo lo que crea al final, incluso si falla a medio camino.
"""
import os
import sys
import threading
import time

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


def _usuario_de_prueba():
    with app.app_context():
        r = db.session.execute(text("SELECT id_usuario FROM usuarios LIMIT 1")).scalar()
        if not r:
            raise RuntimeError("No hay ningun usuario en la BD para usar en la prueba")
        return r


USUARIO_DE_PRUEBA = _usuario_de_prueba()


def _vender_una_unidad(id_producto, resultados, idx):
    """Cada hilo corre en su PROPIO app_context / sesion / conexion, para
    que MySQL las vea como transacciones realmente concurrentes."""
    with app.app_context():
        from app.services.inventario_service import InventarioService, StockInsuficiente
        try:
            InventarioService.mover(
                id_producto, -1, "venta", usuario_id=USUARIO_DE_PRUEBA,
                referencia=f"TEST-CONCURRENCIA-{idx}", commit=True,
            )
            with resultados_lock:
                resultados[idx] = "SUCCESS"
        except StockInsuficiente:
            db.session.rollback()
            with resultados_lock:
                resultados[idx] = "FAIL"
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            with resultados_lock:
                resultados[idx] = f"ERROR: {e}"


def _crear_producto_prueba(stock_inicial):
    with app.app_context():
        res = db.session.execute(text(
            """INSERT INTO productos
               (id_empresa, id_categoria, id_unidad, codigo, nombre, tipo_producto,
                precio_compra, precio_venta, se_vende, estado)
               VALUES (1, NULL, 1, :cod, :nom, 'insumo', 0, 0, 0, 'activo')"""
        ), {"cod": f"TEST-CONC-{stock_inicial}-{int(time.time())}", "nom": f"TEST concurrencia stock={stock_inicial}"})
        id_producto = res.lastrowid
        db.session.execute(text(
            "INSERT INTO inventario (id_producto, id_sucursal, stock_actual, stock_minimo) VALUES (:id, 1, :stock, 0)"
        ), {"id": id_producto, "stock": stock_inicial})
        db.session.commit()
        return id_producto


def _limpiar(id_producto):
    with app.app_context():
        db.session.execute(text("DELETE FROM movimientos_inventario WHERE id_producto=:id"), {"id": id_producto})
        db.session.execute(text("DELETE FROM inventario WHERE id_producto=:id"), {"id": id_producto})
        db.session.execute(text("DELETE FROM sync_queue WHERE tabla_afectada IN ('productos','inventario','movimientos_inventario') AND registro_id=:id"), {"id": id_producto})
        db.session.execute(text("DELETE FROM productos WHERE id_producto=:id"), {"id": id_producto})
        db.session.commit()


def _stock_actual(id_producto):
    with app.app_context():
        return db.session.execute(text("SELECT stock_actual FROM inventario WHERE id_producto=:id"), {"id": id_producto}).scalar()


def caso_1_ultimo_producto():
    print("\n=== CASO 1: stock=1, 2 hilos venden 1 unidad cada uno ===")
    id_producto = _crear_producto_prueba(1)
    try:
        resultados = {}
        hilos = [threading.Thread(target=_vender_una_unidad, args=(id_producto, resultados, i)) for i in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        stock_final = _stock_actual(id_producto)
        exitos = sum(1 for v in resultados.values() if v == "SUCCESS")
        fallos = sum(1 for v in resultados.values() if v == "FAIL")
        errores = [v for v in resultados.values() if v.startswith("ERROR")]

        print("Resultados:", resultados)
        print("Stock final:", stock_final)

        assert errores == [], f"Errores inesperados: {errores}"
        assert exitos == 1, f"Se esperaba exactamente 1 exito, hubo {exitos}"
        assert fallos == 1, f"Se esperaba exactamente 1 fallo, hubo {fallos}"
        assert stock_final == 0, f"Stock final deberia ser 0, fue {stock_final}"
        print("PASS: exactamente 1 exito, 1 fallo, stock final = 0 (nunca negativo).")
    finally:
        _limpiar(id_producto)


def caso_2_diez_contra_once():
    print("\n=== CASO 2: stock=10, 11 hilos concurrentes venden 1 unidad cada uno ===")
    id_producto = _crear_producto_prueba(10)
    try:
        resultados = {}
        hilos = [threading.Thread(target=_vender_una_unidad, args=(id_producto, resultados, i)) for i in range(11)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        stock_final = _stock_actual(id_producto)
        exitos = sum(1 for v in resultados.values() if v == "SUCCESS")
        fallos = sum(1 for v in resultados.values() if v == "FAIL")
        errores = [v for v in resultados.values() if v.startswith("ERROR")]

        print("Exitos:", exitos, "| Fallos:", fallos, "| Stock final:", stock_final)

        assert errores == [], f"Errores inesperados: {errores}"
        assert exitos == 10, f"Se esperaban 10 exitos, hubo {exitos}"
        assert fallos == 1, f"Se esperaba 1 fallo (la 11a), hubo {fallos}"
        assert stock_final == 0, f"Stock final deberia ser 0, fue {stock_final}"
        print("PASS: 10 exitosas, 1 fallo, stock final = 0.")
    finally:
        _limpiar(id_producto)


if __name__ == "__main__":
    caso_1_ultimo_producto()
    caso_2_diez_contra_once()
    print("\nTODOS LOS CASOS DE CONCURRENCIA (H-02) PASARON.")
