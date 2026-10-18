"""Carta de Pedidos Ya: copias " P.YA" de los platos, en su propia categoria.

Cada copia se vende igual que el original pero queda marcada como
`es_pedidos_ya`, asi el dashboard puede sumar lo vendido por Pedidos Ya.

Inventario:
  - Plato con receta activa -> la copia lleva la MISMA receta (ingredientes,
    opciones y lo que se puede quitar): descuenta los mismos insumos.
  - Plato sin receta (se vende de su propio stock, ej. Gallopinto o una
    bebida) -> la receta de la copia es "1 del plato original": comparten el
    mismo stock, y si algun dia el original tiene receta, la copia la sigue.
"""
from decimal import Decimal

from app.extensions import db
from app.models import Categoria, Producto
from app.models.receta import Receta, RecetaIngrediente, RecetaOpcionGrupo, RecetaOpcionItem
from app.services.inventario_service import InventarioService

NOMBRE_CATEGORIA = "Pedidos Ya"
SUFIJO = " P.YA"


def _categoria(id_empresa):
    cat = Categoria.query.filter(db.func.lower(Categoria.nombre) == NOMBRE_CATEGORIA.lower()).first()
    if not cat:
        cat = Categoria(id_empresa=id_empresa, nombre=NOMBRE_CATEGORIA,
                        descripcion="Carta de Pedidos Ya", estado="activo")
        db.session.add(cat)
        db.session.flush()
    return cat


def _copiar_receta(original, receta_original, copia, usuario_id):
    """Receta de la copia: la misma del original, o "1 del original"."""
    receta = Receta(
        id_producto=copia.id_producto,
        nombre=copia.nombre,
        descripcion=receta_original.descripcion if receta_original else None,
        modo_preparacion=receta_original.modo_preparacion if receta_original else None,
        tiempo_preparacion=receta_original.tiempo_preparacion if receta_original else None,
        rendimiento=(receta_original.rendimiento if receta_original else None) or Decimal("1"),
        id_unidad_rendimiento=receta_original.id_unidad_rendimiento if receta_original else None,
        costo_total=(receta_original.costo_total if receta_original else original.precio_compra) or 0,
        estado="activo",
        creado_por=usuario_id,
    )
    db.session.add(receta)
    db.session.flush()

    if receta_original is not None:
        for ing in receta_original.ingredientes:
            db.session.add(RecetaIngrediente(
                id_receta=receta.id_receta, id_producto=ing.id_producto,
                cantidad_necesaria=ing.cantidad_necesaria, id_unidad=ing.id_unidad,
                costo_estimado=ing.costo_estimado, opcional=ing.opcional, excluible=ing.excluible,
            ))
        for grupo in receta_original.grupos_opciones:
            nuevo = RecetaOpcionGrupo(id_receta=receta.id_receta, nombre=grupo.nombre,
                                      obligatorio=grupo.obligatorio, orden=grupo.orden)
            db.session.add(nuevo)
            db.session.flush()
            for item in grupo.items:
                db.session.add(RecetaOpcionItem(
                    id_grupo=nuevo.id_grupo, nombre=item.nombre,
                    id_producto_insumo=item.id_producto_insumo, cantidad=item.cantidad,
                    es_default=item.es_default, orden=item.orden,
                ))
    else:
        db.session.add(RecetaIngrediente(
            id_receta=receta.id_receta, id_producto=original.id_producto,
            cantidad_necesaria=Decimal("1"), id_unidad=original.id_unidad,
            costo_estimado=original.precio_compra or 0, opcional=False, excluible=False,
        ))
    copia.es_receta = True


def crear_copias(usuario_id, id_empresa=1):
    """Crea la categoria y una copia " P.YA" de cada plato final activo.

    Se puede correr mas de una vez: salta los platos que ya tienen su copia.
    """
    cat = _categoria(id_empresa)
    originales = (
        Producto.query
        .filter(Producto.estado == "activo", Producto.tipo_producto == "final",
                Producto.se_vende.is_(True), Producto.es_pedidos_ya.is_(False))
        .order_by(Producto.nombre)
        .all()
    )
    existentes = {p.nombre for p in Producto.query.filter(Producto.nombre.like("%" + SUFIJO)).all()}
    resumen = {"categoria": cat.nombre, "creados": [], "omitidos": 0}

    for original in originales:
        if original.nombre.endswith(SUFIJO) or (original.nombre + SUFIJO) in existentes:
            resumen["omitidos"] += 1
            continue
        copia = Producto(
            id_empresa=original.id_empresa or id_empresa,
            id_categoria=cat.id_categoria,
            id_proveedor=original.id_proveedor,
            id_unidad=original.id_unidad,
            nombre=(original.nombre + SUFIJO)[:150],
            descripcion=original.descripcion,
            precio_compra=original.precio_compra,
            precio_venta=original.precio_venta,
            imagen_url=original.imagen_url,
            imagen_datos=original.imagen_datos,
            imagen_mimetype=original.imagen_mimetype,
            aplica_impuesto=original.aplica_impuesto,
            tipo_producto="final",
            es_ingrediente_receta=False,
            se_vende=True,
            impresora=original.impresora,
            estado="activo",
            es_pedidos_ya=True,
        )
        db.session.add(copia)
        db.session.flush()
        InventarioService.obtener_o_crear(copia.id_producto)

        receta_original = Receta.query.filter_by(id_producto=original.id_producto, estado="activo").first()
        if receta_original is not None and not (receta_original.ingredientes or receta_original.grupos_opciones):
            receta_original = None
        _copiar_receta(original, receta_original, copia, usuario_id)
        resumen["creados"].append(copia.nombre)

    db.session.commit()
    return resumen
