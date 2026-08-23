"""Apertura/cierre de turno de caja y movimientos de efectivo."""
import pytest

from app.services.caja_service import CajaService, CajaError


def test_abrir_turno_crea_apertura(app, db, datos_base):
    apertura = CajaService.abrir_turno(datos_base["admin"], 500)
    assert apertura.estado == "abierta"
    assert apertura.monto_inicial == 500
    assert CajaService.apertura_actual().id_apertura == apertura.id_apertura


def test_no_se_puede_abrir_dos_turnos_a_la_vez(app, db, datos_base):
    CajaService.abrir_turno(datos_base["admin"], 500)
    with pytest.raises(CajaError):
        CajaService.abrir_turno(datos_base["admin"], 200)


def test_movimiento_requiere_turno_abierto(app, db, datos_base):
    with pytest.raises(CajaError):
        CajaService.registrar_movimiento(datos_base["admin"], "egreso", 50, "Sin turno")


def test_resumen_y_cierre_de_turno(app, db, datos_base):
    CajaService.abrir_turno(datos_base["admin"], 500)
    CajaService.registrar_movimiento(datos_base["admin"], "egreso", 50, "Compra de bolsas")
    CajaService.registrar_movimiento(datos_base["admin"], "ingreso", 20, "Ajuste")

    apertura = CajaService.apertura_actual()
    resumen = CajaService.resumen_turno(apertura)
    assert resumen["total_egresos"] == 50
    assert resumen["total_ingresos"] == 20
    # 500 inicial + 0 ventas en efectivo + 20 ingreso - 50 egreso
    assert resumen["monto_esperado"] == 470

    cierre = CajaService.cerrar_turno(datos_base["admin"], 460, "Faltaron C$10")
    assert cierre.diferencia == -10
    assert CajaService.apertura_actual() is None
