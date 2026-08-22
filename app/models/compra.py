from app.extensions import db
from datetime import datetime
from app.utils.date_utils import nicaragua_now

class Compra(db.Model):
    __tablename__ = 'compras'

    id_compra = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=False)
    id_sucursal = db.Column(db.Integer, nullable=False)
    id_usuario = db.Column(db.Integer, nullable=False)
    id_proveedor = db.Column(db.Integer, nullable=True)
    numero_compra = db.Column(db.String(50), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), default=0.0)
    impuesto = db.Column(db.Numeric(10, 2), default=0.0)
    total = db.Column(db.Numeric(10, 2), default=0.0)
    estado = db.Column(db.Enum('completada', 'cancelada'), default='completada')
    fecha_compra = db.Column(db.DateTime, default=nicaragua_now)
    tipo_compra = db.Column(db.Enum('productos', 'varios'), default='productos')
    descripcion_gasto = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            "id_compra": self.id_compra,
            "numero_compra": self.numero_compra,
            "subtotal": float(self.subtotal),
            "impuesto": float(self.impuesto),
            "total": float(self.total),
            "estado": self.estado,
            "fecha_compra": self.fecha_compra.strftime("%Y-%m-%d %H:%M:%S") if self.fecha_compra else "",
            "id_proveedor": self.id_proveedor,
            "tipo_compra": self.tipo_compra,
            "descripcion_gasto": self.descripcion_gasto
        }
