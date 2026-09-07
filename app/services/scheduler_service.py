"""Jobs en segundo plano: monitor de red + sincronizacion automatica."""
import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.network_service import NetworkService
from app.services.sync_service import SyncService
from app.services.notificacion_service import NotificacionService
from app.services.backup_service import BackupService

log = logging.getLogger("sync.scheduler")

scheduler = BackgroundScheduler(daemon=True, timezone="America/Managua")

NOTIFICACIONES_INTERVAL_SEGUNDOS = 300  # cada 5 min: stock bajo + pedidos demorados


def _job_notificaciones(app):
    with app.app_context():
        try:
            NotificacionService.revisar_todo()
        except Exception:  # noqa: BLE001
            log.exception("Fallo la revision periodica de notificaciones")


def _job_backup(app):
    """Respaldo diario de la base LOCAL (la que de verdad puede perderse
    si falla el disco de esta maquina). No depende de que haya internet
    ni de que la sincronizacion este activada."""
    with app.app_context():
        try:
            BackupService.crear_backup(nombre_bind="local")
            dias = app.config.get("BACKUP_RETENCION_DIAS", 14)
            BackupService.limpiar_viejos(dias_retener=dias, prefijo="local")
        except Exception:  # noqa: BLE001
            log.exception("Fallo el respaldo automatico")


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
    """Arranca los jobs. Evita duplicarlos con el reloader de Flask.

    Notificaciones y respaldos SIEMPRE se inician, incluso con
    SYNC_ENABLED=false (ej. una instancia 100% en la nube que no necesita
    sincronizarse consigo misma) -- no dependen de la nube, dependen de que
    el negocio siga operando y de que su propia base de datos no se pierda.
    Solo el monitor de red y la sincronizacion se saltan en ese caso.
    """
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" and scheduler.running:
        return scheduler
    if scheduler.running:
        return scheduler

    sync_habilitado = app.config.get("SYNC_ENABLED", True)
    if sync_habilitado:
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
    else:
        log.info("SYNC_ENABLED=false -> monitor de red y sincronizacion no se inician")

    scheduler.add_job(
        func=_job_notificaciones,
        args=[app],
        trigger="interval",
        seconds=NOTIFICACIONES_INTERVAL_SEGUNDOS,
        id="notificaciones_periodicas",
        replace_existing=True,
        max_instances=1,
    )
    backup_horas = app.config.get("BACKUP_INTERVALO_HORAS", 24)
    backup_dias = app.config.get("BACKUP_RETENCION_DIAS", 14)
    scheduler.add_job(
        func=_job_backup,
        args=[app],
        trigger="interval",
        hours=backup_horas,
        id="respaldo_automatico",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(),  # tambien corre uno al arrancar, no solo 24h despues
    )
    scheduler.start()
    log.info(
        "Scheduler iniciado (sync=%s, notificaciones cada %ss, respaldo cada %sh, retencion %sd)",
        sync_habilitado, NOTIFICACIONES_INTERVAL_SEGUNDOS, backup_horas, backup_dias,
    )
    return scheduler
