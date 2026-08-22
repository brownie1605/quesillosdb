"""Recetas: costo, descuento de insumos y disponibilidad."""
from decimal import Decimal

import pytest

from app.services.receta_service import RecetaService, RecetaError
from app.services.inventario_service import InventarioService, StockInsuficiente
from app.services.venta_service import VentaService


def test_receta_se_crea_con_sus_ingredientes(app, quesillo):
    receta = quesillo["receta"]
    assert receta.id_receta is not None
    assert len(receta.ingredientes) == 4
    assert quesillo["final"].es_receta is True
    # Todos los insumos quedan marcados como usables en recetas
    assert quesillo["tortilla"].es_ingrediente_receta is True


def test_costo_de_la_receta_suma_los_insumos(app, quesillo):
    # 2×1.50 + 0.25×60 + 6×2 + 1×25 = 3 + 15 + 12 + 25 = 55.00
    costo = RecetaService.calcular_costo_receta(quesillo["receta"])
    assert costo == Decimal("55.00")


def test_requerimiento_expande_la_receta_a_insumos(app, quesillo):
    req = RecetaService.requerimiento_de_venta(quesillo["final"].id_producto, 3)
    assert req[quesillo["tortilla"].id_producto] == Decimal("6")
    assert req[quesillo["crema"].id_producto] == Decimal("0.75")
    assert req[quesillo["cebolla"].id_producto] == Decimal("18")
    assert req[quesillo["queso"].id_producto] == Decimal("3")
    # El producto final no consume stock propio
    assert quesillo["final"].id_producto not in req


def test_insumo_vendido_solo_no_expande(app, quesillo):
    req = RecetaService.requerimiento_de_venta(quesillo["tortilla"].id_producto, 12)
    assert req == {quesillo["tortilla"].id_producto: Decimal("12")}


def test_vender_receta_descuenta_los_insumos(app, db, datos_base, quesillo):
    antes_tortilla = InventarioService.stock_de(quesillo["tortilla"].id_producto)
    antes_crema = InventarioService.stock_de(quesillo["crema"].id_producto)

    VentaService.registrar_venta(
        datos_base["cajero"],
        [{"id_producto": quesillo["final"].id_producto, "cantidad": 2, "precio": 60.0}],
    )

    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes_tortilla - 4
    assert InventarioService.stock_de(quesillo["crema"].id_producto) == antes_crema - Decimal("0.5")


def test_vender_insumo_directo_descuenta_solo_el_insumo(app, db, datos_base, quesillo):
    antes = InventarioService.stock_de(quesillo["tortilla"].id_producto)
    VentaService.registrar_venta(
        datos_base["cajero"],
        [{"id_producto": quesillo["tortilla"].id_producto, "cantidad": 12, "precio": 3.0}],
    )
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes - 12


def test_stock_insuficiente_bloquea_la_venta(app, db, datos_base, quesillo):
    # Solo hay 10 L de crema -> alcanza para 40 quesillos
    with pytest.raises(StockInsuficiente):
        VentaService.registrar_venta(
            datos_base["cajero"],
            [{"id_producto": quesillo["final"].id_producto, "cantidad": 500, "precio": 60.0}],
        )


def test_maximo_producible_lo_limita_el_insumo_mas_escaso(app, quesillo):
    # tortilla 100/2=50 · crema 10/0.25=40 · cebolla 120/6=20 · queso 20/1=20
    assert RecetaService.maximo_producible(quesillo["final"].id_producto) == 20.0


def test_no_se_permite_una_receta_de_si_misma(app, db, datos_base, quesillo):
    from app.models import Producto, Receta

    otro = Producto(id_empresa=1, nombre="Otro", tipo_producto="final",
                    precio_venta=10, estado="activo")
    db.session.add(otro)
    db.session.commit()

    with pytest.raises(RecetaError):
        RecetaService.crear_receta(
            otro.id_producto, {"nombre": "Otro"},
            [{"id_producto": otro.id_producto, "cantidad_necesaria": 1}],
            datos_base["admin"].id_usuario,
        )


def test_anular_venta_devuelve_los_insumos(app, db, datos_base, quesillo):
    antes = InventarioService.stock_de(quesillo["tortilla"].id_producto)
    venta = VentaService.registrar_venta(
        datos_base["cajero"],
        [{"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 60.0}],
    )
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes - 2

    VentaService.anular_venta(venta.id_venta, datos_base["admin"])
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes
    assert venta.estado == "anulada"
