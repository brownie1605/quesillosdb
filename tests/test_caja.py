"""Apertura/cierre de turno de caja, y que una venta exija turno abierto.

`datos_base` ya deja un turno abierto (ver conftest.py) porque casi todas las
pruebas de venta del resto de la suite solo necesitan poder cobrar, no estan
probando esta regla en si. Las pruebas de este archivo que necesitan partir
de "sin turno abierto" cierran ese turno primero.
"""
import pytest

from app.services.caja_service import CajaService, CajaError
from app.services.venta_service import VentaService, VentaError


def test_datos_base_ya_deja_un_turno_abierto(app, db, datos_base):
    assert CajaService.apertura_actual() is not None
    assert CajaService.apertura_actual().id_apertura == datos_base["apertura_caja"].id_apertura


def test_no_se_puede_abrir_dos_turnos_a_la_vez(app, db, datos_base):
    with pytest.raises(CajaError):
        CajaService.abrir_turno(datos_base["admin"], 200)


def test_abrir_turno_crea_apertura_tras_cerrar_el_anterior(app, db, datos_base):
    CajaService.cerrar_turno(datos_base["admin"], 0)
    apertura = CajaService.abrir_turno(datos_base["admin"], 500)
    assert apertura.estado == "abierta"
    assert apertura.monto_inicial == 500
    assert CajaService.apertura_actual().id_apertura == apertura.id_apertura


def test_resumen_y_cierre_de_turno(app, db, datos_base):
    CajaService.cerrar_turno(datos_base["admin"], 0)
    CajaService.abrir_turno(datos_base["admin"], 500)

    apertura = CajaService.apertura_actual()
    resumen = CajaService.resumen_turno(apertura)
    # Sin movimientos manuales (se quitaron del sistema) ni ventas todavia.
    assert resumen["monto_esperado"] == 500

    cierre = CajaService.cerrar_turno(datos_base["admin"], 490, "Faltaron C$10")
    assert cierre.diferencia == -10
    assert CajaService.apertura_actual() is None


def test_venta_sin_turno_abierto_es_rechazada(app, db, datos_base, quesillo):
    CajaService.cerrar_turno(datos_base["admin"], 0)
    with pytest.raises(VentaError):
        VentaService.registrar_venta(
            datos_base["cajero"],
            [{"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": float(quesillo["final"].precio_venta)}],
        )


def test_venta_funciona_de_nuevo_al_reabrir_turno(app, db, datos_base, quesillo):
    CajaService.cerrar_turno(datos_base["admin"], 0)
    CajaService.abrir_turno(datos_base["cajero"], 0)
    venta = VentaService.registrar_venta(
        datos_base["cajero"],
        [{"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": float(quesillo["final"].precio_venta)}],
    )
    assert venta.id_venta is not None
