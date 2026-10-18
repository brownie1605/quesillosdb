"""Mesa: separar la cuenta en varias, descuento en % y cliente por cuenta."""
from decimal import Decimal

import pytest

from app.models import Mesa
from app.services.inventario_service import InventarioService
from app.services.venta_service import VentaService, VentaError


@pytest.fixture()
def mesa(app, db):
    m = Mesa(nombre="Mesa 1", tipo="mesa", capacidad=4, orden=1)
    db.session.add(m)
    db.session.commit()
    return m


def _item(producto, cantidad=1):
    return {"id_producto": producto.id_producto, "cantidad": cantidad, "precio": 0}


def _cuenta_con_3_quesillos_y_tortillas(datos_base, quesillo, mesa):
    return VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[
        _item(quesillo["final"], 3),       # 3 x 60 = 180
        _item(quesillo["tortilla"], 2),    # 2 x 3 = 6
    ])


def test_separar_parte_una_linea_y_crea_la_cuenta_2(app, db, datos_base, quesillo, mesa):
    venta = _cuenta_con_3_quesillos_y_tortillas(datos_base, quesillo, mesa)
    linea_quesillo = next(d for d in venta.detalles if d.id_producto == quesillo["final"].id_producto)

    nueva = VentaService.separar_cuenta(
        venta, [{"id_detalle": linea_quesillo.id_detalle_venta, "cantidad": 1}], datos_base["cajero"])

    assert nueva.estado == "pendiente" and nueva.id_mesa == mesa.id_mesa
    assert venta.total == Decimal("126.00")        # 2 quesillos + 2 tortillas
    assert nueva.total == Decimal("60.00")
    assert len(nueva.detalles) == 1 and nueva.detalles[0].cantidad == 1
    assert [c.id_venta for c in VentaService.cuentas_de_mesa(mesa)] == [venta.id_venta, nueva.id_venta]


def test_separar_no_cambia_el_stock_y_anular_devuelve_solo_lo_de_esa_cuenta(app, db, datos_base, quesillo, mesa):
    queso = quesillo["queso"].id_producto
    antes = InventarioService.stock_de(queso)
    venta = _cuenta_con_3_quesillos_y_tortillas(datos_base, quesillo, mesa)
    linea = next(d for d in venta.detalles if d.id_producto == quesillo["final"].id_producto)

    nueva = VentaService.separar_cuenta(
        venta, [{"id_detalle": linea.id_detalle_venta, "cantidad": 1}], datos_base["cajero"])
    assert InventarioService.stock_de(queso) == antes - 3

    VentaService.anular_venta(nueva.id_venta, datos_base["cajero"])
    assert InventarioService.stock_de(queso) == antes - 2    # solo vuelve el de la cuenta 2
    assert mesa.estado == "ocupada"                            # la cuenta 1 sigue abierta


def test_la_mesa_se_libera_al_cobrar_la_ultima_cuenta(app, db, datos_base, quesillo, mesa):
    venta = _cuenta_con_3_quesillos_y_tortillas(datos_base, quesillo, mesa)
    linea = next(d for d in venta.detalles if d.id_producto == quesillo["tortilla"].id_producto)
    nueva = VentaService.separar_cuenta(
        venta, [{"id_detalle": linea.id_detalle_venta, "cantidad": 2}], datos_base["cajero"])

    VentaService.cobrar_mesa(venta, datos_base["cajero"], metodo_pago="Tarjeta BAC")
    assert mesa.estado == "ocupada" and mesa.id_venta_actual == nueva.id_venta

    VentaService.cobrar_mesa(nueva, datos_base["cajero"], metodo_pago="Tarjeta BAC")
    assert mesa.estado == "libre" and mesa.id_venta_actual is None


def test_no_se_puede_dejar_vacia_la_cuenta_original(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"], 2)])
    linea = venta.detalles[0]
    with pytest.raises(VentaError):
        VentaService.separar_cuenta(
            venta, [{"id_detalle": linea.id_detalle_venta, "cantidad": 2}], datos_base["cajero"])
    with pytest.raises(VentaError):
        VentaService.separar_cuenta(
            venta, [{"id_detalle": linea.id_detalle_venta, "cantidad": 5}], datos_base["cajero"])


def test_descuento_en_porcentaje_sigue_al_subtotal(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"], 1)])
    VentaService.fijar_descuento(venta, 10)
    assert venta.descuento == Decimal("6.00") and venta.total == Decimal("54.00")

    VentaService.agregar_items(venta, [_item(quesillo["final"], 1)], datos_base["cajero"])
    assert venta.descuento == Decimal("12.00") and venta.total == Decimal("108.00")

    venta = VentaService.cobrar_mesa(venta, datos_base["cajero"], metodo_pago="Tarjeta BAC",
                                     descuento=12)
    assert venta.total == Decimal("108.00")

    with pytest.raises(VentaError):
        VentaService.fijar_descuento(venta, 10)             # ya cobrada


def test_cliente_por_cuenta_y_publico_general_por_defecto(app, db, datos_base, quesillo, mesa):
    from app.models.cliente import Cliente
    cliente = Cliente(id_empresa=1, nombre="Ana", estado="activo")
    db.session.add(cliente)
    db.session.commit()

    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"], 1)])
    assert venta.id_cliente is None
    VentaService.fijar_cliente(venta, cliente.id_cliente)
    venta = VentaService.cobrar_mesa(venta, datos_base["cajero"], metodo_pago="Tarjeta BAC", id_cliente=None)
    assert venta.id_cliente == cliente.id_cliente
