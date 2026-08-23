"""Mesas del salon: libre <-> ocupada, ligada a la venta (cuenta) abierta."""
from app.extensions import db
from app.models.mesa import Mesa


class MesaError(Exception):
    pass


class MesaService:

    @staticmethod
    def listar():
        return Mesa.query.filter_by(activa=True).order_by(Mesa.orden, Mesa.id_mesa).all()

    # -----------------------------------------------------------------
    @staticmethod
    def liberar(id_mesa):
        mesa = Mesa.query.get(id_mesa)
        if not mesa:
            return None
        mesa.estado = "libre"
        mesa.id_venta_actual = None
        mesa.estado_sync = "pendiente"
        return mesa

    # -----------------------------------------------------------------
    @staticmethod
    def crear(nombre, tipo="mesa", capacidad=4, orden=None):
        if orden is None:
            ultimo = db.session.query(db.func.max(Mesa.orden)).scalar() or 0
            orden = ultimo + 1
        mesa = Mesa(nombre=nombre, tipo=tipo, capacidad=capacidad, orden=orden)
        db.session.add(mesa)
        db.session.commit()
        return mesa

    # -----------------------------------------------------------------
    @staticmethod
    def desactivar(id_mesa):
        mesa = Mesa.query.get(id_mesa)
        if not mesa:
            raise MesaError("Mesa no encontrada")
        if mesa.estado == "ocupada":
            raise MesaError("No se puede quitar una mesa ocupada")
        mesa.activa = False
        mesa.estado_sync = "pendiente"
        db.session.commit()
        return mesa
