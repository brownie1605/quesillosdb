from app.extensions import db
from datetime import datetime
from app.utils.date_utils import nicaragua_now

class Marca(db.Model):
    """Marca de un producto. Va ligada a un Proveedor: de quien viene esa marca."""

    __tablename__ = 'marcas'

    id_marca = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=True)
    nombre = db.Column(db.String(100), nullable=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey("proveedores.id_proveedor"), nullable=True)
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)

    proveedor = db.relationship("Proveedor", lazy="joined")

    def to_dict(self):
        return {
            "id_marca": self.id_marca,
            "nombre": self.nombre,
            "id_proveedor": self.id_proveedor,
            "proveedor_nombre": self.proveedor.nombre if self.proveedor else None,
            "estado": self.estado
        }
