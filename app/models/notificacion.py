from app.extensions import db
from app.utils.date_utils import nicaragua_now


class Notificacion(db.Model):
    __tablename__ = "notificaciones"

    id_notificacion = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=False, default=1)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    titulo = db.Column(db.String(150), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.Enum("info", "warning", "success", "error"), default="info")
    leida = db.Column(db.Boolean, default=False)
    url_accion = db.Column(db.String(255))
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)

    def to_dict(self):
        return {
            "id_notificacion": self.id_notificacion,
            "id_usuario": self.id_usuario,
            "titulo": self.titulo,
            "mensaje": self.mensaje,
            "tipo": self.tipo,
            "leida": bool(self.leida),
            "url_accion": self.url_accion,
            "fecha_creacion": self.fecha_creacion.strftime("%Y-%m-%d %H:%M:%S")
            if self.fecha_creacion
            else None,
        }
