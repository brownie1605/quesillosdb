from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_user, logout_user, login_required
from datetime import datetime, timedelta
import random
import string
import os

from app.extensions import db
from app.models.usuario import Usuario, RecuperacionPassword
from app.models.rol import Rol
from app.services.auth_service import verificar_password, generar_password
from app.services.auditoria_service import registrar_auditoria
from app.services.email_service import enviar_codigo_recuperacion
from app.utils.date_utils import nicaragua_now

auth_bp = Blueprint("auth", __name__)

DESTINO_POR_ROL = {
    "admin": "dashboard.dashboard",
    "administrador": "dashboard.dashboard",
    "cajero": "venta.pos",
    "mesero": "venta.pos",
    "cocinero": "cocina.pendientes",
}


def _generar_codigo():
    return "".join(random.choices(string.digits, k=6))


# ==================================================================
# LOGIN / LOGOUT
# ==================================================================
@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        password = request.form.get("password")

        user = Usuario.query.filter_by(usuario=usuario).first()

        is_valid_password = False
        if user and user.estado == "activo":
            if verificar_password(user.password_hash, password):
                is_valid_password = True
            elif user.codigo_temporal and user.codigo_temporal == password:
                if user.expiracion_codigo and user.expiracion_codigo > datetime.now():
                    is_valid_password = True
                    user.codigo_temporal = None
                    user.expiracion_codigo = None
                    db.session.commit()
                else:
                    flash("El código temporal ha expirado.", "danger")

        if is_valid_password:
            login_user(user)
            user.ultimo_acceso = nicaragua_now()
            db.session.commit()
            registrar_auditoria("INICIO SESION", "Auth", "Usuario logueado exitosamente")

            destino = DESTINO_POR_ROL.get(user.rol_nombre, "dashboard.dashboard")
            return redirect(url_for(destino))

        flash("Usuario o contraseña incorrectos", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    registrar_auditoria("CIERRE SESION", "Auth", "Usuario cerró sesión")
    logout_user()
    return redirect(url_for("auth.login"))


# ==================================================================
# RECUPERACION DE CONTRASENA (codigo de 6 digitos + correo + rol)
# ==================================================================
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Paso 1: el usuario ingresa su correo y su rol."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        rol_nombre = (request.form.get("rol") or "").strip()

        user = Usuario.query.filter_by(correo=email).first()

        if user and user.rol and user.rol.nombre.strip().lower() == rol_nombre.lower():
            codigo = _generar_codigo()
            user.codigo_recuperacion = codigo
            user.codigo_expiry = datetime.now() + timedelta(
                seconds=current_app.config.get("PASSWORD_RECOVERY_TIMEOUT", 900)
            )
            db.session.commit()

            enviado, detalle = enviar_codigo_recuperacion(
                email, codigo, user.nombre_completo
            )
            if enviado:
                flash("Código enviado a tu correo. Válido por 15 minutos.", "success")
            else:
                current_app.logger.warning("SMTP no disponible: %s", detalle)
                flash(
                    "No se pudo enviar el correo (" + detalle + "). "
                    "Revisa la configuración SMTP.",
                    "warning",
                )
            return redirect(url_for("auth.verify_code", email=email, rol=rol_nombre))

        flash("Correo o rol no encontrado.", "danger")

    roles = Rol.query.filter_by(estado="activo").order_by(Rol.nombre).all()
    return render_template("auth/forgot_password.html", roles=roles)


@auth_bp.route("/verify-code/<email>/<rol>", methods=["GET", "POST"])
def verify_code_view(email, rol):
    """Paso 2: el usuario ingresa el código de 6 dígitos."""
    if request.method == "POST":
        codigo_ingresado = (request.form.get("codigo") or "").strip()
        user = Usuario.query.filter_by(correo=email).first()

        if not user or not user.codigo_recuperacion or user.codigo_recuperacion != codigo_ingresado:
            flash("Código incorrecto.", "danger")
            return render_template("auth/verify_code.html", email=email, rol=rol)

        if not user.codigo_expiry or user.codigo_expiry < datetime.now():
            flash("Código expirado. Solicita uno nuevo.", "danger")
            return redirect(url_for("auth.forgot_password"))

        return redirect(
            url_for("auth.reset_password_view", email=email, rol=rol, codigo=codigo_ingresado)
        )

    return render_template("auth/verify_code.html", email=email, rol=rol)


# Alias usado en el plan: /verify-code/<email>/<rol>
auth_bp.add_url_rule(
    "/verify_code/<email>/<rol>",
    endpoint="verify_code",
    view_func=verify_code_view,
    methods=["GET", "POST"],
)


@auth_bp.route("/reset-password/<email>/<rol>/<codigo>", methods=["GET", "POST"])
def reset_password_view(email, rol, codigo):
    """Paso 3: nueva contraseña."""
    user = Usuario.query.filter_by(correo=email).first()

    if (
        not user
        or user.codigo_recuperacion != codigo
        or not user.codigo_expiry
        or user.codigo_expiry < datetime.now()
    ):
        flash("Sesión expirada. Solicita un nuevo código.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        nueva = request.form.get("password") or ""
        confirmar = request.form.get("password_confirm") or ""

        if nueva != confirmar:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("auth/reset_password.html", email=email, rol=rol, codigo=codigo)

        if len(nueva) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return render_template("auth/reset_password.html", email=email, rol=rol, codigo=codigo)

        user.password_hash = generar_password(nueva)
        user.codigo_recuperacion = None
        user.codigo_expiry = None
        db.session.commit()

        flash("Contraseña actualizada. Inicia sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", email=email, rol=rol, codigo=codigo)


@auth_bp.route("/api/roles-publicos", methods=["GET"])
def api_roles_publicos():
    roles = Rol.query.filter_by(estado="activo").order_by(Rol.nombre).all()
    return jsonify([{"id_rol": r.id_rol, "nombre": r.nombre} for r in roles])


# ==================================================================
# API JSON de recuperacion (compatibilidad con el login existente)
# ==================================================================
@auth_bp.route("/api/forgot-password", methods=["POST"])
def forgot_password_api():
    data = request.get_json(silent=True) or {}
    correo = data.get("correo")
    rol_nombre = data.get("rol")

    if not correo:
        return jsonify({"success": False, "message": "Correo es requerido."})

    user = Usuario.query.filter_by(correo=correo).first()
    if not user:
        return jsonify(
            {"success": False, "message": "Este correo electrónico no está registrado en el sistema."}
        )
    if rol_nombre and (not user.rol or user.rol.nombre.strip().lower() != rol_nombre.strip().lower()):
        return jsonify({"success": False, "message": "El rol no coincide con el usuario."})

    codigo = _generar_codigo()

    RecuperacionPassword.query.filter_by(usuario_id=user.id_usuario, usado=False).update(
        {"usado": True}
    )
    db.session.add(
        RecuperacionPassword(
            usuario_id=user.id_usuario,
            codigo=codigo,
            fecha_expiracion=datetime.now() + timedelta(minutes=15),
        )
    )
    user.codigo_recuperacion = codigo
    user.codigo_expiry = datetime.now() + timedelta(minutes=15)
    db.session.commit()

    enviado, detalle = enviar_codigo_recuperacion(correo, codigo, user.nombre_completo)
    if enviado:
        return jsonify(
            {"success": True, "message": "Se ha enviado un código de recuperación a tu correo."}
        )

    current_app.logger.warning("SMTP no disponible (%s). Código para %s: %s", detalle, correo, codigo)
    return jsonify(
        {
            "success": True,
            "message": "(Modo prueba) No se pudo enviar el correo: " + detalle,
            "modo_prueba": True,
        }
    )


@auth_bp.route("/api/verify-code", methods=["POST"])
def verify_code_api():
    data = request.get_json(silent=True) or {}
    correo = data.get("correo")
    codigo = data.get("codigo")

    if not correo or not codigo:
        return jsonify({"success": False, "message": "Correo y código son requeridos."})

    user = Usuario.query.filter_by(correo=correo).first()
    if not user or user.estado != "activo":
        return jsonify({"success": False, "message": "Código inválido o expirado."})

    recuperacion = RecuperacionPassword.query.filter_by(
        usuario_id=user.id_usuario, codigo=codigo, usado=False
    ).first()

    if recuperacion and recuperacion.fecha_expiracion > datetime.now():
        return jsonify({"success": True, "message": "Código verificado."})

    return jsonify({"success": False, "message": "El código es inválido o ha expirado."})


@auth_bp.route("/api/reset-password", methods=["POST"])
def reset_password_api():
    data = request.get_json(silent=True) or {}
    correo = data.get("correo")
    codigo = data.get("codigo")
    nueva_password = data.get("nueva_password")

    if not correo or not codigo or not nueva_password:
        return jsonify({"success": False, "message": "Faltan datos requeridos."})
    if len(nueva_password) < 6:
        return jsonify({"success": False, "message": "La contraseña debe tener al menos 6 caracteres."})

    user = Usuario.query.filter_by(correo=correo).first()
    if not user:
        return jsonify({"success": False, "message": "Usuario no encontrado."})

    recuperacion = RecuperacionPassword.query.filter_by(
        usuario_id=user.id_usuario, codigo=codigo, usado=False
    ).first()

    if recuperacion and recuperacion.fecha_expiracion > datetime.now():
        user.password_hash = generar_password(nueva_password)
        user.codigo_recuperacion = None
        user.codigo_expiry = None
        recuperacion.usado = True
        db.session.commit()

        registrar_auditoria(
            "ACTUALIZAR CONTRASENA", "Auth",
            "Usuario " + user.usuario + " restableció su contraseña.",
        )
        return jsonify({"success": True, "message": "Contraseña actualizada correctamente."})

    return jsonify(
        {"success": False, "message": "No se pudo restablecer la contraseña. Código inválido o expirado."}
    )
