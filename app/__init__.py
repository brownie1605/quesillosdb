import logging
from datetime import datetime

from flask import Flask, request, jsonify, render_template

from app.config.config import Config
from app.extensions import db, migrate, login_manager, mail, socketio, csrf, limiter

from app.routes.auth_routes import auth_bp
from app.routes.dashboard_routes import dashboard_bp
from app.routes.producto_routes import producto_bp
from app.routes.venta_routes import venta_bp
from app.routes.compra_routes import compra_bp
from app.routes.inventario_routes import inventario_bp
from app.routes.reporte_routes import reporte_bp
from app.routes.proveedor_routes import proveedor_bp
from app.routes.usuario_routes import usuario_bp
from app.routes.configuracion_routes import configuracion_bp
from app.routes.auditoria_routes import auditoria_bp
from app.routes.receta_routes import receta_bp
from app.routes.cocina_routes import cocina_bp
from app.routes.sync_routes import sync_bp
from app.routes.notificacion_routes import notificacion_bp
from app.routes.mesa_routes import mesa_bp
from app.routes.cliente_routes import cliente_bp
from app.routes.caja_routes import caja_bp

from app.models import Usuario


def create_app(config_class=Config, iniciar_jobs=True):
    app = Flask(__name__)
    app.config.from_object(config_class)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ---------------------------------------------------------- extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    if not app.config.get("TESTING"):
        socketio.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Debes iniciar sesión para acceder."
    login_manager.login_message_category = "warning"

    csrf.init_app(app)
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    # ---------------------------------------------------------- contexto
    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from app.models import Empresa
        from app.services.network_service import NetworkService

        empresa = None
        if current_user.is_authenticated and current_user.id_empresa:
            empresa = db.session.get(Empresa, current_user.id_empresa)
        return dict(
            empresa_actual=empresa,
            now=datetime.now(),
            sync_online=NetworkService.is_online(),
        )

    @app.template_filter("number_format")
    def number_format_filter(value, decimals=2):
        try:
            val = float(value)
        except (TypeError, ValueError):
            return "0"
        return f"{val:,.{decimals}f}"

    @app.template_filter("datetimeformat")
    def datetimeformat_filter(value, formato="%d/%m/%Y %H:%M"):
        if not value:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return value
        return value.strftime(formato)

    # ---------------------------------------------------------- headers de seguridad
    # CSP deliberadamente permisivo en 'unsafe-inline' (script/style): casi
    # toda plantilla de este proyecto usa <script> y style="" inline, y
    # pasar a nonces por request tocaria decenas de archivos de golpe. Aun
    # asi esto ya bloquea cargar scripts desde un dominio que no sea este
    # o cdn.jsdelivr.net (los unicos CDN que usa el sistema), y bloquea que
    # la app se incruste en un iframe ajeno (frame-ancestors).
    _CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "img-src 'self' data: blob: https://unpkg.com; "
        "connect-src 'self' https://unpkg.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        # HSTS solo tiene sentido (y solo es seguro anunciar) si esta
        # request de verdad llego por HTTPS -- anunciarlo sobre HTTP no
        # hace nada y puede confundir a quien audite los headers.
        if request.is_secure:
            resp.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return resp

    # ---------------------------------------------------------- paginas de error
    def _quiere_json():
        return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"

    def _error_response(codigo, mensaje):
        if _quiere_json():
            return jsonify({"success": False, "message": mensaje}), codigo
        return render_template("errores/error.html", codigo=codigo, mensaje=mensaje), codigo

    @app.errorhandler(400)
    def _e400(e):
        return _error_response(400, "Solicitud invalida.")

    @app.errorhandler(401)
    def _e401(e):
        return _error_response(401, "Debes iniciar sesión para acceder.")

    @app.errorhandler(403)
    def _e403(e):
        return _error_response(403, "No tienes permiso para acceder a esto.")

    @app.errorhandler(404)
    def _e404(e):
        return _error_response(404, "No encontramos lo que buscas.")

    @app.errorhandler(429)
    def _e429(e):
        return _error_response(429, "Demasiados intentos. Espera un momento e intenta de nuevo.")

    @app.errorhandler(500)
    def _e500(e):
        app.logger.exception("Error interno no manejado")
        return _error_response(500, "Ocurrió un error interno. Ya quedó registrado.")

    @app.errorhandler(503)
    def _e503(e):
        return _error_response(503, "El sistema no está disponible en este momento.")

    # ---------------------------------------------------------- salud
    # Endpoint sin login para que un monitor externo (ej. UptimeRobot,
    # gratis) revise si el sistema sigue respondiendo y avise si se cae --
    # sin esto, el primer aviso de una caida es un cliente molesto.
    @app.route("/healthz")
    def _healthz():
        from flask import jsonify
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"status": "ok", "hora": datetime.now().isoformat()})
        except Exception as e:  # noqa: BLE001
            return jsonify({"status": "error", "detalle": str(e)}), 503

    # ---------------------------------------------------------- PWA
    # sw.js debe servirse desde la raiz (no desde /static/) para que su
    # alcance ("scope") cubra toda la app y no solo /static/.
    @app.route("/sw.js")
    def _service_worker():
        from flask import send_from_directory
        resp = send_from_directory(app.static_folder, "sw.js")
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ---------------------------------------------------------- blueprints
    for bp in (
        auth_bp, dashboard_bp, producto_bp, venta_bp, compra_bp, inventario_bp,
        reporte_bp, proveedor_bp, usuario_bp, configuracion_bp, auditoria_bp,
        receta_bp, cocina_bp, sync_bp, notificacion_bp,
        mesa_bp, cliente_bp, caja_bp,
    ):
        app.register_blueprint(bp)

    # ------------------------------------- encolado automatico para la nube
    from app.services import sync_events

    sync_events.configurar(app)

    # ---------------------------------------------------------- CLI + jobs
    from app.cli import registrar_comandos

    registrar_comandos(app)

    if iniciar_jobs and app.config.get("SYNC_ENABLED", True):
        with app.app_context():
            from app.services.network_service import NetworkService

            try:
                NetworkService.check_connectivity(app)
            except Exception:  # noqa: BLE001
                app.logger.warning("No se pudo verificar la conectividad inicial")

        from app.services.scheduler_service import iniciar_scheduler

        iniciar_scheduler(app)

    return app
