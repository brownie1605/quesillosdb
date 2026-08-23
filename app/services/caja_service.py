"""Apertura/cierre de turno de caja y movimientos de efectivo (gastos/ingresos)."""
from decimal import Decimal

from app.extensions import db
from app.models.caja import Caja, AperturaCaja, MovimientoCaja, CierreCaja
from app.models.venta import Venta
from app.utils.date_utils import nicaragua_now


class CajaError(Exception):
    pass


class CajaService:

    # -----------------------------------------------------------------
    @staticmethod
    def caja_principal():
        """Una sola caja para el local; se crea sola si no existe."""
        caja = Caja.query.filter_by(estado="activa").first()
        if not caja:
            caja = Caja(nombre="Caja principal", estado="activa")
            db.session.add(caja)
            db.session.commit()
        return caja

    # -----------------------------------------------------------------
    @staticmethod
    def apertura_actual():
        return AperturaCaja.query.filter_by(estado="abierta").order_by(
            AperturaCaja.fecha_apertura.desc()
        ).first()

    # -----------------------------------------------------------------
    @staticmethod
    def abrir_turno(usuario, monto_inicial):
        if CajaService.apertura_actual():
            raise CajaError("Ya hay un turno de caja abierto")
        caja = CajaService.caja_principal()
        apertura = AperturaCaja(
            id_caja=caja.id_caja,
            id_usuario=usuario.id_usuario,
            monto_inicial=Decimal(str(monto_inicial or 0)),
            estado="abierta",
            fecha_apertura=nicaragua_now(),
        )
        db.session.add(apertura)
        db.session.commit()
        return apertura

    # -----------------------------------------------------------------
    @staticmethod
    def registrar_movimiento(usuario, tipo_movimiento, monto, descripcion=None, referencia=None):
        apertura = CajaService.apertura_actual()
        if not apertura:
            raise CajaError("No hay un turno de caja abierto")
        mov = MovimientoCaja(
            id_apertura=apertura.id_apertura,
            id_usuario=usuario.id_usuario,
            tipo_movimiento=tipo_movimiento,
            monto=Decimal(str(monto)),
            descripcion=descripcion,
            referencia=referencia,
            fecha_movimiento=nicaragua_now(),
        )
        db.session.add(mov)
        db.session.commit()
        return mov

    # -----------------------------------------------------------------
    @staticmethod
    def resumen_turno(apertura):
        """Ventas y movimientos del turno, para mostrar antes de cerrar."""
        ventas = Venta.query.filter(
            Venta.estado == "completada",
            Venta.fecha_venta >= apertura.fecha_apertura,
        ).all()
        total_ventas = sum((Decimal(str(v.total or 0)) for v in ventas), Decimal("0"))

        movimientos = MovimientoCaja.query.filter_by(id_apertura=apertura.id_apertura).all()
        ingresos = sum(
            (m.monto for m in movimientos if m.tipo_movimiento in ("ingreso", "ajuste")),
            Decimal("0"),
        )
        egresos = sum(
            (m.monto for m in movimientos if m.tipo_movimiento in ("egreso", "retiro")),
            Decimal("0"),
        )

        efectivo = sum(
            (Decimal(str(v.total or 0)) for v in ventas if (v.metodo_pago or "").lower() == "efectivo"),
            Decimal("0"),
        )
        monto_esperado = Decimal(str(apertura.monto_inicial or 0)) + efectivo + ingresos - egresos

        return {
            "total_ventas": total_ventas,
            "cantidad_ventas": len(ventas),
            "total_ingresos": ingresos,
            "total_egresos": egresos,
            "efectivo_en_ventas": efectivo,
            "monto_esperado": monto_esperado,
            "movimientos": movimientos,
        }

    # -----------------------------------------------------------------
    @staticmethod
    def cerrar_turno(usuario, monto_real, observacion=None):
        apertura = CajaService.apertura_actual()
        if not apertura:
            raise CajaError("No hay un turno de caja abierto")

        resumen = CajaService.resumen_turno(apertura)
        monto_real = Decimal(str(monto_real or 0))
        diferencia = monto_real - resumen["monto_esperado"]

        cierre = CierreCaja(
            id_apertura=apertura.id_apertura,
            id_usuario=usuario.id_usuario,
            monto_inicial=apertura.monto_inicial,
            total_ingresos=resumen["total_ingresos"],
            total_egresos=resumen["total_egresos"],
            total_ventas=resumen["total_ventas"],
            monto_esperado=resumen["monto_esperado"],
            monto_real=monto_real,
            diferencia=diferencia,
            observacion=observacion,
            fecha_cierre=nicaragua_now(),
        )
        db.session.add(cierre)
        apertura.estado = "cerrada"
        db.session.commit()
        return cierre
