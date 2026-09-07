from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models import Usuario
from app.services.auditoria_service import registrar_auditoria
from app.services.twofa_service import TwoFAService

configuracion_bp = Blueprint("configuracion", __name__, url_prefix="/configuracion")

# Configuracion es autoservicio (tu propia contrasena, tus propias
# preferencias, tu propio 2FA): cualquier usuario logueado puede entrar,
# sin importar el rol -- antes exigia roles que ni existen en el sistema
# ('Administrador', 'Inventario'), lo que dejaba a Mesero y Cocinero sin
# poder cambiar ni su propia contrasena.
@configuracion_bp.before_request
@login_required
def check_roles():
    return None


@configuracion_bp.route("/")
@login_required
def index():
    return render_template("configuracion/index.html")

@configuracion_bp.route("/api/cambiar_password", methods=["POST"])
@login_required
def api_cambiar_password():
    data = request.json or {}
    actual = data.get("password_actual") or ""
    nueva = data.get("password_nueva") or ""

    if not check_password_hash(current_user.password_hash, actual):
        return jsonify({"success": False, "message": "La contraseña actual es incorrecta"}), 400

    if len(nueva) < 8:
        return jsonify({"success": False, "message": "La nueva contraseña debe tener al menos 8 caracteres"}), 400

    current_user.password_hash = generate_password_hash(nueva)
    db.session.commit()
    registrar_auditoria("ACTUALIZAR CONTRASENA", "Configuracion", "El usuario cambió su propia contraseña")
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


# ======================================================================
# 2FA (TOTP) -- autoservicio: cada quien activa/desactiva el suyo.
# ======================================================================
SESSION_KEY_2FA_PENDIENTE = "totp_pendiente"


@configuracion_bp.route("/api/2fa/estado", methods=["GET"])
def api_2fa_estado():
    return jsonify({"habilitado": bool(current_user.totp_habilitado)})


@configuracion_bp.route("/api/2fa/iniciar", methods=["POST"])
def api_2fa_iniciar():
    """Genera un secreto NUEVO y lo deja pendiente en la sesion -- no se
    guarda en la BD hasta que el usuario confirme con un codigo real de
    su app, para no dejar nunca un 2FA a medio activar."""
    from flask import session

    if current_user.totp_habilitado:
        return jsonify({"success": False, "message": "El 2FA ya está activado. Desactívalo primero para reconfigurarlo."}), 400

    secreto = TwoFAService.generar_secreto()
    session[SESSION_KEY_2FA_PENDIENTE] = secreto
    uri = TwoFAService.uri_provisioning(current_user, secreto)
    return jsonify({
        "success": True,
        "secreto": secreto,
        "qr": TwoFAService.qr_data_uri(uri),
    })


@configuracion_bp.route("/api/2fa/confirmar", methods=["POST"])
def api_2fa_confirmar():
    from flask import session

    secreto = session.get(SESSION_KEY_2FA_PENDIENTE)
    if not secreto:
        return jsonify({"success": False, "message": "No hay una activación en curso. Empieza de nuevo."}), 400

    data = request.json or {}
    codigo = (data.get("codigo") or "").strip()
    if not TwoFAService.verificar_codigo(secreto, codigo):
        return jsonify({"success": False, "message": "Código incorrecto."}), 400

    codigos_recuperacion = TwoFAService.activar(current_user, secreto)
    session.pop(SESSION_KEY_2FA_PENDIENTE, None)
    registrar_auditoria("ACTIVAR 2FA", "Configuracion", "El usuario activó la verificación en dos pasos")
    return jsonify({"success": True, "codigos_recuperacion": codigos_recuperacion})


@configuracion_bp.route("/api/2fa/desactivar", methods=["POST"])
def api_2fa_desactivar():
    data = request.json or {}
    password = data.get("password") or ""
    if not check_password_hash(current_user.password_hash, password):
        return jsonify({"success": False, "message": "Contraseña incorrecta."}), 400

    TwoFAService.desactivar(current_user)
    registrar_auditoria("DESACTIVAR 2FA", "Configuracion", "El usuario desactivó la verificación en dos pasos")
    return jsonify({"success": True})
