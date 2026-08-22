from app.extensions import db

class Categoria(db.Model):
    __tablename__ = 'categorias'

    id_categoria = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255))
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime, default=db.func.current_timestamp())

    def to_dict(self):
        return {
            "id_categoria": self.id_categoria,
            "id_empresa": self.id_empresa,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "estado": self.estado
        }
