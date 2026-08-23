"""Recetas: composicion de un producto final a partir de insumos.

Ejemplo del negocio:
    Quesillo = 2 tortillas + 0.25 L crema + 6 oz cebolla + 1 quesillo(insumo)

Al vender 1 Quesillo se descuentan automaticamente esos insumos del inventario.
Los insumos tambien pueden venderse solos (ej. "Tortilla docena"), en cuyo caso
se descuenta unicamente el insumo.

Personalizacion en el POS (ej. "Desayuno tipico" o "Quesillo sin cebolla"):
    - Ingredientes marcados `excluible=True` se descuentan por defecto, pero el
      cajero/mesero puede quitarlos para esa venta puntual sin tocar la receta.
    - `RecetaOpcionGrupo` / `RecetaOpcionItem` modelan una eleccion (radio) por
      grupo, ej. "Proteina: salsa ranchera / jamon / chorizo criollo". Cada
      opcion puede descontar su propio insumo (ej. elegir "chorizo criollo"
      descuenta chorizo del inventario ademas de lo fijo de la receta).
"""
import logging
from decimal import Decimal

from app.extensions import db
from app.models.producto import Producto
from app.models.receta import Receta, RecetaIngrediente, RecetaOpcionGrupo, RecetaOpcionItem
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("recetas")


class RecetaError(Exception):
    pass


class RecetaService:

    # =================================================================
    # CRUD
    # =================================================================
    @staticmethod
    def crear_receta(id_producto, datos, ingredientes, usuario_id, producto_nuevo=None,
                      grupos_opciones=None):
        """Crea una receta.

        `id_producto`: producto final existente, o None si se pasa `producto_nuevo`.
        `producto_nuevo`: dict {nombre, precio_venta, precio_compra, id_categoria}
            para crear el producto final en el mismo paso (evita ir primero a
            /productos y luego volver aqui).
        `ingredientes`: lista de dicts {id_producto, cantidad_necesaria, id_unidad,
            opcional, excluible}.
        `grupos_opciones`: lista de dicts {nombre, obligatorio, items:[...]}.
        """
        if producto_nuevo:
            nombre = (producto_nuevo.get("nombre") or "").strip()
            if not nombre:
                raise RecetaError("El producto nuevo necesita un nombre")
            producto = Producto(
                id_empresa=producto_nuevo.get("id_empresa") or 1,
                id_categoria=producto_nuevo.get("id_categoria") or None,
                nombre=nombre,
                precio_compra=Decimal(str(producto_nuevo.get("precio_compra") or 0)),
                precio_venta=Decimal(str(producto_nuevo.get("precio_venta") or 0)),
                tipo_producto="final",
                estado="activo",
            )
            db.session.add(producto)
            db.session.flush()
            id_producto = producto.id_producto
        else:
            producto = Producto.query.get(id_producto)
            if not producto:
                raise RecetaError("El producto no existe")

        if Receta.query.filter_by(id_producto=id_producto).first():
            raise RecetaError("Este producto ya tiene una receta")
        if not ingredientes:
            raise RecetaError("La receta debe tener al menos un ingrediente")

        receta = Receta(
            id_producto=id_producto,
            nombre=datos.get("nombre") or producto.nombre,
            descripcion=datos.get("descripcion"),
            modo_preparacion=datos.get("modo_preparacion"),
            tiempo_preparacion=datos.get("tiempo_preparacion") or None,
            rendimiento=Decimal(str(datos.get("rendimiento") or 1)),
            id_unidad_rendimiento=datos.get("id_unidad_rendimiento") or None,
            estado="activo",
            creado_por=usuario_id,
        )
        db.session.add(receta)
        db.session.flush()

        RecetaService._reemplazar_ingredientes(receta, ingredientes)
        RecetaService._reemplazar_grupos_opciones(receta, grupos_opciones or [])

        producto.es_receta = True
        producto.tipo_producto = producto.tipo_producto or "final"
        producto.estado_sync = "pendiente"

        receta.costo_total = RecetaService.calcular_costo_receta(receta)
        db.session.flush()

        db.session.commit()
        log.info("Receta creada para producto %s", id_producto)
        return receta

    # -----------------------------------------------------------------
    @staticmethod
    def actualizar_receta(id_receta, datos, ingredientes, usuario_id, grupos_opciones=None):
        receta = Receta.query.get(id_receta)
        if not receta:
            raise RecetaError("Receta no encontrada")

        receta.nombre = datos.get("nombre") or receta.nombre
        receta.descripcion = datos.get("descripcion")
        receta.modo_preparacion = datos.get("modo_preparacion")
        receta.tiempo_preparacion = datos.get("tiempo_preparacion") or None
        receta.rendimiento = Decimal(str(datos.get("rendimiento") or 1))
        receta.id_unidad_rendimiento = datos.get("id_unidad_rendimiento") or None
        if datos.get("estado"):
            receta.estado = datos["estado"]
        receta.fecha_actualizacion = nicaragua_now()
        receta.estado_sync = "pendiente"

        if ingredientes is not None:
            RecetaService._reemplazar_ingredientes(receta, ingredientes)
        if grupos_opciones is not None:
            RecetaService._reemplazar_grupos_opciones(receta, grupos_opciones)

        receta.costo_total = RecetaService.calcular_costo_receta(receta)
        db.session.flush()

        db.session.commit()
        return receta

    # -----------------------------------------------------------------
    @staticmethod
    def eliminar_receta(id_receta, usuario_id):
        receta = Receta.query.get(id_receta)
        if not receta:
            raise RecetaError("Receta no encontrada")
        id_producto = receta.id_producto
        db.session.delete(receta)

        producto = Producto.query.get(id_producto)
        if producto:
            producto.es_receta = False
            producto.estado_sync = "pendiente"

        db.session.commit()
        return True

    # -----------------------------------------------------------------
    @staticmethod
    def _reemplazar_ingredientes(receta, ingredientes):
        # Se borra fila por fila (no Query.delete()) para que cada baja pase
        # por session.deleted y sync_events la encole hacia la nube; un DELETE
        # masivo no dispara eventos de instancia y deja filas huerfanas alla.
        for actual in list(receta.ingredientes):
            db.session.delete(actual)
        db.session.flush()

        vistos = set()
        for ing in ingredientes:
            id_ing = int(ing.get("id_producto"))
            if id_ing in vistos:
                continue
            if id_ing == receta.id_producto:
                raise RecetaError("Una receta no puede contenerse a si misma")
            vistos.add(id_ing)

            insumo = Producto.query.get(id_ing)
            if not insumo:
                raise RecetaError("Ingrediente inexistente: " + str(id_ing))

            cantidad = Decimal(str(ing.get("cantidad_necesaria") or 0))
            if cantidad <= 0:
                raise RecetaError("La cantidad de " + insumo.nombre + " debe ser mayor a cero")

            costo = Decimal(str(insumo.precio_compra or 0)) * cantidad

            db.session.add(
                RecetaIngrediente(
                    id_receta=receta.id_receta,
                    id_producto=id_ing,
                    cantidad_necesaria=cantidad,
                    id_unidad=ing.get("id_unidad") or insumo.id_unidad,
                    costo_estimado=costo,
                    opcional=bool(ing.get("opcional")),
                    excluible=bool(ing.get("excluible")),
                )
            )

            # Marca el insumo como utilizable en recetas.
            if not insumo.es_ingrediente_receta:
                insumo.es_ingrediente_receta = True
                insumo.estado_sync = "pendiente"
        db.session.flush()

    # -----------------------------------------------------------------
    @staticmethod
    def _reemplazar_grupos_opciones(receta, grupos):
        """Reemplaza por completo los grupos de opciones de eleccion unica."""
        # Borrado por instancia (no Query.delete()): el cascade de SQLAlchemy
        # borra tambien los items y ambas bajas quedan encoladas hacia la nube.
        for actual in list(receta.grupos_opciones):
            db.session.delete(actual)
        db.session.flush()

        for orden_g, grupo in enumerate(grupos):
            nombre_grupo = (grupo.get("nombre") or "").strip()
            if not nombre_grupo:
                continue
            items = grupo.get("items") or []
            if not items:
                continue

            og = RecetaOpcionGrupo(
                id_receta=receta.id_receta,
                nombre=nombre_grupo,
                obligatorio=grupo.get("obligatorio", True),
                orden=grupo.get("orden", orden_g),
            )
            db.session.add(og)
            db.session.flush()

            tiene_default = False
            for orden_i, item in enumerate(items):
                nombre_item = (item.get("nombre") or "").strip()
                if not nombre_item:
                    continue
                es_default = bool(item.get("es_default")) and not tiene_default
                tiene_default = tiene_default or es_default
                db.session.add(
                    RecetaOpcionItem(
                        id_grupo=og.id_grupo,
                        nombre=nombre_item,
                        id_producto_insumo=item.get("id_producto_insumo") or None,
                        cantidad=Decimal(str(item.get("cantidad") or 0)),
                        es_default=es_default,
                        orden=item.get("orden", orden_i),
                    )
                )
        db.session.flush()

    # =================================================================
    # CALCULOS
    # =================================================================
    @staticmethod
    def calcular_costo_receta(receta):
        if isinstance(receta, int):
            receta = Receta.query.get(receta)
        if not receta:
            return Decimal("0")
        total = Decimal("0")
        for ing in receta.ingredientes:
            insumo = ing.producto or Producto.query.get(ing.id_producto)
            precio = Decimal(str((insumo.precio_compra if insumo else 0) or 0))
            total += precio * Decimal(str(ing.cantidad_necesaria or 0))
        return total.quantize(Decimal("0.01"))

    # -----------------------------------------------------------------
    @staticmethod
    def opciones_de_venta(id_producto):
        """Lo que hay que preguntarle al cliente al vender este producto.

        Usado por el modal del POS: ingredientes que se pueden quitar +
        grupos de eleccion unica con sus opciones (y si cada una tiene stock).
        """
        from app.services.inventario_service import InventarioService

        producto = Producto.query.get(id_producto)
        if not producto or not producto.es_receta:
            return None
        receta = Receta.query.filter_by(id_producto=id_producto, estado="activo").first()
        if not receta:
            return None

        excluibles = [
            {"id_producto": ing.id_producto, "nombre": ing.producto.nombre if ing.producto else "?"}
            for ing in receta.ingredientes if ing.excluible
        ]

        grupos = []
        for g in receta.grupos_opciones:
            items = []
            for it in g.items:
                disponible = True
                if it.id_producto_insumo and it.cantidad:
                    disponible = InventarioService.stock_de(it.id_producto_insumo) >= Decimal(str(it.cantidad))
                items.append({
                    "id_item": it.id_item,
                    "nombre": it.nombre,
                    "es_default": bool(it.es_default),
                    "disponible": bool(disponible),
                })
            grupos.append({
                "id_grupo": g.id_grupo,
                "nombre": g.nombre,
                "obligatorio": bool(g.obligatorio),
                "items": items,
            })

        if not excluibles and not grupos:
            return None

        return {
            "id_producto": id_producto,
            "producto_nombre": producto.nombre,
            "ingredientes_excluibles": excluibles,
            "grupos": grupos,
        }

    # -----------------------------------------------------------------
    @staticmethod
    def comentario_de_personalizacion(id_producto, excluidos=None, opciones=None):
        """Texto legible para el carrito y el ticket, ej:

        "Sin cebolla encurtida · Chorizo criollo · Gallopinto · Tortillas"
        """
        excluidos = set(int(x) for x in (excluidos or []))
        opciones = [int(x) for x in (opciones or [])]
        partes = []

        if excluidos:
            nombres = [p.nombre for p in Producto.query.filter(Producto.id_producto.in_(excluidos)).all()]
            if nombres:
                partes.append("Sin " + ", ".join(nombres))

        if opciones:
            items = (
                RecetaOpcionItem.query.filter(RecetaOpcionItem.id_item.in_(opciones))
                .order_by(RecetaOpcionItem.orden)
                .all()
            )
            partes.extend(i.nombre for i in items)

        return " · ".join(partes) if partes else None

    # -----------------------------------------------------------------
    @staticmethod
    def requerimiento_de_venta(id_producto, cantidad, excluidos=None, opciones=None):
        """Cuanto inventario consume vender `cantidad` de `id_producto`.

        - Producto con receta -> consumo de cada insumo (escalado por
          rendimiento), sin los `excluidos` y sumando lo que agreguen las
          `opciones` elegidas.
        - Insumo o producto simple -> el propio producto.
        """
        cantidad = Decimal(str(cantidad))
        producto = Producto.query.get(id_producto)
        if not producto:
            return {id_producto: cantidad}

        if producto.es_receta:
            receta = Receta.query.filter_by(id_producto=id_producto, estado="activo").first()
            if receta and receta.ingredientes:
                excluidos = set(int(x) for x in (excluidos or []))
                rendimiento = Decimal(str(receta.rendimiento or 1))
                if rendimiento <= 0:
                    rendimiento = Decimal("1")
                requerido = {}
                for ing in receta.ingredientes:
                    if ing.opcional or ing.id_producto in excluidos:
                        continue
                    consumo = Decimal(str(ing.cantidad_necesaria)) * cantidad / rendimiento
                    requerido[ing.id_producto] = requerido.get(
                        ing.id_producto, Decimal("0")
                    ) + consumo

                if opciones:
                    ids_item = [int(x) for x in opciones]
                    items = RecetaOpcionItem.query.filter(RecetaOpcionItem.id_item.in_(ids_item)).all()
                    for it in items:
                        if not it.id_producto_insumo or not it.cantidad:
                            continue
                        consumo = Decimal(str(it.cantidad)) * cantidad / rendimiento
                        requerido[it.id_producto_insumo] = requerido.get(
                            it.id_producto_insumo, Decimal("0")
                        ) + consumo

                return requerido

        return {id_producto: cantidad}

    # -----------------------------------------------------------------
    @staticmethod
    def requerimiento_de_carrito(items):
        """items: lista de {id_producto, cantidad, excluidos?, opciones?}."""
        total = {}
        for it in items:
            parcial = RecetaService.requerimiento_de_venta(
                int(it["id_producto"]), it["cantidad"],
                excluidos=it.get("excluidos"), opciones=it.get("opciones"),
            )
            for pid, cant in parcial.items():
                total[pid] = total.get(pid, Decimal("0")) + cant
        return total

    # -----------------------------------------------------------------
    @staticmethod
    def descontar_ingredientes(id_producto, cantidad, usuario_id, referencia=None,
                                excluidos=None, opciones=None):
        """Descuenta del inventario lo que consume vender el producto."""
        from app.services.inventario_service import InventarioService

        requerimientos = RecetaService.requerimiento_de_venta(
            id_producto, cantidad, excluidos=excluidos, opciones=opciones
        )
        producto = Producto.query.get(id_producto)
        es_receta = bool(producto and producto.es_receta and len(requerimientos) > 0
                         and id_producto not in requerimientos)

        for pid, cant in requerimientos.items():
            InventarioService.mover(
                pid,
                -cant,
                "receta" if es_receta else "venta",
                usuario_id,
                referencia=referencia,
                observacion=(
                    "Consumo por receta de " + (producto.nombre if producto else "")
                    if es_receta
                    else "Venta directa"
                ),
                commit=False,
            )
        return requerimientos

    # -----------------------------------------------------------------
    @staticmethod
    def maximo_producible(id_producto):
        """Cuantas unidades del producto se pueden preparar con el stock actual."""
        from app.services.inventario_service import InventarioService

        producto = Producto.query.get(id_producto)
        if not producto:
            return 0
        if not producto.es_receta:
            return float(InventarioService.stock_de(id_producto))

        receta = Receta.query.filter_by(id_producto=id_producto, estado="activo").first()
        if not receta or not receta.ingredientes:
            return float(InventarioService.stock_de(id_producto))

        rendimiento = Decimal(str(receta.rendimiento or 1)) or Decimal("1")
        posibles = None
        for ing in receta.ingredientes:
            if ing.opcional:
                continue
            necesaria = Decimal(str(ing.cantidad_necesaria or 0))
            if necesaria <= 0:
                continue
            disponible = InventarioService.stock_de(ing.id_producto)
            cuantos = (disponible * rendimiento) / necesaria
            posibles = cuantos if posibles is None else min(posibles, cuantos)
        return float(posibles or 0)
