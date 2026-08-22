from app.extensions import db
from app.utils.date_utils import nicaragua_now


class MovimientoInventario(db.Model):
    __tablename__ = "movimientos_inventario"

    id_movimiento = db.Column(db.Integer, primary_key=True)
    id_empresa = db.Column(db.Integer, nullable=False, default=1)
    id_sucursal = db.Column(db.Integer, nullable=False, default=1)
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    tipo_movimiento = db.Column(
        db.Enum("entrada", "salida", "ajuste", "venta", "compra", "devolucion", "receta"),
        nullable=False,
    )
    cantidad = db.Column(db.Numeric(12, 2), nullable=False)
    stock_anterior = db.Column(db.Numeric(12, 2), nullable=False)
    stock_nuevo = db.Column(db.Numeric(12, 2), nullable=False)
    referencia = db.Column(db.String(100))
    observacion = db.Column(db.Text)
    fecha_movimiento = db.Column(db.DateTime, default=nicaragua_now)
    timestamp_operacion = db.Column(db.DateTime, default=nicaragua_now)
    estado_sync = db.Column(
        db.Enum("pendiente", "sinc_local", "sinc_remoto"), default="pendiente"
    )

    producto = db.relationship("Producto", lazy=True)

    def to_dict(self):
        return {
            "id_movimiento": self.id_movimiento,
            "id_producto": self.id_producto,
            "producto": self.producto.nombre if self.producto else None,
            "tipo_movimiento": self.tipo_movimiento,
            "cantidad": float(self.cantidad or 0),
            "stock_anterior": float(self.stock_anterior or 0),
            "stock_nuevo": float(self.stock_nuevo or 0),
            "referencia": self.referencia,
            "observacion": self.observacion,
            "fecha_movimiento": self.fecha_movimiento.strftime("%Y-%m-%d %H:%M:%S")
            if self.fecha_movimiento
            else None,
        }
