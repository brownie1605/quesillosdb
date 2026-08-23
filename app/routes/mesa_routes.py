"""Mesas: Mesas -> Pedido (cuenta abierta) -> Cobrar."""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Mesa, Venta, DetalleVenta
from app.services.mesa_service import MesaService, MesaError
from app.services.venta_service import VentaService, VentaError
from app.services.inventario_service import StockInsuficiente
from app.services.auditoria_service import registrar_auditoria
from app.utils.decorators import require_roles, usuario_tiene_rol

mesa_bp = Blueprint("mesa", __name__, url_prefix="/mesas")


@mesa_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cajero", "Mesero")


# ---------------------------------------------------------------- vistas
@mesa_bp.route("/")
@login_required
def lista():
    mesas = MesaService.listar()
    return render_template(
        "mesas/lista.html",
        mesas=[m for m in mesas if m.tipo == "mesa"],
        para_llevar=[m for m in mesas if m.tipo == "llevar"],
        barra=[m for m in mesas if m.tipo == "barra"],
    )


@mesa_bp.route("/<int:id_mesa>/pedido")
@login_required
def pedido(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    return render_template("mesas/pedido.html", mesa=mesa)


# ---------------------------------------------------------------- API
@mesa_bp.route("/api/<int:id_mesa>/atender", methods=["POST"])
@login_required
def api_atender(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    try:
        venta = VentaService.abrir_mesa(mesa, current_user, cart=[])
        registrar_auditoria("ATENDER MESA", "Mesas", {"mesa": mesa.nombre, "venta": venta.id_venta})
        return jsonify({"success": True, "id_venta": venta.id_venta})
    except (MesaError, VentaError) as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/<int:id_mesa>/cuenta", methods=["GET"])
@login_required
def api_cuenta(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    if not mesa.id_venta_actual:
        return jsonify({"mesa": mesa.to_dict(), "venta": None, "detalles": []})

    venta = Venta.query.get(mesa.id_venta_actual)
    detalles = [d.to_dict() for d in venta.detalles] if venta else []
    return jsonify({
        "mesa": mesa.to_dict(),
        "venta": venta.to_dict() if venta else None,
        "detalles": detalles,
    })


@mesa_bp.route("/api/<int:id_mesa>/agregar", methods=["POST"])
@login_required
def api_agregar(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"success": False, "message": "No hay productos que agregar"}), 400

    try:
        if not mesa.id_venta_actual:
            venta = VentaService.abrir_mesa(mesa, current_user, cart=items)
        else:
            venta = Venta.query.get(mesa.id_venta_actual)
            venta = VentaService.agregar_items(venta, items, current_user)
        return jsonify({"success": True, "venta": venta.to_dict()})
    except StockInsuficiente as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e), "faltantes": e.faltantes}), 409
    except (MesaError, VentaError) as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/<int:id_mesa>/quitar/<int:id_detalle>", methods=["DELETE", "POST"])
@login_required
def api_quitar_item(id_mesa, id_detalle):
    mesa = Mesa.query.get_or_404(id_mesa)
    if not mesa.id_venta_actual:
        return jsonify({"success": False, "message": "Esta mesa no tiene una cuenta abierta"}), 400
    venta = Venta.query.get(mesa.id_venta_actual)
    try:
        venta = VentaService.quitar_item(venta, id_detalle, current_user)
        return jsonify({"success": True, "venta": venta.to_dict()})
    except VentaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400


@mesa_bp.route("/api/<int:id_mesa>/cobrar", methods=["POST"])
@login_required
def api_cobrar(id_mesa):
    mesa = Mesa.query.get_or_404(id_mesa)
    if not mesa.id_venta_actual:
        return jsonify({"success": False, "message": "Esta mesa no tiene una cuenta abierta"}), 400

    data = request.get_json(silent=True) or {}
    venta = Venta.query.get(mesa.id_venta_actual)
    try:
        venta = VentaService.cobrar_mesa(
            venta, current_user,
            metodo_pago=data.get("metodo_pago", "Efectivo"),
            descuento=float(data.get("descuento", 0.0) or 0),
            propina=float(data.get("propina", 0.0) or 0),
            monto_recibido=float(data.get("monto_recibido", 0.0) or 0),
            id_cliente=data.get("id_cliente"),
        )
        registrar_auditoria(
            "COBRAR MESA", "Mesas",
            {"mesa": mesa.nombre, "venta": venta.id_venta, "total": float(venta.total)},
        )
        return jsonify({
            "success": True, "venta_id": venta.id_venta,
            "numero_venta": venta.numero_venta, "total": float(venta.total),
            "cambio": float(venta.cambio or 0),
        })
    except VentaError as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@mesa_bp.route("/api/gestion", methods=["GET"])
@login_required
def api_gestion():
    """Listado simple para el admin (crear/desactivar mesas)."""
    return jsonify([m.to_dict() for m in Mesa.query.order_by(Mesa.orden).all()])


@mesa_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    if not usuario_tiene_rol("Admin", "Administrador"):
        return jsonify({"success": False, "message": "Solo un administrador puede hacer esto"}), 403
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"success": False, "message": "El nombre es obligatorio"}), 400
    mesa = MesaService.crear(
        nombre, tipo=data.get("tipo", "mesa"), capacidad=int(data.get("capacidad", 4) or 4)
    )
    return jsonify({"success": True, "mesa": mesa.to_dict()})


@mesa_bp.route("/api/<int:id_mesa>/desactivar", methods=["POST"])
@login_required
def api_desactivar(id_mesa):
    if not usuario_tiene_rol("Admin", "Administrador"):
        return jsonify({"success": False, "message": "Solo un administrador puede hacer esto"}), 403
    try:
        MesaService.desactivar(id_mesa)
        return jsonify({"success": True})
    except MesaError as e:
        return jsonify({"success": False, "message": str(e)}), 400
