"""Vista de cocina: ordenes pendientes y disponibilidad de recetas."""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Venta, DetalleVenta, Producto, Receta
from app.services.receta_service import RecetaService
from app.services.inventario_service import InventarioService
from app.utils.decorators import require_roles
from app.utils.date_utils import nicaragua_now

cocina_bp = Blueprint("cocina", __name__, url_prefix="/cocina")


@cocina_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cocinero")


@cocina_bp.route("/")
@cocina_bp.route("/pendientes")
@login_required
def pendientes():
    return render_template("cocina/pendientes.html")


@cocina_bp.route("/api/pendientes", methods=["GET"])
@login_required
def api_pendientes():
    """Ventas en estado pendiente: lo que la cocina debe preparar."""
    ventas = (
        Venta.query.filter(Venta.estado == "pendiente")
        .order_by(Venta.fecha_venta.asc())
        .limit(100)
        .all()
    )
    salida = []
    for v in ventas:
        salida.append(
            {
                "id_venta": v.id_venta,
                "numero_venta": v.numero_venta,
                "fecha_venta": v.fecha_venta.strftime("%H:%M") if v.fecha_venta else "",
                "mesero": v.usuario.nombre_completo if v.usuario else None,
                "items": [d.to_dict() for d in v.detalles],
                "total": float(v.total or 0),
            }
        )
    return jsonify(salida)


@cocina_bp.route("/api/<int:id_venta>/listo", methods=["POST"])
@login_required
def api_marcar_listo(id_venta):
    from app.services.sync_service import SyncService

    venta = Venta.query.get_or_404(id_venta)
    venta.estado = "completada"
    venta.timestamp_local_actualizacion = nicaragua_now()
    venta.estado_sync = "pendiente"
    SyncService.encolar(
        "ventas", venta.id_venta, "UPDATE",
        payload={"id_venta": venta.id_venta, "estado": "completada"},
        usuario_id=current_user.id_usuario, commit=False,
    )
    db.session.commit()

    try:
        from app.extensions import socketio

        socketio.emit("orden_lista", {"id_venta": id_venta, "numero": venta.numero_venta})
    except Exception:  # noqa: BLE001
        pass

    return jsonify({"success": True, "message": "Orden marcada como lista"})


@cocina_bp.route("/api/disponibilidad", methods=["GET"])
@login_required
def api_disponibilidad():
    """Cuantas unidades se pueden preparar de cada receta con el stock actual."""
    recetas = Receta.query.filter_by(estado="activo").all()
    salida = []
    for r in recetas:
        maximo = RecetaService.maximo_producible(r.id_producto)
        faltantes = []
        for ing in r.ingredientes:
            stock = float(InventarioService.stock_de(ing.id_producto))
            if stock < float(ing.cantidad_necesaria or 0):
                faltantes.append(
                    {
                        "producto": ing.producto.nombre if ing.producto else "",
                        "necesita": float(ing.cantidad_necesaria or 0),
                        "hay": stock,
                    }
                )
        salida.append(
            {
                "id_receta": r.id_receta,
                "receta": r.nombre,
                "producto": r.producto.nombre if r.producto else "",
                "max_producible": maximo,
                "faltantes": faltantes,
            }
        )
    return jsonify(salida)
