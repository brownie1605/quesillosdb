"""Notificaciones del sistema: creacion centralizada (con push en vivo por
socketio) y los chequeos periodicos de stock bajo / pedidos demorados.

Todas las notificaciones que crea este servicio son "para todos" (
`id_usuario=None`), tal como se pidio: cualquier usuario logueado las ve en
la campanita, sin importar su rol.
"""
import logging
from datetime import timedelta

from app.extensions import db
from app.models import Notificacion, Producto, Inventario, Venta, Mesa
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("notificaciones")

UMBRAL_PEDIDO_MINUTOS = 20


class NotificacionService:

    # -----------------------------------------------------------------
    @staticmethod
    def crear(titulo, mensaje, tipo="info", id_usuario=None, url_accion=None, id_empresa=1):
        """Crea una notificacion y la empuja en vivo por socketio si hay
        alguien conectado. `id_usuario=None` = visible para todos."""
        n = Notificacion(
            id_empresa=id_empresa,
            id_usuario=id_usuario,
            titulo=titulo,
            mensaje=mensaje,
            tipo=tipo,
            url_accion=url_accion,
        )
        db.session.add(n)
        db.session.commit()

        try:
            from app.extensions import socketio

            socketio.emit(
                "notificacion",
                n.to_dict(),
                to=("usuario_" + str(id_usuario)) if id_usuario else None,
            )
        except Exception:  # noqa: BLE001
            pass
        return n

    # -----------------------------------------------------------------
    @staticmethod
    def _ya_avisado(url_accion):
        """True si ya existe una notificacion sin leer para esa misma
        referencia -- evita mandar el mismo aviso en cada corrida del job.
        Si alguien la marca leida y la situacion sigue igual, se vuelve a
        avisar en la siguiente revision (a proposito: no debe quedar
        silenciada para siempre)."""
        return (
            db.session.query(Notificacion.id_notificacion)
            .filter_by(url_accion=url_accion, leida=False)
            .first()
            is not None
        )

    # -----------------------------------------------------------------
    @staticmethod
    def revisar_stock_bajo():
        """Un aviso por producto bajo su stock minimo."""
        filas = (
            db.session.query(Producto, Inventario)
            .join(Inventario, Inventario.id_producto == Producto.id_producto)
            .filter(Producto.estado == "activo")
            .filter(Inventario.stock_actual <= Inventario.stock_minimo)
            .all()
        )
        creadas = 0
        for prod, inv in filas:
            url = f"/productos/?bajo_stock={prod.id_producto}"
            if NotificacionService._ya_avisado(url):
                continue
            NotificacionService.crear(
                titulo="📦 Stock bajo",
                mensaje=(
                    f'"{prod.nombre}" tiene {float(inv.stock_actual):g} unidades '
                    f'(mínimo {float(inv.stock_minimo):g}). Repón comprando en Compras.'
                ),
                tipo="warning",
                url_accion=url,
            )
            creadas += 1
        if creadas:
            log.info("Avisos de stock bajo creados: %s", creadas)
        return creadas

    # -----------------------------------------------------------------
    @staticmethod
    def revisar_pedidos_demorados():
        """Avisa si un pedido de mesa lleva abierto mas del umbral sin
        cerrarse (cuenta sin cobrar), para que alguien le de seguimiento."""
        limite = nicaragua_now() - timedelta(minutes=UMBRAL_PEDIDO_MINUTOS)
        ventas = (
            Venta.query.filter(Venta.estado == "pendiente")
            .filter(Venta.id_mesa.isnot(None))
            .filter(Venta.fecha_venta <= limite)
            .all()
        )
        creadas = 0
        for v in ventas:
            url = f"/mesas/{v.id_mesa}/pedido"
            if NotificacionService._ya_avisado(url):
                continue
            minutos = int((nicaragua_now() - v.fecha_venta).total_seconds() // 60)
            mesa = Mesa.query.get(v.id_mesa)
            nombre_mesa = mesa.nombre if mesa else f"Mesa #{v.id_mesa}"
            NotificacionService.crear(
                titulo="⏰ Pedido demorado",
                mensaje=f'El pedido de "{nombre_mesa}" lleva {minutos} min sin cerrarse.',
                tipo="warning",
                url_accion=url,
            )
            creadas += 1
        if creadas:
            log.info("Avisos de pedido demorado creados: %s", creadas)
        return creadas

    # -----------------------------------------------------------------
    @staticmethod
    def avisar_nuevo_pedido(id_mesa, usuario_nombre=None):
        """Se llama cuando se agregan productos a la cuenta de una mesa:
        avisa que hay algo nuevo para preparar."""
        mesa = Mesa.query.get(id_mesa)
        nombre_mesa = mesa.nombre if mesa else f"Mesa #{id_mesa}"
        quien = f" · pedido por {usuario_nombre}" if usuario_nombre else ""
        return NotificacionService.crear(
            titulo="🍳 Nuevo pedido para preparar",
            mensaje=f'{nombre_mesa}: se agregaron productos a la cuenta{quien}.',
            tipo="info",
            url_accion="/cocina/pendientes",
        )

    # -----------------------------------------------------------------
    @staticmethod
    def revisar_todo():
        """Corrida periodica completa (ver scheduler_service.py)."""
        total = 0
        total += NotificacionService.revisar_stock_bajo()
        total += NotificacionService.revisar_pedidos_demorados()
        return total
