"""Pago dividido: parte de la cuenta en un metodo y parte en otro."""
from decimal import Decimal

import pytest

from app.services.caja_service import CajaService
from app.services.venta_service import VentaService, VentaError


def _cart(quesillo):
    # Quesillo Lo Nuestro: C$ 60
    return [{"id_producto": quesillo["final"].id_producto, "cantidad": 2, "precio": 0}]


def test_transferencia_mas_efectivo(app, db, datos_base, quesillo):
    venta = VentaService.registrar_venta(
        datos_base["cajero"], _cart(quesillo), propina=0,
        pagos=[{"metodo": "Transferencia", "monto": 70}, {"metodo": "Efectivo", "monto": 100}],
    )
    assert venta.total == Decimal("120.00")
    assert venta.metodo_pago == "Mixto"
    assert venta.pagos_detalle == [
        {"metodo": "Transferencia", "monto": 70.0}, {"metodo": "Efectivo", "monto": 100.0},
    ]
    assert venta.cambio == Decimal("50.00")
    # A la caja solo entra lo que quedo en efectivo: 120 - 70.
    assert VentaService.efectivo_de(venta) == Decimal("50.00")


def test_la_caja_cuenta_solo_la_parte_en_efectivo(app, db, datos_base, quesillo):
    VentaService.registrar_venta(
        datos_base["cajero"], _cart(quesillo),
        pagos=[{"metodo": "Tarjeta BAC", "monto": 100}, {"metodo": "Efectivo", "monto": 20}],
    )
    VentaService.registrar_venta(datos_base["cajero"], _cart(quesillo), metodo_pago="Efectivo")
    resumen = CajaService.resumen_turno(CajaService.apertura_actual())
    assert resumen["efectivo_en_ventas"] == Decimal("140.00")  # 20 + 120


def test_no_cubre_el_total(app, db, datos_base, quesillo):
    with pytest.raises(VentaError):
        VentaService.registrar_venta(
            datos_base["cajero"], _cart(quesillo),
            pagos=[{"metodo": "Transferencia", "monto": 50}, {"metodo": "Efectivo", "monto": 20}],
        )


def test_tarjeta_no_puede_pasar_del_total(app, db, datos_base, quesillo):
    with pytest.raises(VentaError):
        VentaService.registrar_venta(
            datos_base["cajero"], _cart(quesillo),
            pagos=[{"metodo": "Tarjeta BAC", "monto": 150}, {"metodo": "Efectivo", "monto": 10}],
        )


def test_un_solo_pago_es_como_siempre(app, db, datos_base, quesillo):
    venta = VentaService.registrar_venta(
        datos_base["cajero"], _cart(quesillo), metodo_pago="Transferencia",
        pagos=[{"metodo": "Transferencia", "monto": 120}],
    )
    assert venta.metodo_pago == "Transferencia"
    assert venta.pagos_detalle is None
    assert VentaService.efectivo_de(venta) == Decimal("0")


def test_nota_del_producto_se_guarda(app, db, datos_base, quesillo):
    venta = VentaService.registrar_venta(datos_base["cajero"], [
        {"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 0,
         "comentario": "bien tostado"},
    ])
    assert venta.detalles[0].comentario == "bien tostado"
