"""Deteccion de conectividad con la base de datos en la nube.

La app SIEMPRE trabaja contra MySQL local. Este servicio unicamente informa
si la nube esta alcanzable, para decidir cuando disparar la sincronizacion.
"""
import threading
import logging
from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("sync.network")


class NetworkService:
    _lock = threading.Lock()
    _is_online = False
    _last_check = None
    _last_error = None
    _last_online = None
    _last_offline = None
    _listeners = []

    # ------------------------------------------------------------------
    @classmethod
    def check_connectivity(cls, app=None):
        """Hace ping real a la BD remota. Devuelve True/False."""
        estaba_online = cls._is_online
        online = False
        error = None
        try:
            engine = db.engines.get("cloud")
            if engine is None:
                raise RuntimeError("Bind 'cloud' no configurado")
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            online = True
        except Exception as exc:  # noqa: BLE001 - cualquier fallo = offline
            error = str(exc).split("\n")[0][:300]
            online = False

        with cls._lock:
            cls._is_online = online
            cls._last_check = nicaragua_now()
            cls._last_error = error
            if online:
                cls._last_online = cls._last_check
            else:
                cls._last_offline = cls._last_check

        if online != estaba_online:
            log.info("Cambio de conectividad: %s", "ONLINE" if online else "OFFLINE")
            cls._notificar(online, app)

        return online

    # ------------------------------------------------------------------
    @classmethod
    def is_online(cls):
        return cls._is_online

    @classmethod
    def status(cls):
        return {
            "online": cls._is_online,
            "last_check": cls._last_check.isoformat() if cls._last_check else None,
            "last_online": cls._last_online.isoformat() if cls._last_online else None,
            "last_offline": cls._last_offline.isoformat() if cls._last_offline else None,
            "error": cls._last_error,
        }

    # ------------------------------------------------------------------
    @classmethod
    def on_change(cls, callback):
        """Registra un callback callback(online: bool, app) ."""
        cls._listeners.append(callback)

    @classmethod
    def _notificar(cls, online, app):
        for cb in list(cls._listeners):
            try:
                cb(online, app)
            except Exception:  # noqa: BLE001
                log.exception("Error en listener de conectividad")
