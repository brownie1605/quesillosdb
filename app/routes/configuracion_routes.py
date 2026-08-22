from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models import Usuario

from app.utils.decorators import require_roles

configuracion_bp = Blueprint("configuracion", __name__, url_prefix="/configuracion")

@configuracion_bp.before_request
def check_roles():
    return require_roles('Administrador', 'Cajero', 'Inventario')


@configuracion_bp.route("/")
@login_required
def index():
    return render_template("configuracion/index.html")

@configuracion_bp.route("/api/cambiar_password", methods=["POST"])
@login_required
def api_cambiar_password():
    data = request.json
    actual = data.get("password_actual")
    nueva = data.get("password_nueva")
    
    if not check_password_hash(current_user.password_hash, actual):
        return jsonify({"success": False, "message": "La contraseña actual es incorrecta"}), 400
        
    current_user.password_hash = generate_password_hash(nueva)
    db.session.commit()
    return jsonify({"success": True, "message": "Contraseña actualizada exitosamente"})

@configuracion_bp.route("/api/guardar_preferencias", methods=["POST"])
@login_required
def api_guardar_preferencias():
    data = request.json
    
    if "tema_preferido" in data:
        current_user.tema_preferido = data["tema_preferido"]
    if "color_primario" in data:
        current_user.color_primario = data["color_primario"]
        
    try:
        db.session.commit()
        return jsonify({"success": True, "message": "Preferencias visuales guardadas"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
