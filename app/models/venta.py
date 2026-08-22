from app.extensions import db
from datetime import datetime
from app.utils.date_utils import nicaragua_now

class Venta(db.Model):
    __tablename__ = 'ventas'

    id_venta = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=False)
    id_sucursal = db.Column(db.Integer, nullable=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=True)
    numero_venta = db.Column(db.String(50), nullable=True)
    subtotal = db.Column(db.Numeric(12, 2), default=0.0)
    descuento = db.Column(db.Numeric(12, 2), default=0.0)
    impuesto = db.Column(db.Numeric(12, 2), default=0.0)
    propina = db.Column(db.Numeric(12, 2), default=0.0)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    monto_recibido = db.Column(db.Numeric(12, 2), default=0.0)
    cambio = db.Column(db.Numeric(12, 2), default=0.0)
    estado = db.Column(db.Enum("completada", "anulada", "pendiente"), default="completada")
    metodo_pago = db.Column(db.String(50), default="Efectivo")
    fecha_venta = db.Column(db.DateTime, default=nicaragua_now)

    # --- Sincronizacion Local <-> Nube ---
    uuid_venta = db.Column(db.String(36), unique=True, index=True)
    origen = db.Column(db.Enum("local", "nube"), default="local")
    timestamp_local_creacion = db.Column(db.DateTime, default=nicaragua_now)
    timestamp_local_actualizacion = db.Column(db.DateTime, default=nicaragua_now, onupdate=nicaragua_now)
    estado_sync = db.Column(db.Enum("pendiente", "sinc_local", "sinc_remoto", "en_conflicto"), default="pendiente")
    motivo_anulacion = db.Column(db.String(255))

    # Relaciones
    detalles = db.relationship('DetalleVenta', backref='venta', lazy=True, cascade="all, delete-orphan")
    usuario = db.relationship('Usuario', lazy=True)
    cliente = db.relationship('Cliente', lazy=True)

    def to_dict(self):
        return {
            "id_venta": self.id_venta,
            "numero_venta": self.numero_venta,
            "subtotal": float(self.subtotal) if self.subtotal else 0.0,
            "descuento": float(self.descuento) if self.descuento else 0.0,
            "impuesto": float(self.impuesto) if self.impuesto else 0.0,
            "total": float(self.total) if self.total else 0.0,
            "estado": self.estado,
            "metodo_pago": self.metodo_pago,
            "fecha_venta": self.fecha_venta.strftime("%Y-%m-%d %H:%M:%S") if self.fecha_venta else "",
            "uuid_venta": self.uuid_venta,
            "estado_sync": self.estado_sync,
            "origen": self.origen,
            "motivo_anulacion": self.motivo_anulacion
        }
