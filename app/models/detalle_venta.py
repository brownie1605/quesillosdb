from app.extensions import db
from app.utils.date_utils import nicaragua_now

class DetalleVenta(db.Model):
    __tablename__ = 'detalle_ventas'

    id_detalle_venta = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    cantidad = db.Column(db.Numeric(12, 2), nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)
    descuento = db.Column(db.Numeric(12, 2), default=0.0)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    consumio_receta = db.Column(db.Boolean, default=False)
    # Personalizacion elegida por el cliente (ingredientes quitados, opciones
    # de cada grupo) y su version en texto listo para mostrar en el carrito
    # y el ticket. Ej: {"excluidos": [12], "opciones": [45, 51]}
    personalizacion = db.Column(db.JSON)
    comentario = db.Column(db.String(500))
    timestamp_local_creacion = db.Column(db.DateTime, default=nicaragua_now)
    estado_sync = db.Column(db.Enum('pendiente', 'sinc_local', 'sinc_remoto'), default='pendiente')

    producto = db.relationship('Producto', lazy=True)

    def to_dict(self):
        return {
            'id_detalle_venta': self.id_detalle_venta,
            'id_venta': self.id_venta,
            'id_producto': self.id_producto,
            'producto': self.producto.nombre if self.producto else None,
            'cantidad': float(self.cantidad or 0),
            'precio_unitario': float(self.precio_unitario or 0),
            'descuento': float(self.descuento or 0),
            'subtotal': float(self.subtotal or 0),
            'consumio_receta': bool(self.consumio_receta),
            'comentario': self.comentario,
        }
