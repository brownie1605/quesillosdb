import logging
from datetime import datetime

from flask import Flask

from app.config.config import Config
from app.extensions import db, migrate, login_manager, mail, socketio

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
from app.routes.insumo_routes import insumo_bp
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

    # ---------------------------------------------------------- blueprints
    for bp in (
        auth_bp, dashboard_bp, producto_bp, venta_bp, compra_bp, inventario_bp,
        reporte_bp, proveedor_bp, usuario_bp, configuracion_bp, auditoria_bp,
        receta_bp, insumo_bp, cocina_bp, sync_bp, notificacion_bp,
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
