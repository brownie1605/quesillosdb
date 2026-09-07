from app.extensions import db
from app.utils.date_utils import nicaragua_now


class Caja(db.Model):
    __tablename__ = "cajas"

    id_caja = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=False, default=1)
    id_sucursal = db.Column(db.Integer, nullable=False, default=1)
    nombre = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.Enum("activa", "inactiva"), default="activa")
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)


class AperturaCaja(db.Model):
    __tablename__ = "aperturas_caja"

    id_apertura = db.Column(db.Integer, primary_key=True)
    id_caja = db.Column(db.Integer, db.ForeignKey("cajas.id_caja"), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    monto_inicial = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    estado = db.Column(db.Enum("abierta", "cerrada"), default="abierta")
    fecha_apertura = db.Column(db.DateTime, default=nicaragua_now)

    caja = db.relationship("Caja", lazy=True)
    usuario = db.relationship("Usuario", lazy=True)


class MovimientoCaja(db.Model):
    __tablename__ = "movimientos_caja"

    id_movimiento_caja = db.Column(db.Integer, primary_key=True)
    id_apertura = db.Column(db.Integer, db.ForeignKey("aperturas_caja.id_apertura"), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    tipo_movimiento = db.Column(
        db.Enum("ingreso", "egreso", "venta", "retiro", "ajuste"), nullable=False
    )
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    descripcion = db.Column(db.Text)
    referencia = db.Column(db.String(100))
    fecha_movimiento = db.Column(db.DateTime, default=nicaragua_now)


class CierreCaja(db.Model):
    __tablename__ = "cierres_caja"

    id_cierre = db.Column(db.Integer, primary_key=True)
    id_apertura = db.Column(db.Integer, db.ForeignKey("aperturas_caja.id_apertura"), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    monto_inicial = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_ingresos = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_egresos = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_ventas = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    monto_esperado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    monto_real = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    diferencia = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    observacion = db.Column(db.Text)
    # Arqueo detallado: cuantas monedas/billetes de cada denominacion se
    # contaron (cordobas y dolares) -- ver CajaService.cerrar_turno. Queda
    # guardado tal cual para poder auditar despues como pidio finanzas.
    detalle_conteo = db.Column(db.JSON, nullable=True)
    tipo_cambio = db.Column(db.Numeric(10, 4), nullable=True)
    fecha_cierre = db.Column(db.DateTime, default=nicaragua_now)

    apertura = db.relationship("AperturaCaja", lazy=True)
