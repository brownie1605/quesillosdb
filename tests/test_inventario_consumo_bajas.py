"""Inventario: consumo por dia/mes y bajas (merma, vencido...)."""
from decimal import Decimal

import pytest

from app.services.inventario_service import InventarioService, StockInsuficiente
from app.services.venta_service import VentaService
from app.utils.date_utils import nicaragua_now


def _vender(datos_base, quesillo, cantidad):
    return VentaService.registrar_venta(datos_base["cajero"], [
        {"id_producto": quesillo["final"].id_producto, "cantidad": cantidad, "precio": 0},
    ])


def test_consumo_del_dia_sale_de_las_ventas(app, db, datos_base, quesillo):
    _vender(datos_base, quesillo, 3)       # receta: 2 tortillas y 1 quesillo por plato
    hoy = nicaragua_now().date()
    datos = InventarioService.consumo(hoy, hoy, "dia")
    usado = {r["id_producto"]: r["cantidad"] for r in datos["resumen"]}
    assert usado[quesillo["tortilla"].id_producto] == 6
    assert usado[quesillo["queso"].id_producto] == 3
    assert datos["detalle"][0]["periodo"] == hoy.isoformat()


def test_una_venta_anulada_no_cuenta_como_consumo(app, db, datos_base, quesillo):
    venta = _vender(datos_base, quesillo, 2)
    _vender(datos_base, quesillo, 1)
    VentaService.anular_venta(venta.id_venta, datos_base["cajero"])
    hoy = nicaragua_now().date()
    usado = {r["id_producto"]: r["cantidad"] for r in InventarioService.consumo(hoy, hoy, "mes")["resumen"]}
    assert usado[quesillo["tortilla"].id_producto] == 2


def test_baja_resta_stock_y_se_lista(app, db, datos_base, quesillo):
    crema = quesillo["crema"].id_producto
    antes = InventarioService.stock_de(crema)
    InventarioService.registrar_baja(crema, 2, "Vencido", datos_base["admin"].id_usuario, "lote de ayer")
    assert InventarioService.stock_de(crema) == antes - Decimal("2")

    hoy = nicaragua_now().date()
    bajas = InventarioService.bajas(hoy, hoy)
    assert len(bajas) == 1
    assert bajas[0]["cantidad"] == 2
    assert bajas[0]["motivo"] == "Vencido - lote de ayer"
    assert bajas[0]["costo"] == 120.0      # 2 x C$ 60 de compra
    # Una baja no es consumo de ventas.
    assert all(r["id_producto"] != crema for r in InventarioService.consumo(hoy, hoy)["resumen"])


def test_baja_mayor_al_stock_se_rechaza(app, db, datos_base, quesillo):
    with pytest.raises(StockInsuficiente):
        InventarioService.registrar_baja(quesillo["crema"].id_producto, 9999, "Merma", datos_base["admin"].id_usuario)
