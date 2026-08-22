from flask_login import UserMixin
from app.extensions import db


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id_usuario = db.Column(db.Integer, primary_key=True)

    id_empresa = db.Column(db.Integer, db.ForeignKey("empresas.id_empresa"), nullable=False)
    id_sucursal = db.Column(db.Integer, db.ForeignKey("sucursales.id_sucursal"))
    id_rol = db.Column(db.Integer, db.ForeignKey("roles.id_rol"), nullable=False)

    usuario = db.Column(db.String(80), nullable=False)
    nombre_completo = db.Column(db.String(150), nullable=False)
    correo = db.Column(db.String(100))
    telefono = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    imagen_url = db.Column(db.String(255))
    imagen_datos = db.Column(db.LargeBinary)
    imagen_mimetype = db.Column(db.String(50))
    estado = db.Column(db.Enum("activo", "inactivo", "bloqueado"), default="activo")
    ultimo_acceso = db.Column(db.DateTime)
    fecha_creacion = db.Column(db.DateTime)
    tema_preferido = db.Column(db.String(20), default="light")
    color_primario = db.Column(db.String(20), default="#0b5cff")

    codigo_temporal = db.Column(db.String(10), nullable=True)
    expiracion_codigo = db.Column(db.DateTime, nullable=True)

    # Recuperacion de contrasena por codigo de 6 digitos enviado al correo
    codigo_recuperacion = db.Column(db.String(6), nullable=True)
    codigo_expiry = db.Column(db.DateTime, nullable=True)
    estado_sync = db.Column(db.Enum("pendiente", "sinc_local", "sinc_remoto"), default="pendiente")

    empresa = db.relationship("Empresa", lazy=True)
    sucursal = db.relationship("Sucursal", lazy=True)
    rol = db.relationship("Rol", lazy=True)

    @property
    def rol_nombre(self):
        return (self.rol.nombre or "").strip().lower() if self.rol else ""

    def tiene_rol(self, *roles):
        return self.rol_nombre in [r.strip().lower() for r in roles]

    @property
    def es_admin(self):
        return self.rol_nombre in ("admin", "administrador")

    def get_id(self):
        return str(self.id_usuario)

    def to_dict(self):
        return {
            "id_usuario": self.id_usuario,
            "id_rol": self.id_rol,
            "usuario": self.usuario,
            "nombre_completo": self.nombre_completo,
            "correo": self.correo,
            "telefono": self.telefono,
            "imagen_url": self.imagen_url,
            "estado": self.estado,
            "rol": self.rol.nombre if self.rol else None
        }

class RecuperacionPassword(db.Model):
    __tablename__ = "recuperacion_password"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    codigo = db.Column(db.String(6), nullable=False)
    fecha_expiracion = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, default=False)
    
    usuario = db.relationship("Usuario", backref=db.backref("recuperaciones", lazy=True))