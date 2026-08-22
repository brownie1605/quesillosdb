"""Recetas: composicion de un producto final a partir de insumos.

Ejemplo del negocio:
    Quesillo = 2 tortillas + 0.25 L crema + 6 oz cebolla + 1 quesillo(insumo)

Al vender 1 Quesillo se descuentan automaticamente esos insumos del inventario.
Los insumos tambien pueden venderse solos (ej. "Tortilla docena"), en cuyo caso
se descuenta unicamente el insumo.
"""
import logging
from decimal import Decimal

from flask import current_app

from app.extensions import db
from app.models.producto import Producto
from app.models.receta import Receta, RecetaIngrediente
from app.models.inventario import Inventario
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("recetas")


class RecetaError(Exception):
    pass


class RecetaService:

    # =================================================================
    # CRUD
    # =================================================================
    @staticmethod
    def crear_receta(id_producto, datos, ingredientes, usuario_id):
        """ingredientes: lista de dicts {id_producto, cantidad_necesaria, id_unidad, opcional}."""
        from app.services.sync_service import SyncService

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

        producto.es_receta = True
        producto.tipo_producto = producto.tipo_producto or "final"
        producto.estado_sync = "pendiente"

        receta.costo_total = RecetaService.calcular_costo_receta(receta)
        db.session.flush()

        RecetaService._encolar(receta, usuario_id, "INSERT")
        db.session.commit()
        log.info("Receta creada para producto %s", id_producto)
        return receta

    # -----------------------------------------------------------------
    @staticmethod
    def actualizar_receta(id_receta, datos, ingredientes, usuario_id):
        from app.services.sync_service import SyncService

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

        receta.costo_total = RecetaService.calcular_costo_receta(receta)
        db.session.flush()

        RecetaService._encolar(receta, usuario_id, "UPDATE")
        db.session.commit()
        return receta

    # -----------------------------------------------------------------
    @staticmethod
    def eliminar_receta(id_receta, usuario_id):
        from app.services.sync_service import SyncService

        receta = Receta.query.get(id_receta)
        if not receta:
            raise RecetaError("Receta no encontrada")
        id_producto = receta.id_producto
        db.session.delete(receta)

        producto = Producto.query.get(id_producto)
        if producto:
            producto.es_receta = False
            producto.estado_sync = "pendiente"

        SyncService.encolar("recetas", id_receta, "DELETE", usuario_id=usuario_id, commit=False)
        db.session.commit()
        return True

    # -----------------------------------------------------------------
    @staticmethod
    def _reemplazar_ingredientes(receta, ingredientes):
        RecetaIngrediente.query.filter_by(id_receta=receta.id_receta).delete()
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
                )
            )

            # Marca el insumo como utilizable en recetas.
            if not insumo.es_ingrediente_receta:
                insumo.es_ingrediente_receta = True
                insumo.estado_sync = "pendiente"
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
    def requerimiento_de_venta(id_producto, cantidad):
        """Cuanto inventario consume vender `cantidad` de `id_producto`.

        - Producto con receta -> consumo de cada insumo (escalado por rendimiento).
        - Insumo o producto simple -> el propio producto.
        """
        cantidad = Decimal(str(cantidad))
        producto = Producto.query.get(id_producto)
        if not producto:
            return {id_producto: cantidad}

        if producto.es_receta:
            receta = Receta.query.filter_by(id_producto=id_producto, estado="activo").first()
            if receta and receta.ingredientes:
                rendimiento = Decimal(str(receta.rendimiento or 1))
                if rendimiento <= 0:
                    rendimiento = Decimal("1")
                requerido = {}
                for ing in receta.ingredientes:
                    if ing.opcional:
                        continue
                    consumo = Decimal(str(ing.cantidad_necesaria)) * cantidad / rendimiento
                    requerido[ing.id_producto] = requerido.get(
                        ing.id_producto, Decimal("0")
                    ) + consumo
                return requerido

        return {id_producto: cantidad}

    # -----------------------------------------------------------------
    @staticmethod
    def requerimiento_de_carrito(items):
        """items: lista de {id_producto, cantidad}. Devuelve consumo agregado."""
        total = {}
        for it in items:
            parcial = RecetaService.requerimiento_de_venta(
                int(it["id_producto"]), it["cantidad"]
            )
            for pid, cant in parcial.items():
                total[pid] = total.get(pid, Decimal("0")) + cant
        return total

    # -----------------------------------------------------------------
    @staticmethod
    def descontar_ingredientes(id_producto, cantidad, usuario_id, referencia=None):
        """Descuenta del inventario lo que consume vender el producto."""
        from app.services.inventario_service import InventarioService

        requerimientos = RecetaService.requerimiento_de_venta(id_producto, cantidad)
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

    # -----------------------------------------------------------------
    @staticmethod
    def _encolar(receta, usuario_id, operacion):
        from app.services.sync_service import SyncService

        SyncService.encolar(
            "recetas",
            receta.id_receta,
            operacion,
            payload={
                "id_receta": receta.id_receta,
                "id_producto": receta.id_producto,
                "nombre": receta.nombre,
                "descripcion": receta.descripcion,
                "modo_preparacion": receta.modo_preparacion,
                "tiempo_preparacion": receta.tiempo_preparacion,
                "rendimiento": float(receta.rendimiento or 1),
                "id_unidad_rendimiento": receta.id_unidad_rendimiento,
                "costo_total": float(receta.costo_total or 0),
                "estado": receta.estado,
                "creado_por": receta.creado_por,
            },
            usuario_id=usuario_id,
            commit=False,
        )
        for ing in receta.ingredientes:
            SyncService.encolar(
                "receta_ingredientes",
                ing.id_ingrediente,
                "INSERT",
                payload={
                    "id_ingrediente": ing.id_ingrediente,
                    "id_receta": ing.id_receta,
                    "id_producto": ing.id_producto,
                    "cantidad_necesaria": float(ing.cantidad_necesaria),
                    "id_unidad": ing.id_unidad,
                    "costo_estimado": float(ing.costo_estimado or 0),
                    "opcional": bool(ing.opcional),
                },
                usuario_id=usuario_id,
                commit=False,
            )

        SyncService.encolar(
            "productos",
            receta.id_producto,
            "UPDATE",
            payload={"id_producto": receta.id_producto, "es_receta": True},
            usuario_id=usuario_id,
            commit=False,
        )
