from app.extensions import db


class Empresa(db.Model):
    __tablename__ = "empresas"

    id_empresa = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    ruc = db.Column(db.String(30))
    telefono = db.Column(db.String(30))
    correo = db.Column(db.String(100))
    direccion = db.Column(db.Text)
    logo_url = db.Column(db.String(255))
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime)