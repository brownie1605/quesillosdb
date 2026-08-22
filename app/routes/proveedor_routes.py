from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Proveedor
from app.services.auditoria_service import registrar_auditoria

from app.utils.decorators import require_roles

proveedor_bp = Blueprint("proveedor", __name__, url_prefix="/proveedores")

@proveedor_bp.before_request
def check_roles():
    return require_roles('Administrador', 'Cajero', 'Inventario')


@proveedor_bp.route("/")
@login_required
def lista():
    return render_template("proveedores/lista.html")

@proveedor_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    proveedores = Proveedor.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    return jsonify([p.to_dict() for p in proveedores])

@proveedor_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    data = request.json
    try:
        nuevo = Proveedor(
            id_empresa=current_user.id_empresa,
            nombre=data.get("nombre"),
            ruc=data.get("ruc", ""),
            telefono=data.get("telefono", ""),
            correo=data.get("correo", ""),
            direccion=data.get("direccion", "")
        )
        db.session.add(nuevo)
        db.session.commit()
        registrar_auditoria("CREAR PROVEEDOR", "Proveedores", f"Proveedor {nuevo.nombre} registrado")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@proveedor_bp.route("/api/editar/<int:id>", methods=["PUT"])
@login_required
def api_editar(id):
    data = request.json
    try:
        p = Proveedor.query.get_or_404(id)
        if p.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        p.nombre = data.get("nombre", p.nombre)
        p.ruc = data.get("ruc", p.ruc)
        p.telefono = data.get("telefono", p.telefono)
        p.correo = data.get("correo", p.correo)
        p.direccion = data.get("direccion", p.direccion)
        
        db.session.commit()
        registrar_auditoria("EDITAR PROVEEDOR", "Proveedores", f"Proveedor {p.nombre} modificado")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@proveedor_bp.route("/api/eliminar/<int:id>", methods=["DELETE"])
@login_required
def api_eliminar(id):
    try:
        p = Proveedor.query.get_or_404(id)
        if p.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        p.estado = "inactivo"
        db.session.commit()
        registrar_auditoria("ELIMINAR PROVEEDOR", "Proveedores", f"Proveedor {p.nombre} eliminado")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
