"""Resolucion de conflictos de sincronizacion.

Regla de negocio definida por el cliente:
  Si dos usuarios venden la ULTIMA unidad de un producto (uno offline y otro
  en la nube), gana la venta con el timestamp MENOR (la que ocurrio primero).
  La otra venta se ANULA y se notifica al usuario perdedor con el mensaje
  "El ultimo producto ha sido vendido".
"""
import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text

from app.extensions import db
from app.models.sync import ConflictLog, SyncQueue
from app.models.venta import Venta
from app.models.notificacion import Notificacion
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("sync.conflict")

MENSAJE_AGOTADO = "El ultimo producto ha sido vendido"


def _parse_ts(valor):
    if isinstance(valor, datetime):
        return valor
    if not valor:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(str(valor)[:26], fmt)
        except ValueError:
            continue
    return None


class ConflictService:

    # =================================================================
    # DETECCION durante el PUSH
    # =================================================================
    @staticmethod
    def verificar_venta_remota(conn, op):
        """Antes de subir una venta local, revisa si la nube ya no tiene stock.

        Devuelve el ConflictLog creado si hay conflicto, o None si puede subir.
        """
        venta = Venta.query.get(op.registro_id)
        if not venta or venta.estado == "anulada":
            return None

        faltantes = []
        for det in venta.detalles:
            requerido = ConflictService._requerimiento_total(det.id_producto, det.cantidad)
            for id_producto, cantidad in requerido.items():
                fila = conn.execute(
                    text(
                        "SELECT stock_actual FROM inventario "
                        "WHERE id_producto = :p ORDER BY id_inventario LIMIT 1"
                    ),
                    {"p": id_producto},
                ).mappings().first()
                stock_remoto = Decimal(str(fila["stock_actual"])) if fila else Decimal("0")
                if stock_remoto < Decimal(str(cantidad)):
                    faltantes.append(
                        {
                            "id_producto": id_producto,
                            "requerido": float(cantidad),
                            "stock_remoto": float(stock_remoto),
                        }
                    )

        if not faltantes:
            return None

        # Busca la venta remota que dejo el stock en cero para comparar tiempos.
        ts_local = venta.timestamp_local_creacion or venta.fecha_venta
        remota = conn.execute(
            text(
                "SELECT v.id_venta, v.fecha_venta, v.id_usuario, v.numero_venta "
                "FROM ventas v JOIN detalle_ventas d ON d.id_venta = v.id_venta "
                "WHERE d.id_producto = :p AND v.estado = 'completada' "
                "ORDER BY v.fecha_venta DESC LIMIT 1"
            ),
            {"p": faltantes[0]["id_producto"]},
        ).mappings().first()

        ts_remoto = _parse_ts(remota["fecha_venta"]) if remota else None

        conflicto = ConflictLog(
            tabla_afectada="ventas",
            registro_id=venta.id_venta,
            id_empresa=venta.id_empresa or 1,
            datos_local={
                "id_venta": venta.id_venta,
                "numero_venta": venta.numero_venta,
                "total": float(venta.total or 0),
                "faltantes": faltantes,
            },
            timestamp_local=ts_local,
            usuario_local=venta.id_usuario,
            datos_remoto={
                "id_venta": remota["id_venta"] if remota else None,
                "numero_venta": remota["numero_venta"] if remota else None,
            }
            if remota
            else {},
            timestamp_remoto=ts_remoto,
            usuario_remoto=remota["id_usuario"] if remota else None,
            tipo_conflicto="venta_simultanea",
            estado_resolucion="pendiente_resolucion",
        )
        db.session.add(conflicto)
        db.session.commit()
        log.info("Conflicto detectado en venta local #%s", venta.id_venta)
        return conflicto

    # -----------------------------------------------------------------
    @staticmethod
    def _requerimiento_total(id_producto, cantidad):
        """Cantidad real de inventario que consume vender `cantidad` de un producto.

        Si el producto es receta devuelve el consumo de cada insumo; si no,
        devuelve el propio producto.
        """
        from app.models.producto import Producto
        from app.models.receta import Receta

        requerido = {}
        producto = Producto.query.get(id_producto)
        if not producto:
            return {id_producto: Decimal(str(cantidad))}

        if producto.es_receta:
            receta = Receta.query.filter_by(id_producto=id_producto, estado="activo").first()
            if receta:
                rendimiento = Decimal(str(receta.rendimiento or 1)) or Decimal("1")
                for ing in receta.ingredientes:
                    consumo = (
                        Decimal(str(ing.cantidad_necesaria)) * Decimal(str(cantidad)) / rendimiento
                    )
                    requerido[ing.id_producto] = requerido.get(
                        ing.id_producto, Decimal("0")
                    ) + consumo
                return requerido

        requerido[id_producto] = Decimal(str(cantidad))
        return requerido

    # =================================================================
    # RESOLUCION
    # =================================================================
    @classmethod
    def resolver_pendientes(cls):
        resultado = {"resueltos": 0, "gano_local": 0, "gano_remoto": 0, "detalle": []}
        pendientes = ConflictLog.query.filter_by(
            estado_resolucion="pendiente_resolucion"
        ).all()

        for c in pendientes:
            if c.tipo_conflicto == "venta_simultanea":
                res = cls.resolve_concurrent_sale(c.id_conflicto)
            else:
                res = cls.resolve_generic(c.id_conflicto)
            if res:
                resultado["resueltos"] += 1
                if res.get("ganador") == "local":
                    resultado["gano_local"] += 1
                else:
                    resultado["gano_remoto"] += 1
                resultado["detalle"].append(res)

        return resultado

    # -----------------------------------------------------------------
    @classmethod
    def resolve_concurrent_sale(cls, conflict_id):
        """Gana el timestamp MENOR. El perdedor se anula y se le notifica."""
        c = ConflictLog.query.get(conflict_id)
        if not c or c.estado_resolucion != "pendiente_resolucion":
            return None

        ts_local = c.timestamp_local
        ts_remoto = c.timestamp_remoto

        # Sin timestamp remoto no podemos comparar: la nube es la fuente de
        # verdad del stock, asi que la venta local pierde.
        gana_local = bool(ts_local and ts_remoto and ts_local < ts_remoto)

        if gana_local:
            c.resolucion_tipo = "prioridad_local"
            c.notas_resolucion = (
                "La venta local ocurrio primero ({}). Se mantiene y se fuerza el "
                "envio a la nube; la venta remota queda anulada.".format(ts_local)
            )
            cls._anular_venta_remota(c)
            cls._reencolar_venta_local(c)
            ganador = "local"
        else:
            c.resolucion_tipo = "prioridad_remoto"
            c.notas_resolucion = (
                "La venta remota ocurrio primero. Se anula la venta local por "
                "falta de existencias."
            )
            cls._anular_venta_local(c)
            ganador = "remoto"

        c.estado_resolucion = "resuelto_auto"
        c.fecha_resolucion = nicaragua_now()
        c.datos_resueltos = {"ganador": ganador}
        db.session.commit()

        log.info("Conflicto #%s resuelto: gana %s", conflict_id, ganador)
        return {"conflicto": conflict_id, "ganador": ganador, "tipo": "venta_simultanea"}

    # -----------------------------------------------------------------
    @staticmethod
    def _anular_venta_local(c):
        from app.services.inventario_service import InventarioService

        venta = Venta.query.get(c.registro_id)
        if not venta or venta.estado == "anulada":
            return
        venta.estado = "anulada"
        venta.motivo_anulacion = MENSAJE_AGOTADO
        venta.estado_sync = "sinc_remoto"

        # Devuelve al inventario local lo que la venta habia descontado.
        InventarioService.revertir_venta(venta, motivo="Anulada por conflicto de sincronizacion")

        # Marca la operacion en cola como resuelta para que no reintente.
        SyncQueue.query.filter_by(
            tabla_afectada="ventas", registro_id=venta.id_venta
        ).update({"estado_sync": "resuelto"})

        ConflictService._notificar(
            venta.id_usuario,
            titulo="Venta anulada",
            mensaje=(
                MENSAJE_AGOTADO
                + ". La venta "
                + str(venta.numero_venta or venta.id_venta)
                + " fue anulada porque otro usuario vendio la ultima existencia antes."
            ),
            tipo="error",
        )
        c.notificado = True
        db.session.commit()

    # -----------------------------------------------------------------
    @staticmethod
    def _anular_venta_remota(c):
        """Anula en la nube la venta perdedora y notifica a su usuario."""
        datos = c.datos_remoto or {}
        id_remoto = datos.get("id_venta")
        if not id_remoto:
            return
        try:
            engine = db.engines.get("cloud")
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE ventas SET estado = 'anulada', motivo_anulacion = :m "
                        "WHERE id_venta = :id"
                    ),
                    {"m": MENSAJE_AGOTADO, "id": id_remoto},
                )
                if c.usuario_remoto:
                    conn.execute(
                        text(
                            "INSERT INTO notificaciones "
                            "(id_empresa, id_usuario, titulo, mensaje, tipo, leida) "
                            "VALUES (:e, :u, :t, :m, 'error', 0)"
                        ),
                        {
                            "e": c.id_empresa or 1,
                            "u": c.usuario_remoto,
                            "t": "Venta anulada",
                            "m": MENSAJE_AGOTADO
                            + ". Otro punto de venta registro la venta antes que usted.",
                        },
                    )
        except Exception:  # noqa: BLE001
            log.exception("No se pudo anular la venta remota #%s", id_remoto)

    # -----------------------------------------------------------------
    @staticmethod
    def _reencolar_venta_local(c):
        SyncQueue.query.filter_by(
            tabla_afectada="ventas", registro_id=c.registro_id
        ).update({"estado_sync": "pendiente", "intentos": 0})
        db.session.commit()

    # -----------------------------------------------------------------
    @classmethod
    def resolve_generic(cls, conflict_id):
        """Conflictos no-venta: gana el timestamp menor."""
        c = ConflictLog.query.get(conflict_id)
        if not c:
            return None
        gana_local = bool(
            c.timestamp_local and c.timestamp_remoto and c.timestamp_local < c.timestamp_remoto
        )
        c.resolucion_tipo = "prioridad_local" if gana_local else "prioridad_remoto"
        c.estado_resolucion = "resuelto_auto"
        c.fecha_resolucion = nicaragua_now()
        c.datos_resueltos = {"ganador": "local" if gana_local else "remoto"}
        db.session.commit()
        return {
            "conflicto": conflict_id,
            "ganador": "local" if gana_local else "remoto",
            "tipo": c.tipo_conflicto,
        }

    # -----------------------------------------------------------------
    @classmethod
    def resolver_manual(cls, conflict_id, resolucion, usuario_id, notas=None):
        c = ConflictLog.query.get(conflict_id)
        if not c:
            return None
        if resolucion == "prioridad_remoto":
            cls._anular_venta_local(c)
        elif resolucion == "prioridad_local":
            cls._anular_venta_remota(c)
            cls._reencolar_venta_local(c)
        c.resolucion_tipo = resolucion
        c.estado_resolucion = "resuelto_manual"
        c.resuelto_por = usuario_id
        c.fecha_resolucion = nicaragua_now()
        c.notas_resolucion = notas
        db.session.commit()
        return c.to_dict()

    # -----------------------------------------------------------------
    @staticmethod
    def _notificar(id_usuario, titulo, mensaje, tipo="info", url=None):
        from flask import current_app

        n = Notificacion(
            id_empresa=current_app.config.get("ID_EMPRESA", 1),
            id_usuario=id_usuario,
            titulo=titulo,
            mensaje=mensaje,
            tipo=tipo,
            url_accion=url,
        )
        db.session.add(n)
        db.session.commit()

        try:
            from app.extensions import socketio

            socketio.emit(
                "notificacion",
                n.to_dict(),
                to="usuario_" + str(id_usuario) if id_usuario else None,
            )
        except Exception:  # noqa: BLE001
            pass
        return n
