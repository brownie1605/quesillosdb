from app.extensions import db
from app.utils.date_utils import nicaragua_now


class Mesa(db.Model):
    """Mesa del salon (o puesto de barra / 'para llevar').

    El flujo del negocio es: Mesas -> el mesero "atiende" una mesa libre,
    lo que abre una Venta en estado 'pendiente' ligada a esa mesa (una
    cuenta abierta). Se le van agregando productos mientras la mesa esta
    ocupada, y al final se "Cobra" -> la venta pasa a 'completada' y la
    mesa vuelve a quedar libre.
    """

    __tablename__ = "mesas"

    id_mesa = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, default=1)
    nombre = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.Enum("mesa", "barra", "llevar"), default="mesa")
    capacidad = db.Column(db.Integer, default=4)
    estado = db.Column(db.Enum("libre", "ocupada"), default="libre")
    id_venta_actual = db.Column(
        db.Integer, db.ForeignKey("ventas.id_venta", use_alter=True, name="fk_mesa_venta_actual"),
        nullable=True,
    )
    orden = db.Column(db.Integer, default=0)
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)
    estado_sync = db.Column(
        db.Enum("pendiente", "sinc_local", "sinc_remoto"), default="pendiente"
    )

    venta_actual = db.relationship("Venta", foreign_keys=[id_venta_actual], lazy=True)

    @property
    def icono(self):
        return {"mesa": "🍽️", "barra": "🍺", "llevar": "🥡"}.get(self.tipo, "🍽️")

    def to_dict(self):
        return {
            "id_mesa": self.id_mesa,
            "nombre": self.nombre,
            "tipo": self.tipo,
            "icono": self.icono,
            "capacidad": self.capacidad,
            "estado": self.estado,
            "id_venta_actual": self.id_venta_actual,
            "orden": self.orden,
        }
