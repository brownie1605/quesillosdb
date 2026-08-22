from app.extensions import db


class Rol(db.Model):
    __tablename__ = "roles"

    id_rol = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, db.ForeignKey("empresas.id_empresa"), nullable=False)

    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id_rol": self.id_rol,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "estado": self.estado
        }