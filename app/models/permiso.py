from app.extensions import db


class Permiso(db.Model):
    __tablename__ = "permisos"

    id_permiso = db.Column(db.Integer, primary_key=True)
    modulo = db.Column(db.String(100), nullable=False)
    accion = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)

    @property
    def codigo(self):
        return f"{self.modulo}.{self.accion}"


class RolPermiso(db.Model):
    __tablename__ = "rol_permiso"

    id_rol_permiso = db.Column(db.Integer, primary_key=True)
    id_rol = db.Column(db.Integer, db.ForeignKey("roles.id_rol"), nullable=False)
    id_permiso = db.Column(db.Integer, db.ForeignKey("permisos.id_permiso"), nullable=False)
