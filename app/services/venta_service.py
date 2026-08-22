"""Registro de ventas offline-first con descuento automatico de recetas."""
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


class VentaService:

    @staticmethod
    def numero_venta():
        return "V-" + nicaragua_now().strftime("%Y%m%d%H%M%S%f")[:20]

    # -----------------------------------------------------------------
    @staticmethod
    def registrar_venta(usuario, cart, metodo_pago="Efectivo", descuento=0.0,
                        propina=0.0, id_cliente=None, monto_recibido=0.0):
        """Registra la venta en la BD LOCAL y la encola para la nube.

        cart: [{id_producto, cantidad, precio}]
        Lanza StockInsuficiente si no alcanzan los insumos.
        """
        from app.services.sync_service import SyncService
        from app.services.network_service import NetworkService

        if not cart:
            raise ValueError("El carrito esta vacio")

        # 1. Consumo real de inventario (expande recetas a sus insumos).
        requerimientos = RecetaService.requerimiento_de_carrito(cart)
        InventarioService.verificar_disponibilidad(requerimientos)

        ahora = nicaragua_now()
        venta = Venta(
            id_empresa=usuario.id_empresa or current_app.config.get("ID_EMPRESA", 1),
            id_sucursal=usuario.id_sucursal or current_app.config.get("ID_SUCURSAL", 1),
            id_usuario=usuario.id_usuario,
            id_cliente=id_cliente or None,
            numero_venta=VentaService.numero_venta(),
            uuid_venta=str(uuid.uuid4()),
            descuento=Decimal(str(descuento or 0)),
            impuesto=Decimal("0"),
            propina=Decimal(str(propina or 0)),
            metodo_pago=metodo_pago,
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

        subtotal = Decimal("0")
        detalles_payload = []

        for item in cart:
            id_producto = int(item["id_producto"])
            cantidad = Decimal(str(item["cantidad"]))
            precio = Decimal(str(item["precio"]))
            sub_item = (cantidad * precio).quantize(Decimal("0.01"))
            subtotal += sub_item

            producto = Producto.query.get(id_producto)
            det = DetalleVenta(
                id_venta=venta.id_venta,
                id_producto=id_producto,
                cantidad=cantidad,
                precio_unitario=precio,
                descuento=Decimal("0"),
                subtotal=sub_item,
                consumio_receta=bool(producto and producto.es_receta),
                timestamp_local_creacion=ahora,
                estado_sync="pendiente",
            )
            db.session.add(det)
            db.session.flush()
            detalles_payload.append(det)

            # 2. Descuenta insumos (o el producto simple).
            RecetaService.descontar_ingredientes(
                id_producto, cantidad, usuario.id_usuario,
                referencia="VENTA-" + str(venta.id_venta),
            )

        venta.subtotal = subtotal
        venta.total = (subtotal - Decimal(str(descuento or 0)) + Decimal(str(propina or 0))).quantize(
            Decimal("0.01")
        )
        venta.cambio = max(Decimal("0"), Decimal(str(monto_recibido or 0)) - venta.total)

        # 3. Se encola solo (ver app/services/sync_events.py).
        db.session.commit()

        # 4. Si hay internet intenta subirla de inmediato (no bloquea la venta).
        if NetworkService.is_online():
            try:
                SyncService.push_pending_operations(limite=50)
            except Exception:  # noqa: BLE001
                log.warning("Push inmediato fallo; la venta queda en cola", exc_info=True)

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

        db.session.commit()
        return venta
