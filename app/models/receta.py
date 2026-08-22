from app.extensions import db
from app.utils.date_utils import nicaragua_now


class Receta(db.Model):
    """Receta de un producto final: define los insumos que consume al venderse."""

    __tablename__ = "recetas"

    id_receta = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(
        db.Integer, db.ForeignKey("productos.id_producto"), nullable=False, unique=True
    )
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    modo_preparacion = db.Column(db.Text)
    tiempo_preparacion = db.Column(db.Integer)          # minutos
    rendimiento = db.Column(db.Numeric(12, 2), default=1)
    id_unidad_rendimiento = db.Column(db.Integer, db.ForeignKey("unidades_medida.id_unidad"))
    costo_total = db.Column(db.Numeric(12, 2), default=0)
    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    creado_por = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)
    fecha_actualizacion = db.Column(db.DateTime, default=nicaragua_now, onupdate=nicaragua_now)
    estado_sync = db.Column(
        db.Enum("pendiente", "sinc_local", "sinc_remoto"), default="pendiente"
    )

    producto = db.relationship("Producto", lazy="joined", foreign_keys=[id_producto])
    unidad_rendimiento = db.relationship("UnidadMedida", lazy=True)
    ingredientes = db.relationship(
        "RecetaIngrediente",
        backref="receta",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def to_dict(self, incluir_ingredientes=True):
        data = {
            "id_receta": self.id_receta,
            "id_producto": self.id_producto,
            "producto_nombre": self.producto.nombre if self.producto else None,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "modo_preparacion": self.modo_preparacion,
            "tiempo_preparacion": self.tiempo_preparacion,
            "rendimiento": float(self.rendimiento or 1),
            "id_unidad_rendimiento": self.id_unidad_rendimiento,
            "costo_total": float(self.costo_total or 0),
            "estado": self.estado,
            "fecha_creacion": self.fecha_creacion.strftime("%Y-%m-%d %H:%M:%S")
            if self.fecha_creacion
            else None,
        }
        if incluir_ingredientes:
            data["ingredientes"] = [i.to_dict() for i in self.ingredientes]
        return data


class RecetaIngrediente(db.Model):
    """Insumo consumido por una receta."""

    __tablename__ = "receta_ingredientes"

    id_ingrediente = db.Column(db.Integer, primary_key=True)
    id_receta = db.Column(
        db.Integer, db.ForeignKey("recetas.id_receta", ondelete="CASCADE"), nullable=False
    )
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False)
    cantidad_necesaria = db.Column(db.Numeric(12, 4), nullable=False)
    id_unidad = db.Column(db.Integer, db.ForeignKey("unidades_medida.id_unidad"))
    costo_estimado = db.Column(db.Numeric(12, 2), default=0)
    opcional = db.Column(db.Boolean, default=False)

    producto = db.relationship("Producto", lazy="joined")
    unidad = db.relationship("UnidadMedida", lazy="joined")

    __table_args__ = (
        db.UniqueConstraint("id_receta", "id_producto", name="uk_receta_ingrediente"),
    )

    def to_dict(self):
        return {
            "id_ingrediente": self.id_ingrediente,
            "id_receta": self.id_receta,
            "id_producto": self.id_producto,
            "producto_nombre": self.producto.nombre if self.producto else None,
            "cantidad_necesaria": float(self.cantidad_necesaria or 0),
            "id_unidad": self.id_unidad,
            "unidad": self.unidad.abreviatura if self.unidad else None,
            "costo_estimado": float(self.costo_estimado or 0),
            "opcional": bool(self.opcional),
        }
