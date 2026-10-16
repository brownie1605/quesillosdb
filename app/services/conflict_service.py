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

        requerido, ya_descontado = ConflictService._consumo_de_venta(conn, venta)
        faltantes = []
        for id_producto, cantidad in requerido.items():
            fila = conn.execute(
                text(
                    "SELECT stock_actual FROM inventario "
                    "WHERE id_producto = :p ORDER BY id_inventario LIMIT 1"
                ),
                {"p": id_producto},
            ).mappings().first()

            # Sin fila de inventario remota el producto todavia no se ha
            # subido. Eso no es un conflicto: la propia cola lo creara.
            if fila is None:
                continue

            # El stock viaja como movimientos y los de esta venta pueden
            # haber subido antes que ella: lo que ya desconto alla no cuenta
            # en su contra.
            stock_remoto = (
                Decimal(str(fila["stock_actual"]))
                + ya_descontado.get(id_producto, Decimal("0"))
            )
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
    def _consumo_de_venta(conn, venta):
        """({producto: cantidad que consume la venta},
            {producto: cuanto de eso ya se desconto en la nube}).

        Sale de los movimientos que la venta registro al cobrarse (incluye
        opciones elegidas e ingredientes quitados). Una venta sin
        movimientos registrados se calcula con la receta, como antes.
        """
        from app.models.movimiento_inventario import MovimientoInventario
        from app.services.sync_service import _delta_movimiento

        movimientos = MovimientoInventario.query.filter_by(
            referencia="VENTA-" + str(venta.id_venta)
        ).all()
        if not movimientos:
            requerido = {}
            for det in venta.detalles:
                for id_producto, cantidad in ConflictService._requerimiento_total(
                    det.id_producto, det.cantidad
                ).items():
                    requerido[id_producto] = requerido.get(id_producto, Decimal("0")) + cantidad
            return requerido, {}

        def delta(m):
            return _delta_movimiento({"stock_nuevo": m.stock_nuevo, "stock_anterior": m.stock_anterior})

        neto = {}
        for m in movimientos:
            neto[m.id_producto] = neto.get(m.id_producto, Decimal("0")) + delta(m)
        requerido = {p: -d for p, d in neto.items() if d < 0}

        ids = [m.id_movimiento for m in movimientos]
        marcas = ", ".join(":m" + str(i) for i in range(len(ids)))
        en_nube = {
            r[0] for r in conn.execute(
                text("SELECT id_movimiento FROM movimientos_inventario "
                     "WHERE id_movimiento IN (" + marcas + ")"),
                {"m" + str(i): v for i, v in enumerate(ids)},
            )
        }
        ya_descontado = {}
        for m in movimientos:
            if m.id_movimiento in en_nube:
                ya_descontado[m.id_producto] = ya_descontado.get(m.id_producto, Decimal("0")) - delta(m)
        return requerido, ya_descontado

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

        # La venta se sube igual, ya anulada (una venta anulada no vuelve a
        # chocar): asi la nube la registra y sus lineas de detalle, que
        # tambien estan en cola, encuentran a su venta alla. Antes se
        # marcaba como resuelta y nunca subia, y esas lineas fallaban para
        # siempre por llave foranea.
        SyncQueue.query.filter_by(
            tabla_afectada="ventas", registro_id=venta.id_venta
        ).update({"estado_sync": "pendiente", "intentos": 0})

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
        """Anula en la nube la venta perdedora y notifica a su usuario.

        Ademas le devuelve al stock de la nube lo que esa venta desconto
        (sus propios movimientos dicen cuanto) y deja todo en el registro de
        cambios de la nube, para que el restaurante tambien la vea anulada y
        reciba la devolucion. Antes solo se cambiaba el estado: el stock de
        la nube quedaba descontado y la venta local volvia a chocar.
        """
        from app.services.sync_service import _delta_movimiento

        datos = c.datos_remoto or {}
        id_remoto = datos.get("id_venta")
        if not id_remoto:
            return
        try:
            engine = db.engines.get("cloud")
            ahora = nicaragua_now()
            referencia = "VENTA-" + str(id_remoto)
            with engine.begin() as conn:
                estado = conn.execute(
                    text("SELECT estado FROM ventas WHERE id_venta = :id"), {"id": id_remoto}
                ).scalar()
                if estado is None or estado == "anulada":
                    return
                conn.execute(
                    text(
                        "UPDATE ventas SET estado = 'anulada', motivo_anulacion = :m, "
                        "timestamp_local_actualizacion = :ahora WHERE id_venta = :id"
                    ),
                    {"m": MENSAJE_AGOTADO, "id": id_remoto, "ahora": ahora},
                )
                ConflictService._registrar_cambio_nube(conn, "UPDATE", "ventas", id_remoto, ahora)

                neto, dueno = {}, {}
                for m in conn.execute(
                    text(
                        "SELECT id_producto, id_empresa, id_sucursal, id_usuario, "
                        "stock_anterior, stock_nuevo FROM movimientos_inventario "
                        "WHERE referencia = :r"
                    ),
                    {"r": referencia},
                ).mappings().all():
                    neto[m["id_producto"]] = neto.get(m["id_producto"], Decimal("0")) + _delta_movimiento(m)
                    dueno[m["id_producto"]] = m
                for id_producto, total in neto.items():
                    if total >= 0:
                        continue
                    inv = conn.execute(
                        text(
                            "SELECT id_inventario, stock_actual FROM inventario "
                            "WHERE id_producto = :p ORDER BY id_inventario LIMIT 1 FOR UPDATE"
                        ),
                        {"p": id_producto},
                    ).mappings().first()
                    if inv is None:
                        continue
                    anterior = Decimal(str(inv["stock_actual"]))
                    nuevo = anterior - total
                    conn.execute(
                        text(
                            "UPDATE inventario SET stock_actual = :n, fecha_actualizacion = :ahora "
                            "WHERE id_inventario = :i"
                        ),
                        {"n": nuevo, "ahora": ahora, "i": inv["id_inventario"]},
                    )
                    m = dueno[id_producto]
                    mov = conn.execute(
                        text(
                            "INSERT INTO movimientos_inventario (id_empresa, id_sucursal, "
                            "id_producto, id_usuario, tipo_movimiento, cantidad, stock_anterior, "
                            "stock_nuevo, referencia, observacion, fecha_movimiento, "
                            "timestamp_operacion, estado_sync) VALUES (:e, :s, :p, :u, "
                            "'devolucion', :c, :a, :n, :r, :o, :ahora, :ahora, 'sinc_remoto')"
                        ),
                        {
                            "e": m["id_empresa"], "s": m["id_sucursal"], "p": id_producto,
                            "u": m["id_usuario"], "c": -total, "a": anterior, "n": nuevo,
                            "r": referencia, "o": "Anulada por conflicto de sincronizacion",
                            "ahora": ahora,
                        },
                    )
                    ConflictService._registrar_cambio_nube(
                        conn, "INSERT", "movimientos_inventario", mov.lastrowid, ahora
                    )

                if c.usuario_remoto:
                    notif = conn.execute(
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
                    ConflictService._registrar_cambio_nube(
                        conn, "INSERT", "notificaciones", notif.lastrowid, ahora
                    )
        except Exception:  # noqa: BLE001
            log.exception("No se pudo anular la venta remota #%s", id_remoto)

    # -----------------------------------------------------------------
    @staticmethod
    def _registrar_cambio_nube(conn, operacion, tabla, registro_id, ahora):
        """Anota en el registro de cambios de la nube algo que se escribio
        alla directamente, para que el restaurante lo baje en su pull."""
        from flask import current_app

        conn.execute(
            text(
                "INSERT INTO sync_queue (operation_type, tabla_afectada, registro_id, "
                "id_empresa, timestamp_operacion, timestamp_sincronizacion, estado_sync, "
                "dispositivo_origen, intentos, fecha_creacion) VALUES "
                "(:op, :t, :r, :e, :ahora, :ahora, 'sinc_remoto', 'nube-conflicto', 0, :ahora)"
            ),
            {
                "op": operacion, "t": tabla, "r": registro_id, "ahora": ahora,
                "e": current_app.config.get("ID_EMPRESA", 1),
            },
        )

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
