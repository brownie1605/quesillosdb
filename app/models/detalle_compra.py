from app.extensions import db

class DetalleCompra(db.Model):
    __tablename__ = 'detalle_compras'

    id_detalle_compra = db.Column(db.Integer, primary_key=True)
    id_compra = db.Column(db.Integer, nullable=False)
    id_producto = db.Column(db.Integer, nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    def to_dict(self):
        return {
            "id_detalle_compra": self.id_detalle_compra,
            "id_compra": self.id_compra,
            "id_producto": self.id_producto,
            "cantidad": float(self.cantidad),
            "precio_unitario": float(self.precio_unitario),
            "subtotal": float(self.subtotal)
        }
