"""Control de existencias con registro de movimientos y encolado de sync."""
import logging
from decimal import Decimal

from flask import current_app

from app.extensions import db
from app.models.inventario import Inventario
from app.models.movimiento_inventario import MovimientoInventario
from app.models.producto import Producto
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("inventario")


class StockInsuficiente(Exception):
    def __init__(self, faltantes):
        self.faltantes = faltantes
        detalle = ", ".join(
            f"{f['producto']} (requiere {f['requerido']}, hay {f['disponible']})"
            for f in faltantes
        )
        super().__init__("Stock insuficiente: " + detalle)


class InventarioService:

    # -----------------------------------------------------------------
    @staticmethod
    def obtener_o_crear(id_producto):
        inv = Inventario.query.filter_by(id_producto=id_producto).first()
        if not inv:
            inv = Inventario(
                id_producto=id_producto,
                id_sucursal=current_app.config.get("ID_SUCURSAL", 1),
                stock_actual=0,
                stock_minimo=0,
                stock_maximo=0,
            )
            db.session.add(inv)
            db.session.flush()
        return inv

    # -----------------------------------------------------------------
    @staticmethod
    def stock_de(id_producto):
        inv = Inventario.query.filter_by(id_producto=id_producto).first()
        return Decimal(str(inv.stock_actual)) if inv and inv.stock_actual is not None else Decimal("0")

    # -----------------------------------------------------------------
    @staticmethod
    def verificar_disponibilidad(requerimientos):
        """requerimientos: dict {id_producto: cantidad}. Lanza StockInsuficiente."""
        faltantes = []
        for id_producto, cantidad in requerimientos.items():
            disponible = InventarioService.stock_de(id_producto)
            if disponible < Decimal(str(cantidad)):
                producto = Producto.query.get(id_producto)
                faltantes.append(
                    {
                        "id_producto": id_producto,
                        "producto": producto.nombre if producto else str(id_producto),
                        "requerido": float(cantidad),
                        "disponible": float(disponible),
                    }
                )
        if faltantes:
            raise StockInsuficiente(faltantes)
        return True

    # -----------------------------------------------------------------
    @staticmethod
    def mover(id_producto, cantidad, tipo_movimiento, usuario_id,
              referencia=None, observacion=None, encolar=True, commit=False):
        """Aplica un movimiento de stock. `cantidad` positiva = entrada."""
        from app.services.sync_service import SyncService

        inv = InventarioService.obtener_o_crear(id_producto)
        anterior = Decimal(str(inv.stock_actual or 0))
        delta = Decimal(str(cantidad))
        nuevo = anterior + delta

        inv.stock_actual = nuevo
        inv.fecha_actualizacion = nicaragua_now()
        inv.estado_sync = "pendiente"

        mov = MovimientoInventario(
            id_empresa=current_app.config.get("ID_EMPRESA", 1),
            id_sucursal=current_app.config.get("ID_SUCURSAL", 1),
            id_producto=id_producto,
            id_usuario=usuario_id,
            tipo_movimiento=tipo_movimiento,
            cantidad=abs(delta),
            stock_anterior=anterior,
            stock_nuevo=nuevo,
            referencia=referencia,
            observacion=observacion,
            fecha_movimiento=nicaragua_now(),
            timestamp_operacion=nicaragua_now(),
        )
        db.session.add(mov)
        db.session.flush()

        if encolar:
            SyncService.encolar(
                "movimientos_inventario",
                mov.id_movimiento,
                "INSERT",
                payload={
                    "id_movimiento": mov.id_movimiento,
                    "id_empresa": mov.id_empresa,
                    "id_sucursal": mov.id_sucursal,
                    "id_producto": mov.id_producto,
                    "id_usuario": mov.id_usuario,
                    "tipo_movimiento": mov.tipo_movimiento,
                    "cantidad": float(mov.cantidad),
                    "stock_anterior": float(mov.stock_anterior),
                    "stock_nuevo": float(mov.stock_nuevo),
                    "referencia": mov.referencia,
                    "observacion": mov.observacion,
                    "fecha_movimiento": mov.fecha_movimiento.strftime("%Y-%m-%d %H:%M:%S"),
                },
                usuario_id=usuario_id,
                commit=False,
            )
            SyncService.encolar(
                "inventario",
                inv.id_inventario,
                "UPDATE",
                payload={
                    "id_inventario": inv.id_inventario,
                    "id_producto": inv.id_producto,
                    "id_sucursal": inv.id_sucursal,
                    "stock_actual": float(inv.stock_actual),
                    "stock_minimo": float(inv.stock_minimo or 0),
                    "stock_maximo": float(inv.stock_maximo or 0),
                },
                usuario_id=usuario_id,
                commit=False,
            )

        if commit:
            db.session.commit()
        return mov

    # -----------------------------------------------------------------
    @staticmethod
    def revertir_venta(venta, motivo="Reversion de venta"):
        """Devuelve al stock todo lo que la venta habia descontado."""
        from app.services.receta_service import RecetaService

        for det in venta.detalles:
            requerimientos = RecetaService.requerimiento_de_venta(det.id_producto, det.cantidad)
            for id_producto, cantidad in requerimientos.items():
                InventarioService.mover(
                    id_producto,
                    cantidad,  # positivo = entrada
                    "devolucion",
                    venta.id_usuario,
                    referencia="VENTA-" + str(venta.id_venta),
                    observacion=motivo,
                    commit=False,
                )
        db.session.commit()

    # -----------------------------------------------------------------
    @staticmethod
    def productos_bajo_minimo():
        return (
            db.session.query(Inventario, Producto)
            .join(Producto, Producto.id_producto == Inventario.id_producto)
            .filter(Inventario.stock_actual <= Inventario.stock_minimo)
            .filter(Producto.estado == "activo")
            .all()
        )
