from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, session
from flask_login import login_user, logout_user, login_required
from datetime import datetime, timedelta
import random
import string
import os

from app.extensions import db, limiter
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

MAX_INTENTOS_LOGIN = 5
BLOQUEO_LOGIN_MINUTOS = 15
MAX_INTENTOS_CODIGO = 5
SESSION_KEY_RESET = "reset_verificado"
SESSION_KEY_2FA_PENDIENTE_LOGIN = "login_2fa_pendiente"


def _generar_codigo():
    return "".join(random.choices(string.digits, k=6))


def _registrar_intento_codigo_fallido(user):
    """Cuenta un intento fallido verificando el codigo de recuperacion. Con
    solo 6 digitos (1 millon de combinaciones) y sin esto, alguien con el
    correo y rol de un usuario podia probarlos todos dentro de la ventana
    de 15 minutos. Al llegar al limite, se invalida el codigo -- toca pedir
    uno nuevo en vez de seguir probando."""
    user.intentos_codigo = (user.intentos_codigo or 0) + 1
    if user.intentos_codigo >= MAX_INTENTOS_CODIGO:
        user.codigo_recuperacion = None
        user.codigo_expiry = None
        user.intentos_codigo = 0
    db.session.commit()


# ==================================================================
# LOGIN / LOGOUT
# ==================================================================
@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        password = request.form.get("password")

        user = Usuario.query.filter_by(usuario=usuario).first()

        # Bloqueo temporal por intentos fallidos: ni se revisa la contrasena
        # si la cuenta esta bloqueada, para no darle mas intentos gratis a
        # quien esta probando contrasenas a lo bruto.
        if user and user.bloqueado_hasta and user.bloqueado_hasta > datetime.now():
            minutos = max(1, int((user.bloqueado_hasta - datetime.now()).total_seconds() // 60) + 1)
            flash(
                f"Cuenta bloqueada temporalmente por varios intentos fallidos. "
                f"Intenta de nuevo en {minutos} minuto(s).",
                "danger",
            )
            return render_template("auth/login.html")

        is_valid_password = False
        if user and user.estado == "activo":
            if verificar_password(user.password_hash, password):
                is_valid_password = True
            elif user.codigo_temporal and user.codigo_temporal == password:
                if user.expiracion_codigo and user.expiracion_codigo > datetime.now():
                    is_valid_password = True
                    user.codigo_temporal = None
                    user.expiracion_codigo = None
                else:
                    flash("El código temporal ha expirado.", "danger")

        if is_valid_password:
            user.intentos_fallidos = 0
            user.bloqueado_hasta = None
            db.session.commit()

            if user.totp_habilitado:
                # Contrasena correcta, pero falta el segundo factor: no se
                # llama login_user() todavia -- solo queda "a medio loguear"
                # en la sesion hasta que verify_2fa_view() confirme el codigo.
                session[SESSION_KEY_2FA_PENDIENTE_LOGIN] = user.id_usuario
                return redirect(url_for("auth.verify_2fa_view"))

            login_user(user)
            user.ultimo_acceso = nicaragua_now()
            db.session.commit()
            registrar_auditoria("INICIO SESION", "Auth", "Usuario logueado exitosamente")

            destino = DESTINO_POR_ROL.get(user.rol_nombre, "dashboard.dashboard")
            return redirect(url_for(destino))

        if user:
            user.intentos_fallidos = (user.intentos_fallidos or 0) + 1
            if user.intentos_fallidos >= MAX_INTENTOS_LOGIN:
                user.bloqueado_hasta = datetime.now() + timedelta(minutes=BLOQUEO_LOGIN_MINUTOS)
                user.intentos_fallidos = 0
                registrar_auditoria(
                    "BLOQUEO POR INTENTOS", "Auth",
                    f"Cuenta '{user.usuario}' bloqueada {BLOQUEO_LOGIN_MINUTOS} min por intentos fallidos",
                )
            db.session.commit()

        flash("Usuario o contraseña incorrectos", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/verificar-2fa", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def verify_2fa_view():
    """Segundo paso del login cuando el usuario tiene 2FA activado. Solo
    se llega aqui con contrasena ya verificada (ver login()); sin el
    id pendiente en sesion, no hay nada que verificar."""
    from app.services.twofa_service import TwoFAService

    user_id = session.get(SESSION_KEY_2FA_PENDIENTE_LOGIN)
    if not user_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(Usuario, user_id)
    if not user or not user.totp_habilitado:
        session.pop(SESSION_KEY_2FA_PENDIENTE_LOGIN, None)
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        codigo = (request.form.get("codigo") or "").strip()
        valido = TwoFAService.verificar_codigo(user.totp_secret, codigo) or \
            TwoFAService.verificar_y_consumir_recovery(user, codigo)

        if valido:
            session.pop(SESSION_KEY_2FA_PENDIENTE_LOGIN, None)
            login_user(user)
            user.ultimo_acceso = nicaragua_now()
            db.session.commit()
            registrar_auditoria("INICIO SESION", "Auth", "Usuario logueado exitosamente (2FA)")
            destino = DESTINO_POR_ROL.get(user.rol_nombre, "dashboard.dashboard")
            return redirect(url_for(destino))

        flash("Código incorrecto.", "danger")

    return render_template("auth/verify_2fa.html", usuario=user.usuario)


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
@limiter.limit("5 per minute")
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
            user.intentos_codigo = 0
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
@limiter.limit("15 per minute")
def verify_code_view(email, rol):
    """Paso 2: el usuario ingresa el código de 6 dígitos."""
    if request.method == "POST":
        codigo_ingresado = (request.form.get("codigo") or "").strip()
        user = Usuario.query.filter_by(correo=email).first()

        if not user or not user.codigo_recuperacion or user.codigo_recuperacion != codigo_ingresado:
            if user:
                _registrar_intento_codigo_fallido(user)
            flash("Código incorrecto.", "danger")
            return render_template("auth/verify_code.html", email=email, rol=rol)

        if not user.codigo_expiry or user.codigo_expiry < datetime.now():
            flash("Código expirado. Solicita uno nuevo.", "danger")
            return redirect(url_for("auth.forgot_password"))

        # Verificado: se guarda en la sesion firmada (nunca en la URL, donde
        # quedaria en logs del servidor e historial del navegador) para el
        # ultimo paso. Vence pronto para no dejar la ventana abierta.
        session[SESSION_KEY_RESET] = {
            "email": email,
            "rol": rol,
            "exp": (datetime.now() + timedelta(minutes=10)).isoformat(),
        }
        return redirect(url_for("auth.reset_password_view", email=email, rol=rol))

    return render_template("auth/verify_code.html", email=email, rol=rol)


# Alias usado en el plan: /verify-code/<email>/<rol>
auth_bp.add_url_rule(
    "/verify_code/<email>/<rol>",
    endpoint="verify_code",
    view_func=verify_code_view,
    methods=["GET", "POST"],
)


@auth_bp.route("/reset-password/<email>/<rol>", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def reset_password_view(email, rol):
    """Paso 3: nueva contraseña. El codigo ya no viaja por la URL -- se
    confirma que este paso vino de un `verify_code_view` exitoso mirando la
    sesion firmada (`SESSION_KEY_RESET`), no un parametro adivinable/logueable."""
    verificado = session.get(SESSION_KEY_RESET) or {}
    vencido = True
    if verificado.get("exp"):
        try:
            vencido = datetime.fromisoformat(verificado["exp"]) < datetime.now()
        except ValueError:
            vencido = True

    if verificado.get("email") != email or verificado.get("rol") != rol or vencido:
        session.pop(SESSION_KEY_RESET, None)
        flash("Sesión expirada. Solicita un nuevo código.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = Usuario.query.filter_by(correo=email).first()
    if not user:
        session.pop(SESSION_KEY_RESET, None)
        flash("Sesión expirada. Solicita un nuevo código.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        nueva = request.form.get("password") or ""
        confirmar = request.form.get("password_confirm") or ""

        if nueva != confirmar:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("auth/reset_password.html", email=email, rol=rol)

        if len(nueva) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
            return render_template("auth/reset_password.html", email=email, rol=rol)

        user.password_hash = generar_password(nueva)
        user.codigo_recuperacion = None
        user.codigo_expiry = None
        db.session.commit()
        session.pop(SESSION_KEY_RESET, None)

        flash("Contraseña actualizada. Inicia sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", email=email, rol=rol)


@auth_bp.route("/api/roles-publicos", methods=["GET"])
def api_roles_publicos():
    roles = Rol.query.filter_by(estado="activo").order_by(Rol.nombre).all()
    return jsonify([{"id_rol": r.id_rol, "nombre": r.nombre} for r in roles])


# ==================================================================
# API JSON de recuperacion (compatibilidad con el login existente)
# ==================================================================
@auth_bp.route("/api/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password_api():
    data = request.get_json(silent=True) or {}
    correo = data.get("correo")
    rol_nombre = data.get("rol")

    if not correo:
        return jsonify({"success": False, "message": "Correo es requerido."})

    # Mensaje generico sin importar si el correo existe, si el rol no
    # coincide o si el envio realmente ocurrio: lo contrario deja
    # enumerar cuentas validas probando correos al azar.
    respuesta_generica = jsonify(
        {"success": True, "message": "Si el correo y el rol coinciden con una cuenta, se envió un código."}
    )

    user = Usuario.query.filter_by(correo=correo).first()
    if not user or user.estado != "activo":
        return respuesta_generica
    if rol_nombre and (not user.rol or user.rol.nombre.strip().lower() != rol_nombre.strip().lower()):
        return respuesta_generica

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
    user.intentos_codigo = 0
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
@limiter.limit("15 per minute")
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

    _registrar_intento_codigo_fallido(user)
    return jsonify({"success": False, "message": "El código es inválido o ha expirado."})


@auth_bp.route("/api/reset-password", methods=["POST"])
@limiter.limit("15 per minute")
def reset_password_api():
    data = request.get_json(silent=True) or {}
    correo = data.get("correo")
    codigo = data.get("codigo")
    nueva_password = data.get("nueva_password")

    if not correo or not codigo or not nueva_password:
        return jsonify({"success": False, "message": "Faltan datos requeridos."})
    if len(nueva_password) < 8:
        return jsonify({"success": False, "message": "La contraseña debe tener al menos 8 caracteres."})

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

    _registrar_intento_codigo_fallido(user)
    return jsonify(
        {"success": False, "message": "No se pudo restablecer la contraseña. Código inválido o expirado."}
    )
