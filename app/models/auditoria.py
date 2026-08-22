from app.extensions import db
from datetime import datetime
from app.utils.date_utils import nicaragua_now

class Auditoria(db.Model):
    __tablename__ = "audit"

    id_audit = db.Column(db.BigInteger, primary_key=True)
    id_user = db.Column(db.String(20), nullable=True)
    action = db.Column(db.Enum('crear', 'update', 'delete', 'login', 'logout'), nullable=False)
    entity_affected = db.Column(db.String(100), nullable=False)
    id_reference = db.Column(db.String(64), nullable=True)
    date = db.Column(db.DateTime, default=nicaragua_now)
    ip = db.Column(db.String(45), nullable=True)
    device = db.Column(db.String(120), nullable=True)

    def to_dict(self):
        nombre_usuario = "Sistema"
        if self.id_user:
            from app.models.usuario import Usuario
            try:
                user_id_int = int(self.id_user)
                u = Usuario.query.get(user_id_int)
                if u:
                    nombre_usuario = u.usuario
            except:
                pass

        return {
            "id_auditoria": self.id_audit,
            "id_usuario": self.id_user,
            "accion": self.action,
            "modulo": self.entity_affected,
            "detalles": self.id_reference,
            "ip_address": self.ip,
            "fecha": self.date.strftime("%Y-%m-%d %H:%M:%S") if self.date else None,
            "nombre_usuario": nombre_usuario
        }
