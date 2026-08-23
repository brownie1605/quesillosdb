"""Personalizacion de recetas: ingredientes quitables y grupos de opciones.

Ejemplo del negocio: "Quesillo sin cebolla", o un "Desayuno tipico" donde el
cliente elige la proteina (salsa ranchera / jamon / chorizo criollo).
"""
from decimal import Decimal

from app.models import Producto, Inventario
from app.services.receta_service import RecetaService
from app.services.inventario_service import InventarioService
from app.services.venta_service import VentaService


def _marcar_cebolla_excluible(db, quesillo, admin_id):
    """Reedita la receta del fixture para que la cebolla se pueda quitar."""
    u = quesillo["tortilla"].id_unidad
    ingredientes = [
        {"id_producto": quesillo["tortilla"].id_producto, "cantidad_necesaria": 2},
        {"id_producto": quesillo["crema"].id_producto, "cantidad_necesaria": 0.25},
        {"id_producto": quesillo["cebolla"].id_producto, "cantidad_necesaria": 6, "excluible": True},
        {"id_producto": quesillo["queso"].id_producto, "cantidad_necesaria": 1},
    ]
    return RecetaService.actualizar_receta(
        quesillo["receta"].id_receta, {"nombre": "Quesillo Lo Nuestro"}, ingredientes, admin_id
    )


def test_ingrediente_excluible_se_marca_en_la_receta(app, db, datos_base, quesillo):
    _marcar_cebolla_excluible(db, quesillo, datos_base["admin"].id_usuario)
    ing = [i for i in quesillo["receta"].ingredientes if i.id_producto == quesillo["cebolla"].id_producto][0]
    assert ing.excluible is True


def test_requerimiento_respeta_exclusion(app, db, datos_base, quesillo):
    _marcar_cebolla_excluible(db, quesillo, datos_base["admin"].id_usuario)
    req = RecetaService.requerimiento_de_venta(
        quesillo["final"].id_producto, 1, excluidos=[quesillo["cebolla"].id_producto]
    )
    assert quesillo["cebolla"].id_producto not in req
    assert req[quesillo["tortilla"].id_producto] == Decimal("2")


def test_vender_sin_cebolla_no_descuenta_cebolla(app, db, datos_base, quesillo):
    _marcar_cebolla_excluible(db, quesillo, datos_base["admin"].id_usuario)
    antes_cebolla = InventarioService.stock_de(quesillo["cebolla"].id_producto)
    antes_tortilla = InventarioService.stock_de(quesillo["tortilla"].id_producto)

    venta = VentaService.registrar_venta(
        datos_base["cajero"],
        [{
            "id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 60.0,
            "excluidos": [quesillo["cebolla"].id_producto],
        }],
    )

    assert InventarioService.stock_de(quesillo["cebolla"].id_producto) == antes_cebolla
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes_tortilla - 2
    detalle = venta.detalles[0] if hasattr(venta, "detalles") else None
    # Se guarda el comentario legible para el ticket/carrito.
    from app.models import DetalleVenta
    det = DetalleVenta.query.filter_by(id_venta=venta.id_venta).first()
    assert det.comentario == "Sin Cebolla"
    assert det.personalizacion["excluidos"] == [quesillo["cebolla"].id_producto]


def test_opciones_de_venta_incluye_excluibles_y_grupos(app, db, datos_base, quesillo):
    _marcar_cebolla_excluible(db, quesillo, datos_base["admin"].id_usuario)
    u = datos_base["unidades"]

    chorizo = Producto(
        id_empresa=1, nombre="Chorizo criollo", tipo_producto="insumo",
        precio_compra=10.0, precio_venta=15.0, id_unidad=u["und"].id_unidad, estado="activo",
    )
    db.session.add(chorizo)
    db.session.flush()
    db.session.add(Inventario(id_producto=chorizo.id_producto, id_sucursal=1, stock_actual=50, stock_minimo=0))
    db.session.commit()

    RecetaService.actualizar_receta(
        quesillo["receta"].id_receta, {"nombre": "Quesillo Lo Nuestro"}, None,
        datos_base["admin"].id_usuario,
        grupos_opciones=[{
            "nombre": "Proteina",
            "obligatorio": True,
            "items": [
                {"nombre": "Sin proteina extra", "es_default": True},
                {"nombre": "Chorizo criollo", "id_producto_insumo": chorizo.id_producto, "cantidad": 1},
            ],
        }],
    )

    datos = RecetaService.opciones_de_venta(quesillo["final"].id_producto)
    assert datos is not None
    assert len(datos["ingredientes_excluibles"]) == 1
    assert datos["ingredientes_excluibles"][0]["id_producto"] == quesillo["cebolla"].id_producto
    assert len(datos["grupos"]) == 1
    assert datos["grupos"][0]["nombre"] == "Proteina"
    assert len(datos["grupos"][0]["items"]) == 2


def test_elegir_opcion_descuenta_su_insumo(app, db, datos_base, quesillo):
    u = datos_base["unidades"]
    chorizo = Producto(
        id_empresa=1, nombre="Chorizo criollo", tipo_producto="insumo",
        precio_compra=10.0, precio_venta=15.0, id_unidad=u["und"].id_unidad, estado="activo",
    )
    db.session.add(chorizo)
    db.session.flush()
    db.session.add(Inventario(id_producto=chorizo.id_producto, id_sucursal=1, stock_actual=50, stock_minimo=0))
    db.session.commit()

    receta = RecetaService.actualizar_receta(
        quesillo["receta"].id_receta, {"nombre": "Quesillo Lo Nuestro"}, None,
        datos_base["admin"].id_usuario,
        grupos_opciones=[{
            "nombre": "Proteina",
            "obligatorio": True,
            "items": [{"nombre": "Chorizo criollo", "id_producto_insumo": chorizo.id_producto, "cantidad": 2}],
        }],
    )
    id_item = receta.grupos_opciones[0].items[0].id_item

    antes = InventarioService.stock_de(chorizo.id_producto)
    VentaService.registrar_venta(
        datos_base["cajero"],
        [{
            "id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 60.0,
            "opciones": [id_item],
        }],
    )
    assert InventarioService.stock_de(chorizo.id_producto) == antes - 2


def test_crear_receta_con_producto_nuevo_en_el_mismo_paso(app, db, datos_base, quesillo):
    u = datos_base["unidades"]
    receta = RecetaService.crear_receta(
        None,
        {"nombre": "Quesillo Doble"},
        [{"id_producto": quesillo["tortilla"].id_producto, "cantidad_necesaria": 4}],
        datos_base["admin"].id_usuario,
        producto_nuevo={"nombre": "Quesillo Doble", "precio_venta": 100.0},
    )
    producto = Producto.query.get(receta.id_producto)
    assert producto is not None
    assert producto.nombre == "Quesillo Doble"
    assert producto.tipo_producto == "final"
    assert producto.es_receta is True
    assert float(producto.precio_venta) == 100.0


def test_comentario_de_personalizacion(app, db, datos_base, quesillo):
    _marcar_cebolla_excluible(db, quesillo, datos_base["admin"].id_usuario)
    texto = RecetaService.comentario_de_personalizacion(
        quesillo["final"].id_producto, excluidos=[quesillo["cebolla"].id_producto], opciones=[]
    )
    assert texto == "Sin Cebolla"
