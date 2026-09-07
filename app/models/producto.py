import re
import secrets

from sqlalchemy import LargeBinary, event
from sqlalchemy.dialects.mysql import LONGBLOB

from app.extensions import db

# Las imagenes superan los 64 KB de un BLOB normal.
LONGBLOB_MYSQL = LargeBinary().with_variant(LONGBLOB(), "mysql")
from app.utils.date_utils import nicaragua_now


class Producto(db.Model):
    """Producto del catalogo.

    tipo_producto define su rol en el negocio:
      - 'final'    : se vende al cliente. Puede tener receta (es_receta=True).
      - 'insumo'   : ingrediente de recetas Y TAMBIEN se vende directamente.
      - 'material' : no se vende (empaques, servilletas). Solo control de costo.
    """

    __tablename__ = "productos"

    id_producto = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=True)
    id_categoria = db.Column(db.Integer, nullable=True)
    id_proveedor = db.Column(db.Integer, db.ForeignKey("proveedores.id_proveedor"), nullable=True)
    id_unidad = db.Column(db.Integer, nullable=True)
    codigo = db.Column(db.String(80))
    codigo_barra = db.Column(db.String(100))
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    precio_compra = db.Column(db.Numeric(12, 2))
    precio_venta = db.Column(db.Numeric(12, 2), nullable=False)
    imagen_url = db.Column(db.String(255))
    imagen_datos = db.Column(LONGBLOB_MYSQL)
    imagen_mimetype = db.Column(db.String(50))
    aplica_impuesto = db.Column(db.Boolean, default=False)

    # --- Clasificacion para el modulo de recetas / insumos ---
    tipo_producto = db.Column(
        db.Enum("final", "insumo", "material"), default="final", nullable=False
    )
    es_receta = db.Column(db.Boolean, default=False)
    es_ingrediente_receta = db.Column(db.Boolean, default=False)
    se_vende = db.Column(db.Boolean, default=True)

    # A que impresora de cocina/barra sale este producto en la comanda.
    # NULL = no imprime en ninguna (ej. un material que no se vende).
    impresora = db.Column(db.Enum("quesillo", "cocina", "bebidas"), nullable=True)

    estado = db.Column(db.Enum("activo", "inactivo"), default="activo")
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)
    fecha_actualizacion = db.Column(db.DateTime, default=nicaragua_now, onupdate=nicaragua_now)
    estado_sync = db.Column(
        db.Enum("pendiente", "sinc_local", "sinc_remoto"), default="pendiente"
    )

    receta = db.relationship(
        "Receta",
        primaryjoin="Producto.id_producto==Receta.id_producto",
        foreign_keys="Receta.id_producto",
        uselist=False,
        lazy="select",
        viewonly=True,
    )

    @property
    def tipo_label(self):
        return {
            "final": "Producto final",
            "insumo": "Insumo",
            "material": "Material",
        }.get(self.tipo_producto, self.tipo_producto)

    def to_dict(self):
        return {
            "id_producto": self.id_producto,
            "id_categoria": self.id_categoria,
            "id_proveedor": self.id_proveedor,
            "impresora": self.impresora,
            "id_unidad": self.id_unidad,
            "codigo": self.codigo,
            "codigo_barra": self.codigo_barra,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "precio_compra": float(self.precio_compra) if self.precio_compra else 0.0,
            "precio_venta": float(self.precio_venta) if self.precio_venta else 0.0,
            "aplica_impuesto": self.aplica_impuesto,
            "tipo_producto": self.tipo_producto,
            "tipo_label": self.tipo_label,
            "es_receta": bool(self.es_receta),
            "es_ingrediente_receta": bool(self.es_ingrediente_receta),
            "se_vende": bool(self.se_vende),
            "estado": self.estado,
            "imagen_url": self.imagen_url or None,
        }


def _codigo_automatico(nombre):
    """Codigo legible a partir del nombre: 'Cebolla encurtida' -> 'CEB-40318'."""
    letras = re.sub(r"[^A-Za-z]", "", nombre or "")[:3].upper() or "PRD"
    return letras + "-" + str(secrets.randbelow(90000) + 10000)


@event.listens_for(Producto, "before_insert")
def _asignar_codigo(mapper, connection, target):
    """`codigo` es NOT NULL en la nube: nunca debe salir vacio de aqui."""
    if not (target.codigo or "").strip():
        target.codigo = _codigo_automatico(target.nombre)
