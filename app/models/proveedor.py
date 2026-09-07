from app.extensions import db
from datetime import datetime
from app.utils.date_utils import nicaragua_now

class Proveedor(db.Model):
    __tablename__ = 'proveedores'

    id_proveedor = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=True)
    nombre = db.Column(db.String(150), nullable=False)
    ruc = db.Column(db.String(20))
    telefono = db.Column(db.String(20))
    correo = db.Column(db.String(100))
    direccion = db.Column(db.String(255))
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)

    def to_dict(self):
        return {
            "id_proveedor": self.id_proveedor,
            "nombre": self.nombre,
            "ruc": self.ruc,
            "telefono": self.telefono,
            "correo": self.correo,
            "direccion": self.direccion,
            "estado": self.estado,
        }
