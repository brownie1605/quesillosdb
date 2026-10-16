"""Anular una venta devuelve exactamente lo que desconto, opciones incluidas.

Antes se recalculaba con la receta actual y sin la personalizacion: una
receta de solo opciones (Fajitas bowl) no devolvia nada y un Desayuno
tipico no devolvia la opcion elegida.
"""
from decimal import Decimal

from app.models import Producto, Inventario
from app.models.receta import RecetaOpcionItem
from app.services.inventario_service import InventarioService
from app.services.receta_service import RecetaService
from app.services.venta_service import VentaService


def _producto(db, nombre, tipo, stock=0, precio=0):
    p = Producto(id_empresa=1, nombre=nombre, tipo_producto=tipo, precio_compra=0,
                 precio_venta=precio, estado="activo", es_ingrediente_receta=(tipo == "insumo"))
    db.session.add(p)
    db.session.flush()
    db.session.add(Inventario(id_producto=p.id_producto, id_sucursal=1, stock_actual=stock))
    db.session.commit()
    return p


def _opcion(id_insumo):
    return RecetaOpcionItem.query.filter_by(id_producto_insumo=id_insumo).first().id_item


def test_anular_receta_de_solo_opciones_devuelve_la_opcion(app, db, datos_base):
    res = _producto(db, "Fajitas de res", "insumo", stock=10)
    pollo = _producto(db, "Fajitas de pollo", "insumo", stock=10)
    bowl = _producto(db, "Fajitas bowl", "final", precio=300)
    RecetaService.crear_receta(
        bowl.id_producto, {}, [], datos_base["admin"].id_usuario,
        grupos_opciones=[{"nombre": "Fajitas", "obligatorio": True, "items": [
            {"nombre": "Pollo", "id_producto_insumo": pollo.id_producto, "cantidad": 1},
            {"nombre": "Res", "id_producto_insumo": res.id_producto, "cantidad": 1},
        ]}],
    )
    venta = VentaService.registrar_venta(datos_base["cajero"], [
        {"id_producto": bowl.id_producto, "cantidad": 2, "precio": 0,
         "opciones": [_opcion(res.id_producto)]},
    ])
    assert InventarioService.stock_de(res.id_producto) == Decimal("8")

    VentaService.anular_venta(venta.id_venta, datos_base["cajero"])

    assert InventarioService.stock_de(res.id_producto) == Decimal("10")
    assert InventarioService.stock_de(pollo.id_producto) == Decimal("10")


def test_anular_devuelve_la_opcion_elegida_ademas_de_lo_fijo(app, db, datos_base):
    huevo = _producto(db, "Huevo", "insumo", stock=20)
    jamon = _producto(db, "Jamon", "insumo", stock=5)
    desayuno = _producto(db, "Desayuno tipico", "final", precio=180)
    RecetaService.crear_receta(
        desayuno.id_producto, {}, [{"id_producto": huevo.id_producto, "cantidad_necesaria": 2}],
        datos_base["admin"].id_usuario,
        grupos_opciones=[{"nombre": "Opcion", "obligatorio": True, "items": [
            {"nombre": "Jamon", "id_producto_insumo": jamon.id_producto, "cantidad": 1},
        ]}],
    )
    venta = VentaService.registrar_venta(datos_base["cajero"], [
        {"id_producto": desayuno.id_producto, "cantidad": 1, "precio": 0,
         "opciones": [_opcion(jamon.id_producto)]},
    ])
    VentaService.anular_venta(venta.id_venta, datos_base["cajero"])

    assert InventarioService.stock_de(huevo.id_producto) == Decimal("20")
    assert InventarioService.stock_de(jamon.id_producto) == Decimal("5")


def test_anular_dos_veces_no_devuelve_doble(app, db, datos_base, quesillo):
    antes = InventarioService.stock_de(quesillo["tortilla"].id_producto)
    venta = VentaService.registrar_venta(datos_base["cajero"], [
        {"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 0},
    ])
    InventarioService.revertir_venta(venta)
    InventarioService.revertir_venta(venta)
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes
