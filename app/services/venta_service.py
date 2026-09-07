"""Registro de ventas offline-first con descuento automatico de recetas.

Dos flujos de venta:
  - Directa (mostrador/barra): `registrar_venta()` cobra de una vez.
  - Por mesa (salon): `abrir_mesa()` crea una cuenta abierta (estado
    'pendiente') a la que se le van agregando productos con
    `agregar_items()`/`quitar_item()` mientras el cliente esta en la mesa,
    y se cierra con `cobrar_mesa()` cuando se paga.
"""
import uuid
import logging
from decimal import Decimal

from flask import current_app

from app.extensions import db
from app.models.venta import Venta
from app.models.detalle_venta import DetalleVenta
from app.models.producto import Producto
from app.services.receta_service import RecetaService
from app.services.inventario_service import InventarioService, StockInsuficiente
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("ventas")


class VentaError(Exception):
    pass


class VentaService:

    @staticmethod
    def numero_venta():
        return "V-" + nicaragua_now().strftime("%Y%m%d%H%M%S%f")[:20]

    # -----------------------------------------------------------------
    @staticmethod
    def _crear_detalle(venta, item, usuario, ahora):
        """Agrega una linea al carrito de `venta` y descuenta inventario.

        Devuelve el subtotal de esa linea. Usado tanto por la venta directa
        como por el flujo de mesas para no duplicar la logica.
        """
        id_producto = int(item["id_producto"])
        cantidad = Decimal(str(item["cantidad"]))
        precio = Decimal(str(item["precio"]))
        sub_item = (cantidad * precio).quantize(Decimal("0.01"))

        producto = Producto.query.get(id_producto)
        excluidos = item.get("excluidos") or []
        opciones = item.get("opciones") or []
        comentario = item.get("comentario") or RecetaService.comentario_de_personalizacion(
            id_producto, excluidos, opciones
        )

        det = DetalleVenta(
            id_venta=venta.id_venta,
            id_producto=id_producto,
            cantidad=cantidad,
            precio_unitario=precio,
            descuento=Decimal("0"),
            subtotal=sub_item,
            consumio_receta=bool(producto and producto.es_receta),
            personalizacion={"excluidos": excluidos, "opciones": opciones}
            if (excluidos or opciones) else None,
            comentario=comentario,
            timestamp_local_creacion=ahora,
            estado_sync="pendiente",
        )
        db.session.add(det)
        db.session.flush()

        RecetaService.descontar_ingredientes(
            id_producto, cantidad, usuario.id_usuario,
            referencia="VENTA-" + str(venta.id_venta),
            excluidos=excluidos, opciones=opciones,
        )
        return sub_item

    # -----------------------------------------------------------------
    @staticmethod
    def _recalcular_totales(venta):
        subtotal = sum((d.subtotal for d in venta.detalles), Decimal("0"))
        venta.subtotal = subtotal
        venta.total = (
            subtotal - Decimal(str(venta.descuento or 0)) + Decimal(str(venta.propina or 0))
        ).quantize(Decimal("0.01"))
        venta.cambio = max(Decimal("0"), Decimal(str(venta.monto_recibido or 0)) - venta.total)

    # -----------------------------------------------------------------
    @staticmethod
    def _exigir_caja_abierta():
        """Sin turno de caja abierto no se puede completar ninguna venta."""
        from app.services.caja_service import CajaService, CajaError

        try:
            CajaService.exigir_abierta()
        except CajaError as e:
            raise VentaError(str(e))

    # -----------------------------------------------------------------
    @staticmethod
    def _push_si_hay_internet():
        from app.services.sync_service import SyncService
        from app.services.network_service import NetworkService

        if NetworkService.is_online():
            try:
                SyncService.push_pending_operations(limite=50)
            except Exception:  # noqa: BLE001
                log.warning("Push inmediato fallo; queda en cola", exc_info=True)

    # =================================================================
    # VENTA DIRECTA (mostrador / barra)
    # =================================================================
    @staticmethod
    def registrar_venta(usuario, cart, metodo_pago="Efectivo", descuento=0.0,
                        propina=0.0, id_cliente=None, monto_recibido=0.0, id_mesa=None,
                        notas=None):
        """Registra la venta en la BD LOCAL y la encola para la nube.

        cart: [{id_producto, cantidad, precio, excluidos?, opciones?}]
        `excluidos`: ids de ingredientes de la receta que el cliente pidio quitar.
        `opciones`: ids de RecetaOpcionItem elegidos (uno por grupo).
        Lanza StockInsuficiente si no alcanzan los insumos.
        """
        if not cart:
            raise ValueError("El carrito esta vacio")

        VentaService._exigir_caja_abierta()

        # 1. Consumo real de inventario (expande recetas a sus insumos).
        requerimientos = RecetaService.requerimiento_de_carrito(cart)
        InventarioService.verificar_disponibilidad(requerimientos)

        ahora = nicaragua_now()
        venta = Venta(
            id_empresa=usuario.id_empresa or current_app.config.get("ID_EMPRESA", 1),
            id_sucursal=usuario.id_sucursal or current_app.config.get("ID_SUCURSAL", 1),
            id_usuario=usuario.id_usuario,
            id_cliente=id_cliente or None,
            id_mesa=id_mesa,
            numero_venta=VentaService.numero_venta(),
            uuid_venta=str(uuid.uuid4()),
            descuento=Decimal(str(descuento or 0)),
            impuesto=Decimal("0"),
            propina=Decimal(str(propina or 0)),
            metodo_pago=metodo_pago,
            notas=(notas or "").strip() or None,
            estado="completada",
            total=Decimal("0"),
            subtotal=Decimal("0"),
            monto_recibido=Decimal(str(monto_recibido or 0)),
            fecha_venta=ahora,
            timestamp_local_creacion=ahora,
            timestamp_local_actualizacion=ahora,
            origen="local",
            estado_sync="pendiente",
        )
        db.session.add(venta)
        db.session.flush()

        for item in cart:
            VentaService._crear_detalle(venta, item, usuario, ahora)

        VentaService._recalcular_totales(venta)

        # 3. Se encola solo (ver app/services/sync_events.py).
        db.session.commit()

        # 4. Si hay internet intenta subirla de inmediato (no bloquea la venta).
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def anular_venta(id_venta, usuario, motivo="Anulada por el usuario"):
        venta = Venta.query.get(id_venta)
        if not venta:
            raise ValueError("Venta no encontrada")
        if venta.estado == "anulada":
            return venta

        venta.estado = "anulada"
        venta.motivo_anulacion = motivo
        venta.estado_sync = "pendiente"
        venta.timestamp_local_actualizacion = nicaragua_now()

        InventarioService.revertir_venta(venta, motivo=motivo)

        if venta.id_mesa:
            from app.services.mesa_service import MesaService
            MesaService.liberar(venta.id_mesa)

        db.session.commit()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def editar_datos_venta(id_venta, id_cliente=None, metodo_pago=None, notas=None):
        """Corrige datos NO financieros de una factura ya cobrada: a quien
        se le vendio, el metodo/banco de pago (ej. el cajero marco el banco
        equivocado) y la nota de la factura (ej. para dejar por escrito el
        motivo de un descuento). A proposito NO toca productos, cantidades
        ni totales
        -- esos alimentan los reportes de ganancias y el kardex, y una
        factura cerrada no deberia poder reescribirlos silenciosamente.
        Para corregir un monto real, la venta se anula y se rehace.

        Devuelve (venta, cambios) con `cambios` como lista de strings
        legibles para dejar en la auditoria.
        """
        from app.models.cliente import Cliente

        venta = Venta.query.get(id_venta)
        if not venta:
            raise VentaError("Venta no encontrada")
        if venta.estado != "completada":
            raise VentaError("Solo se pueden editar ventas completadas (no pendientes ni anuladas)")

        cambios = []

        if id_cliente is not None:
            nuevo_id = int(id_cliente) if id_cliente else None
            if nuevo_id != venta.id_cliente:
                nombre_anterior = "Público general"
                if venta.id_cliente:
                    c = Cliente.query.get(venta.id_cliente)
                    nombre_anterior = c.nombre if c else "Público general"

                nombre_nuevo = "Público general"
                if nuevo_id:
                    c = Cliente.query.get(nuevo_id)
                    if not c:
                        raise VentaError("El cliente seleccionado no existe")
                    nombre_nuevo = c.nombre

                venta.id_cliente = nuevo_id
                cambios.append(f"Cliente: {nombre_anterior} -> {nombre_nuevo}")

        if metodo_pago is not None:
            metodo_pago = metodo_pago.strip()
            if metodo_pago and metodo_pago != venta.metodo_pago:
                cambios.append(f"Método de pago: {venta.metodo_pago} -> {metodo_pago}")
                venta.metodo_pago = metodo_pago

        if notas is not None:
            notas_nuevas = notas.strip() or None
            if notas_nuevas != venta.notas:
                cambios.append("Nota de la factura actualizada")
                venta.notas = notas_nuevas

        if not cambios:
            return venta, cambios

        venta.estado_sync = "pendiente"
        venta.timestamp_local_actualizacion = nicaragua_now()
        db.session.commit()
        return venta, cambios

    # =================================================================
    # FLUJO DE MESAS (cuenta abierta)
    # =================================================================
    @staticmethod
    def abrir_mesa(mesa, usuario, cart=None):
        """Abre una cuenta (venta 'pendiente') ligada a `mesa`."""
        cart = cart or []
        if mesa.estado == "ocupada" and mesa.id_venta_actual:
            raise VentaError("Esa mesa ya esta ocupada")

        if cart:
            requerimientos = RecetaService.requerimiento_de_carrito(cart)
            InventarioService.verificar_disponibilidad(requerimientos)

        ahora = nicaragua_now()
        venta = Venta(
            id_empresa=usuario.id_empresa or current_app.config.get("ID_EMPRESA", 1),
            id_sucursal=usuario.id_sucursal or current_app.config.get("ID_SUCURSAL", 1),
            id_usuario=usuario.id_usuario,
            id_mesa=mesa.id_mesa,
            numero_venta=VentaService.numero_venta(),
            uuid_venta=str(uuid.uuid4()),
            descuento=Decimal("0"),
            impuesto=Decimal("0"),
            propina=Decimal("0"),
            metodo_pago="Efectivo",
            estado="pendiente",
            total=Decimal("0"),
            subtotal=Decimal("0"),
            fecha_venta=ahora,
            timestamp_local_creacion=ahora,
            timestamp_local_actualizacion=ahora,
            origen="local",
            estado_sync="pendiente",
        )
        db.session.add(venta)
        db.session.flush()

        for item in cart:
            VentaService._crear_detalle(venta, item, usuario, ahora)
        VentaService._recalcular_totales(venta)

        mesa.estado = "ocupada"
        mesa.id_venta_actual = venta.id_venta
        mesa.estado_sync = "pendiente"

        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def agregar_items(venta, items, usuario):
        """Agrega productos a una cuenta abierta ya existente."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")
        if not items:
            return venta

        requerimientos = RecetaService.requerimiento_de_carrito(items)
        InventarioService.verificar_disponibilidad(requerimientos)

        ahora = nicaragua_now()
        for item in items:
            VentaService._crear_detalle(venta, item, usuario, ahora)

        VentaService._recalcular_totales(venta)
        venta.timestamp_local_actualizacion = ahora
        venta.estado_sync = "pendiente"
        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def quitar_item(venta, id_detalle, usuario):
        """Quita una linea de una cuenta abierta y revierte su inventario."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")

        det = DetalleVenta.query.get(id_detalle)
        if not det or det.id_venta != venta.id_venta:
            raise VentaError("Ese producto no esta en la cuenta")

        personalizacion = det.personalizacion or {}
        requerimientos = RecetaService.requerimiento_de_venta(
            det.id_producto, det.cantidad,
            excluidos=personalizacion.get("excluidos"),
            opciones=personalizacion.get("opciones"),
        )
        for pid, cant in requerimientos.items():
            InventarioService.mover(
                pid, cant, "ajuste", usuario.id_usuario,
                referencia="VENTA-" + str(venta.id_venta),
                observacion="Se quito de la cuenta antes de cobrar", commit=False,
            )

        # `venta.detalles.remove()` (no session.delete() directo) para que la
        # coleccion en memoria quede al dia de inmediato: _recalcular_totales
        # suma sobre `venta.detalles`, y el cascade delete-orphan se encarga
        # de borrar la fila.
        venta.detalles.remove(det)
        db.session.flush()

        VentaService._recalcular_totales(venta)
        venta.timestamp_local_actualizacion = nicaragua_now()
        venta.estado_sync = "pendiente"
        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta

    # -----------------------------------------------------------------
    @staticmethod
    def cobrar_mesa(venta, usuario, metodo_pago="Efectivo", descuento=0.0,
                    propina=0.0, monto_recibido=0.0, id_cliente=None, notas=None):
        """Cierra la cuenta de una mesa: cobra y libera la mesa."""
        if venta.estado != "pendiente":
            raise VentaError("Esta cuenta ya fue cobrada o anulada")
        if not venta.detalles:
            raise VentaError("La cuenta esta vacia")

        VentaService._exigir_caja_abierta()

        venta.descuento = Decimal(str(descuento or 0))
        venta.propina = Decimal(str(propina or 0))
        venta.metodo_pago = metodo_pago
        venta.monto_recibido = Decimal(str(monto_recibido or 0))
        venta.id_cliente = id_cliente or venta.id_cliente
        if notas is not None:
            venta.notas = (notas or "").strip() or None
        venta.estado = "completada"
        venta.timestamp_local_actualizacion = nicaragua_now()
        venta.estado_sync = "pendiente"

        VentaService._recalcular_totales(venta)

        if venta.id_mesa:
            from app.services.mesa_service import MesaService
            MesaService.liberar(venta.id_mesa)

        db.session.commit()
        VentaService._push_si_hay_internet()
        return venta
