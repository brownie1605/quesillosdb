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
        order_by="RecetaIngrediente.id_ingrediente",
    )
    grupos_opciones = db.relationship(
        "RecetaOpcionGrupo",
        backref="receta",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="RecetaOpcionGrupo.orden, RecetaOpcionGrupo.id_grupo",
    )

    @property
    def tiene_personalizacion(self):
        """True si al vender este producto hay algo que preguntarle al cliente."""
        return bool(self.grupos_opciones) or any(i.excluible for i in self.ingredientes)

    def to_dict(self, incluir_ingredientes=True, incluir_opciones=True):
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
            "tiene_personalizacion": self.tiene_personalizacion,
            "fecha_creacion": self.fecha_creacion.strftime("%Y-%m-%d %H:%M:%S")
            if self.fecha_creacion
            else None,
        }
        if incluir_ingredientes:
            data["ingredientes"] = [i.to_dict() for i in self.ingredientes]
        if incluir_opciones:
            data["grupos_opciones"] = [g.to_dict() for g in self.grupos_opciones]
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
    # 'opcional': no se cuenta al calcular stock/maximo producible (guarnicion suelta).
    opcional = db.Column(db.Boolean, default=False)
    # 'excluible': se descuenta normalmente, pero el cliente puede pedir quitarlo
    # en una venta puntual (ej. "quesillo sin cebolla") sin tocar la receta.
    excluible = db.Column(db.Boolean, default=False)

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
            "excluible": bool(self.excluible),
        }


class RecetaOpcionGrupo(db.Model):
    """Grupo de opciones para elegir al vender (ej. "Proteina", "Acompañante").

    Cada grupo se muestra en el modal del POS como una lista de opciones de la
    que el cliente elige una sola. Si `obligatorio` es True el cajero/mesero
    debe elegir una antes de agregar el producto al carrito.
    """

    __tablename__ = "receta_opciones_grupo"

    id_grupo = db.Column(db.Integer, primary_key=True)
    id_receta = db.Column(
        db.Integer, db.ForeignKey("recetas.id_receta", ondelete="CASCADE"), nullable=False
    )
    nombre = db.Column(db.String(120), nullable=False)
    obligatorio = db.Column(db.Boolean, default=True)
    orden = db.Column(db.Integer, default=0)
    estado_sync = db.Column(
        db.Enum("pendiente", "sinc_local", "sinc_remoto"), default="pendiente"
    )

    items = db.relationship(
        "RecetaOpcionItem",
        backref="grupo",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="RecetaOpcionItem.orden, RecetaOpcionItem.id_item",
    )

    def to_dict(self):
        return {
            "id_grupo": self.id_grupo,
            "id_receta": self.id_receta,
            "nombre": self.nombre,
            "obligatorio": bool(self.obligatorio),
            "orden": self.orden,
            "items": [i.to_dict() for i in self.items],
        }


class RecetaOpcionItem(db.Model):
    """Una opcion dentro de un grupo (ej. "Chorizo criollo" dentro de "Proteina").

    `id_producto_insumo` es opcional: si se define, elegir esta opcion
    descuenta `cantidad` de ese insumo del inventario ademas de los
    ingredientes fijos de la receta.
    """

    __tablename__ = "receta_opciones_item"

    id_item = db.Column(db.Integer, primary_key=True)
    id_grupo = db.Column(
        db.Integer, db.ForeignKey("receta_opciones_grupo.id_grupo", ondelete="CASCADE"),
        nullable=False,
    )
    nombre = db.Column(db.String(120), nullable=False)
    id_producto_insumo = db.Column(db.Integer, db.ForeignKey("productos.id_producto"))
    cantidad = db.Column(db.Numeric(12, 4), default=0)
    es_default = db.Column(db.Boolean, default=False)
    orden = db.Column(db.Integer, default=0)
    estado_sync = db.Column(
        db.Enum("pendiente", "sinc_local", "sinc_remoto"), default="pendiente"
    )

    insumo = db.relationship("Producto", lazy="joined")

    def to_dict(self):
        return {
            "id_item": self.id_item,
            "id_grupo": self.id_grupo,
            "nombre": self.nombre,
            "id_producto_insumo": self.id_producto_insumo,
            "insumo_nombre": self.insumo.nombre if self.insumo else None,
            "cantidad": float(self.cantidad or 0),
            "es_default": bool(self.es_default),
            "orden": self.orden,
        }
