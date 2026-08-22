"""Jobs en segundo plano: monitor de red + sincronizacion automatica."""
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.network_service import NetworkService
from app.services.sync_service import SyncService

log = logging.getLogger("sync.scheduler")

scheduler = BackgroundScheduler(daemon=True, timezone="America/Managua")


def _job_check_red(app):
    with app.app_context():
        antes = NetworkService.is_online()
        ahora = NetworkService.check_connectivity(app)
        # Al recuperar la señal, sincroniza de inmediato.
        if ahora and not antes:
            log.info("Conexion recuperada -> sincronizacion inmediata")
            try:
                SyncService.sync_full(disparador="reconexion")
            except Exception:  # noqa: BLE001
                log.exception("Fallo la sincronizacion por reconexion")
        _emitir_estado(app)


def _job_sync(app):
    with app.app_context():
        if not NetworkService.is_online():
            return
        try:
            SyncService.sync_full(disparador="automatico")
        except Exception:  # noqa: BLE001
            log.exception("Fallo la sincronizacion automatica")
        _emitir_estado(app)


def _emitir_estado(app):
    try:
        from app.extensions import socketio

        socketio.emit("sync_status", SyncService.estado_general())
    except Exception:  # noqa: BLE001
        pass


def iniciar_scheduler(app):
    """Arranca los jobs. Evita duplicarlos con el reloader de Flask."""
    if not app.config.get("SYNC_ENABLED", True):
        log.info("SYNC_ENABLED=false -> scheduler no iniciado")
        return None
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" and scheduler.running:
        return scheduler
    if scheduler.running:
        return scheduler

    scheduler.add_job(
        func=_job_check_red,
        args=[app],
        trigger="interval",
        seconds=app.config.get("NETWORK_CHECK_INTERVAL", 30),
        id="monitor_red",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        func=_job_sync,
        args=[app],
        trigger="interval",
        seconds=app.config.get("SYNC_INTERVAL", 120),
        id="sync_automatico",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    log.info(
        "Scheduler iniciado (red cada %ss, sync cada %ss)",
        app.config.get("NETWORK_CHECK_INTERVAL", 30),
        app.config.get("SYNC_INTERVAL", 120),
    )
    return scheduler
