from app.extensions import db


class Sucursal(db.Model):
    __tablename__ = "sucursales"

    id_sucursal = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, db.ForeignKey("empresas.id_empresa"), nullable=False)

    nombre = db.Column(db.String(150), nullable=False)
    telefono = db.Column(db.String(30))
    direccion = db.Column(db.Text)
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime)