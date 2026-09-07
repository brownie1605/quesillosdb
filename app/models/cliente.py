from app.extensions import db
from datetime import datetime
from app.utils.date_utils import nicaragua_now

class Cliente(db.Model):
    __tablename__ = 'clientes'

    id_cliente = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=True)
    nombre = db.Column(db.String(150), nullable=False)
    cedula = db.Column(db.String(30))
    telefono = db.Column(db.String(30))
    direccion = db.Column(db.Text)
    # interno: personal/familia de la empresa. externo: cliente normal que paga.
    tipo_cliente = db.Column(db.Enum("interno", "externo"), default="externo", nullable=False)
    # Preferencial/VIP: para identificarlo en el dashboard de consumo y darle trato especial.
    es_preferencial = db.Column(db.Boolean, default=False, nullable=False)
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)

    def to_dict(self):
        return {
            "id_cliente": self.id_cliente,
            "nombre": self.nombre,
            "cedula": self.cedula,
            "telefono": self.telefono,
            "direccion": self.direccion,
            "tipo_cliente": self.tipo_cliente,
            "es_preferencial": self.es_preferencial,
            "estado": self.estado
        }
