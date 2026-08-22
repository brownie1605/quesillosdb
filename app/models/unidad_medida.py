from app.extensions import db

class UnidadMedida(db.Model):
    __tablename__ = 'unidades_medida'

    id_unidad = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    abreviatura = db.Column(db.String(10), nullable=False)
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")

    def to_dict(self):
        return {
            "id_unidad": self.id_unidad,
            "nombre": self.nombre,
            "abreviatura": self.abreviatura,
            "estado": self.estado
        }
