"""Carta de Pedidos Ya: copias " P.YA" que descuentan lo mismo que el original."""
from decimal import Decimal

from app.models import Producto, Inventario, Categoria
from app.models.receta import RecetaOpcionItem
from app.services.inventario_service import InventarioService
from app.services.pedidos_ya_service import crear_copias
from app.services.receta_service import RecetaService
from app.services.venta_service import VentaService


def _copia(nombre):
    return Producto.query.filter_by(nombre=nombre + " P.YA").first()


def _vender(datos_base, producto, opciones=None):
    item = {"id_producto": producto.id_producto, "cantidad": 1, "precio": 0}
    if opciones:
        item["opciones"] = opciones
    return VentaService.registrar_venta(datos_base["cajero"], [item])


def test_copia_con_receta_descuenta_los_mismos_insumos(app, db, datos_base, quesillo):
    crear_copias(datos_base["admin"].id_usuario)
    copia = _copia("Quesillo Lo Nuestro")
    assert copia is not None and copia.es_pedidos_ya
    assert copia.precio_venta == quesillo["final"].precio_venta
    assert Categoria.query.get(copia.id_categoria).nombre == "Pedidos Ya"

    antes = InventarioService.stock_de(quesillo["tortilla"].id_producto)
    _vender(datos_base, copia)
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes - 2


def test_copia_sin_receta_comparte_el_stock_del_original(app, db, datos_base):
    gallopinto = Producto(id_empresa=1, nombre="Gallopinto", tipo_producto="final",
                          precio_venta=40, estado="activo")
    db.session.add(gallopinto)
    db.session.flush()
    db.session.add(Inventario(id_producto=gallopinto.id_producto, id_sucursal=1, stock_actual=5))
    db.session.commit()

    crear_copias(datos_base["admin"].id_usuario)
    copia = _copia("Gallopinto")
    assert RecetaService.maximo_producible(copia.id_producto) == 5
    _vender(datos_base, copia)
    assert InventarioService.stock_de(gallopinto.id_producto) == Decimal("4")


def test_copia_con_opciones_descuenta_la_opcion(app, db, datos_base):
    def producto(nombre, tipo, stock=0):
        p = Producto(id_empresa=1, nombre=nombre, tipo_producto=tipo, precio_venta=300, estado="activo")
        db.session.add(p)
        db.session.flush()
        db.session.add(Inventario(id_producto=p.id_producto, id_sucursal=1, stock_actual=stock))
        db.session.commit()
        return p

    res = producto("Fajitas de res", "insumo", 10)
    pollo = producto("Fajitas de pollo", "insumo", 10)
    bowl = producto("Fajitas bowl", "final")
    RecetaService.crear_receta(bowl.id_producto, {}, [], datos_base["admin"].id_usuario, grupos_opciones=[
        {"nombre": "Fajitas", "obligatorio": True, "items": [
            {"nombre": "Pollo", "id_producto_insumo": pollo.id_producto, "cantidad": 1},
            {"nombre": "Res", "id_producto_insumo": res.id_producto, "cantidad": 1},
        ]},
    ])
    crear_copias(datos_base["admin"].id_usuario)
    copia = _copia("Fajitas bowl")
    item_res = (RecetaOpcionItem.query
                .filter_by(id_producto_insumo=res.id_producto)
                .order_by(RecetaOpcionItem.id_item.desc()).first())
    _vender(datos_base, copia, opciones=[item_res.id_item])
    assert InventarioService.stock_de(res.id_producto) == Decimal("9")


def test_no_duplica_si_se_corre_dos_veces(app, db, datos_base, quesillo):
    primero = crear_copias(datos_base["admin"].id_usuario)
    segundo = crear_copias(datos_base["admin"].id_usuario)
    assert len(primero["creados"]) >= 1
    assert segundo["creados"] == []
    assert Producto.query.filter_by(nombre="Quesillo Lo Nuestro P.YA").count() == 1
