from app.extensions import db
from app.utils.date_utils import nicaragua_now


class Configuracion(db.Model):
    __tablename__ = "configuraciones"

    id_configuracion = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=False, default=1)
    clave = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.Text)
    descripcion = db.Column(db.Text)
    fecha_actualizacion = db.Column(db.DateTime, default=nicaragua_now, onupdate=nicaragua_now)

    __table_args__ = (db.UniqueConstraint("id_empresa", "clave", name="uk_config_empresa"),)
