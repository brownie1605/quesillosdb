"""Modelos de infraestructura de sincronizacion Local <-> Nube."""
from app.extensions import db
from app.utils.date_utils import nicaragua_now


class SyncQueue(db.Model):
    """Cola de operaciones locales pendientes de subir a la nube."""

    __tablename__ = "sync_queue"

    id_sync_queue = db.Column(db.Integer, primary_key=True)
    operation_type = db.Column(db.Enum("INSERT", "UPDATE", "DELETE"), nullable=False)
    tabla_afectada = db.Column(db.String(100), nullable=False)
    registro_id = db.Column(db.Integer, nullable=False)
    id_empresa = db.Column(db.Integer, nullable=False, default=1)
    timestamp_operacion = db.Column(db.DateTime, default=nicaragua_now, nullable=False)
    timestamp_sincronizacion = db.Column(db.DateTime)
    estado_sync = db.Column(
        db.Enum("pendiente", "sinc_local", "sinc_remoto", "en_conflicto", "resuelto", "error"),
        default="pendiente",
        nullable=False,
    )
    payload = db.Column(db.JSON)
    usuario_origen = db.Column(db.Integer)
    dispositivo_origen = db.Column(db.String(100))
    checksum_datos = db.Column(db.String(64))
    intentos = db.Column(db.Integer, default=0)
    ultimo_error = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=nicaragua_now)

    __table_args__ = (
        db.Index("idx_tabla_estado", "tabla_afectada", "estado_sync"),
        db.Index("idx_timestamp_operacion", "timestamp_operacion"),
    )

    def to_dict(self):
        return {
            "id_sync_queue": self.id_sync_queue,
            "operation_type": self.operation_type,
            "tabla_afectada": self.tabla_afectada,
            "registro_id": self.registro_id,
            "timestamp_operacion": self.timestamp_operacion.isoformat()
            if self.timestamp_operacion
            else None,
            "estado_sync": self.estado_sync,
            "payload": self.payload,
            "usuario_origen": self.usuario_origen,
            "dispositivo_origen": self.dispositivo_origen,
            "checksum_datos": self.checksum_datos,
        }


class ConflictLog(db.Model):
    """Registro de conflictos detectados durante la sincronizacion."""

    __tablename__ = "conflict_log"

    id_conflicto = db.Column(db.Integer, primary_key=True)
    tabla_afectada = db.Column(db.String(100), nullable=False)
    registro_id = db.Column(db.Integer, nullable=False)
    id_empresa = db.Column(db.Integer, nullable=False, default=1)
    timestamp_deteccion = db.Column(db.DateTime, default=nicaragua_now)

    datos_local = db.Column(db.JSON)
    timestamp_local = db.Column(db.DateTime)
    usuario_local = db.Column(db.Integer)

    datos_remoto = db.Column(db.JSON)
    timestamp_remoto = db.Column(db.DateTime)
    usuario_remoto = db.Column(db.Integer)

    tipo_conflicto = db.Column(
        db.Enum("venta_simultanea", "update_simultaneo", "delete_conflict", "stock", "otro"),
        default="otro",
    )
    estado_resolucion = db.Column(
        db.Enum("pendiente_resolucion", "resuelto_auto", "resuelto_manual"),
        default="pendiente_resolucion",
    )
    resolucion_tipo = db.Column(
        db.Enum("prioridad_local", "prioridad_remoto", "merge", "manual"), default="manual"
    )
    datos_resueltos = db.Column(db.JSON)
    resuelto_por = db.Column(db.Integer)
    fecha_resolucion = db.Column(db.DateTime)
    notas_resolucion = db.Column(db.Text)
    notificado = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.Index("idx_estado_resolucion", "estado_resolucion"),
        db.Index("idx_tabla_registro", "tabla_afectada", "registro_id"),
    )

    def to_dict(self):
        return {
            "id_conflicto": self.id_conflicto,
            "tabla_afectada": self.tabla_afectada,
            "registro_id": self.registro_id,
            "tipo_conflicto": self.tipo_conflicto,
            "estado_resolucion": self.estado_resolucion,
            "resolucion_tipo": self.resolucion_tipo,
            "timestamp_local": self.timestamp_local.isoformat() if self.timestamp_local else None,
            "timestamp_remoto": self.timestamp_remoto.isoformat()
            if self.timestamp_remoto
            else None,
            "usuario_local": self.usuario_local,
            "usuario_remoto": self.usuario_remoto,
            "datos_local": self.datos_local,
            "datos_remoto": self.datos_remoto,
            "notas_resolucion": self.notas_resolucion,
            "timestamp_deteccion": self.timestamp_deteccion.isoformat()
            if self.timestamp_deteccion
            else None,
        }


class SyncMetadata(db.Model):
    """Marca de agua por tabla: hasta donde se sincronizo."""

    __tablename__ = "sync_metadata"

    id = db.Column(db.Integer, primary_key=True)
    tabla_nombre = db.Column(db.String(100), nullable=False, unique=True)
    ultima_sincronizacion = db.Column(db.DateTime)
    ultimo_pull = db.Column(db.DateTime)
    ultimo_push = db.Column(db.DateTime)
    version_remota = db.Column(db.Integer, default=0)
    version_local = db.Column(db.Integer, default=0)
    registros_sincronizados = db.Column(db.Integer, default=0)
    estado = db.Column(db.Enum("sincronizado", "pendiente", "error"), default="pendiente")
    mensaje = db.Column(db.Text)

    def to_dict(self):
        return {
            "tabla_nombre": self.tabla_nombre,
            "ultima_sincronizacion": self.ultima_sincronizacion.isoformat()
            if self.ultima_sincronizacion
            else None,
            "ultimo_pull": self.ultimo_pull.isoformat() if self.ultimo_pull else None,
            "ultimo_push": self.ultimo_push.isoformat() if self.ultimo_push else None,
            "registros_sincronizados": self.registros_sincronizados,
            "estado": self.estado,
            "mensaje": self.mensaje,
        }
