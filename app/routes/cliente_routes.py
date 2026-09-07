"""Clientes: alta rapida (se usa tambien desde el selector del POS)."""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Cliente
from app.services.auditoria_service import registrar_auditoria
from app.utils.decorators import require_roles, usuario_tiene_rol

cliente_bp = Blueprint("cliente", __name__, url_prefix="/clientes")


@cliente_bp.before_request
def check_roles():
    return require_roles("Admin", "Administrador", "Cajero", "Mesero")


@cliente_bp.route("/")
@login_required
def lista():
    return render_template("clientes/lista.html")


@cliente_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    clientes = Cliente.query.order_by(Cliente.nombre).all()
    return jsonify([c.to_dict() for c in clientes])


@cliente_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"success": False, "message": "El nombre es obligatorio"}), 400
    try:
        tipo_cliente = data.get("tipo_cliente") or "externo"
        if tipo_cliente not in ("interno", "externo"):
            tipo_cliente = "externo"
        cliente = Cliente(
            id_empresa=current_user.id_empresa,
            nombre=nombre,
            cedula=data.get("cedula"),
            telefono=data.get("telefono"),
            direccion=data.get("direccion"),
            tipo_cliente=tipo_cliente,
            es_preferencial=bool(data.get("es_preferencial")),
            estado="activo",
        )
        db.session.add(cliente)
        db.session.commit()
        registrar_auditoria("CREAR CLIENTE", "Clientes", {"cliente": nombre})
        return jsonify({"success": True, "cliente": cliente.to_dict()})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@cliente_bp.route("/api/editar/<int:id_cliente>", methods=["POST"])
@login_required
def api_editar(id_cliente):
    cliente = Cliente.query.get_or_404(id_cliente)
    data = request.get_json(silent=True) or {}
    try:
        cliente.nombre = data.get("nombre", cliente.nombre)
        cliente.cedula = data.get("cedula", cliente.cedula)
        cliente.telefono = data.get("telefono", cliente.telefono)
        cliente.direccion = data.get("direccion", cliente.direccion)
        if data.get("tipo_cliente") in ("interno", "externo"):
            cliente.tipo_cliente = data.get("tipo_cliente")
        if "es_preferencial" in data:
            cliente.es_preferencial = bool(data.get("es_preferencial"))
        db.session.commit()
        registrar_auditoria("EDITAR CLIENTE", "Clientes", {"cliente": cliente.nombre})
        return jsonify({"success": True, "cliente": cliente.to_dict()})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@cliente_bp.route("/api/eliminar/<int:id_cliente>", methods=["DELETE", "POST"])
@login_required
def api_eliminar(id_cliente):
    if not usuario_tiene_rol("Admin", "Administrador"):
        return jsonify({"success": False, "message": "Solo un administrador puede hacer esto"}), 403
    cliente = Cliente.query.get_or_404(id_cliente)
    try:
        cliente.estado = "inactivo"
        db.session.commit()
        registrar_auditoria("ELIMINAR CLIENTE", "Clientes", {"cliente": cliente.nombre})
        return jsonify({"success": True})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
