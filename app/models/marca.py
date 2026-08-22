from app.extensions import db
from datetime import datetime
from app.utils.date_utils import nicaragua_now

class Marca(db.Model):
    __tablename__ = 'marcas'

    id_marca = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=True)
    nombre = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)

    def to_dict(self):
        return {
            "id_marca": self.id_marca,
            "nombre": self.nombre,
            "estado": self.estado
        }
