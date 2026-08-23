"""Flujo de mesas: atender -> agregar/quitar productos -> cobrar."""
from decimal import Decimal

import pytest

from app.models import Mesa
from app.services.venta_service import VentaService, VentaError
from app.services.mesa_service import MesaService
from app.services.inventario_service import InventarioService


@pytest.fixture()
def mesa(app, db):
    m = Mesa(nombre="Mesa 1", tipo="mesa", capacidad=4, orden=1)
    db.session.add(m)
    db.session.commit()
    return m


def _item(producto, cantidad=1):
    return {"id_producto": producto.id_producto, "cantidad": cantidad, "precio": float(producto.precio_venta)}


def test_atender_mesa_abre_cuenta_y_ocupa_la_mesa(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    assert venta.estado == "pendiente"
    assert venta.id_mesa == mesa.id_mesa
    assert mesa.estado == "ocupada"
    assert mesa.id_venta_actual == venta.id_venta


def test_no_se_puede_atender_una_mesa_ya_ocupada(app, db, datos_base, quesillo, mesa):
    VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    with pytest.raises(VentaError):
        VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])


def test_agregar_items_a_cuenta_abierta_recalcula_el_total(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"], 1)])
    total_antes = venta.total

    VentaService.agregar_items(venta, [_item(quesillo["tortilla"], 2)], datos_base["cajero"])
    assert venta.total == total_antes + Decimal(str(quesillo["tortilla"].precio_venta)) * 2
    assert len(venta.detalles) == 2


def test_quitar_item_revierte_el_inventario(app, db, datos_base, quesillo, mesa):
    antes = InventarioService.stock_de(quesillo["tortilla"].id_producto)
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["tortilla"], 5)])
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes - 5

    det = venta.detalles[0]
    VentaService.quitar_item(venta, det.id_detalle_venta, datos_base["cajero"])
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes
    assert venta.total == 0


def test_cobrar_mesa_completa_la_venta_y_libera_la_mesa(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"], 1)])
    venta = VentaService.cobrar_mesa(
        venta, datos_base["cajero"], metodo_pago="Efectivo", propina=10, monto_recibido=100
    )
    assert venta.estado == "completada"
    assert venta.total == Decimal(str(quesillo["final"].precio_venta)) + Decimal("10")
    assert mesa.estado == "libre"
    assert mesa.id_venta_actual is None


def test_no_se_puede_cobrar_una_cuenta_vacia(app, db, datos_base, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[])
    with pytest.raises(VentaError):
        VentaService.cobrar_mesa(venta, datos_base["cajero"])


def test_mesa_service_listar_y_desactivar(app, db, mesa):
    assert mesa in MesaService.listar()
    MesaService.desactivar(mesa.id_mesa)
    assert mesa not in MesaService.listar()
