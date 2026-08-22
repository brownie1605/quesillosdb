"""Encolado automatico de cambios para la sincronizacion.

Antes cada servicio llamaba a `SyncService.encolar()` a mano, y bastaba con
olvidarlo en un camino (un comando de consola, una ruta nueva) para que el
registro nunca llegara a la nube y ademas rompiera las llaves foraneas de los
registros que si se subian.

Aqui se engancha un unico listener a la sesion de SQLAlchemy: cualquier
INSERT, UPDATE o DELETE sobre una tabla sincronizable queda encolado solo,
venga del camino que venga, y dentro de la misma transaccion que el dato.

Las escrituras que vienen DE la nube (bootstrap y pull) usan SQL directo, que
no dispara eventos ORM, asi que no se re-encolan. Para el resto de casos esta
el contexto `sin_sync()`.
"""
import logging
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

from sqlalchemy import event, insert, update
from sqlalchemy.orm import Session as SASession

from app.extensions import db
from app.models.sync import SyncQueue
from app.services.sync_service import TABLAS_SYNC, PK_POR_TABLA, checksum
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("sync.eventos")

_TABLAS = set(TABLAS_SYNC)

# Config leida una sola vez por proceso (evita depender de current_app aqui).
_CONTEXTO = {"id_empresa": 1, "dispositivo": "local-01"}


def configurar(app):
    _CONTEXTO["id_empresa"] = app.config.get("ID_EMPRESA", 1)
    _CONTEXTO["dispositivo"] = app.config.get("DEVICE_ID", "local-01")


@contextmanager
def sin_sync(session=None):
    """Bloque cuyos cambios NO se encolan (datos que ya vienen de la nube)."""
    session = session or db.session
    anterior = getattr(session, "_sync_desactivado", False)
    session._sync_desactivado = True
    try:
        yield
    finally:
        session._sync_desactivado = anterior


def _valor_simple(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, (bytes, bytearray)):
        return None          # las imagenes no viajan en la cola
    return v


def _instantanea(obj):
    """Columnas del objeto en formato serializable."""
    datos = {}
    for col in obj.__table__.columns:
        valor = _valor_simple(getattr(obj, col.name, None))
        if valor is not None:
            datos[col.name] = valor
    return datos


def _usuario_actual():
    try:
        from flask_login import current_user

        if current_user and current_user.is_authenticated:
            return current_user.id_usuario
    except Exception:  # noqa: BLE001 - fuera de contexto de peticion
        pass
    return None


def _pendientes(session):
    """(objeto, operacion) de todo lo sincronizable en este flush."""
    for obj in session.new:
        yield obj, "INSERT"
    for obj in session.dirty:
        if session.is_modified(obj, include_collections=False):
            yield obj, "UPDATE"
    for obj in session.deleted:
        yield obj, "DELETE"


@event.listens_for(SASession, "after_flush")
def _encolar_cambios(session, flush_context):
    if getattr(session, "_sync_desactivado", False):
        return

    ahora = nicaragua_now()
    usuario = _usuario_actual()
    # Un mismo registro puede tocarse en varios flush de la misma transaccion
    # (p. ej. la venta se crea y despues se le calcula el total). Se guarda a
    # que fila de la cola corresponde para refrescarla en vez de duplicarla.
    encolados = session.info.setdefault("_sync_encolados", {})

    for obj, operacion in _pendientes(session):
        tabla = getattr(obj, "__tablename__", None)
        if tabla not in _TABLAS:
            continue
        pk = PK_POR_TABLA.get(tabla)
        if not pk:
            continue
        registro_id = getattr(obj, pk, None)
        if registro_id is None:
            continue

        payload = {} if operacion == "DELETE" else _instantanea(obj)
        firma = checksum(payload) if payload else None
        clave = (tabla, registro_id)

        if clave in encolados:
            # Ya esta en la cola: se actualiza con el estado mas reciente.
            session.execute(
                update(SyncQueue.__table__)
                .where(SyncQueue.__table__.c.id_sync_queue == encolados[clave])
                .values(payload=payload, checksum_datos=firma,
                        timestamp_operacion=ahora)
            )
            continue

        resultado = session.execute(
            insert(SyncQueue.__table__).values(
                operation_type=operacion,
                tabla_afectada=tabla,
                registro_id=registro_id,
                id_empresa=_CONTEXTO["id_empresa"],
                timestamp_operacion=ahora,
                estado_sync="pendiente",
                payload=payload,
                usuario_origen=usuario,
                dispositivo_origen=_CONTEXTO["dispositivo"],
                checksum_datos=firma,
                intentos=0,
                fecha_creacion=ahora,
            )
        )
        nuevo_id = resultado.inserted_primary_key[0] if resultado.inserted_primary_key else None
        if nuevo_id is not None:
            encolados[clave] = nuevo_id


@event.listens_for(SASession, "after_commit")
@event.listens_for(SASession, "after_rollback")
def _limpiar_seguimiento(session):
    session.info.pop("_sync_encolados", None)
