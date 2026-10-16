"""Sincronizacion bidireccional MySQL local <-> MySQL nube (Railway).

Estrategia:
  * La aplicacion escribe SIEMPRE en la BD local (funciona sin internet).
  * Cada operacion relevante se encola en `sync_queue` -- tanto en el
    restaurante como en la nube: en la nube esa cola es el REGISTRO DE
    CAMBIOS que los nodos locales leen para enterarse de lo que se hizo
    en la web (incluidos los borrados).
  * PUSH (primero): sube las operaciones pendientes del restaurante y deja
    constancia de cada una en el registro de cambios de la nube.
  * PULL (despues): baja, en orden, todo lo que el registro de cambios de
    la nube tenga despues del cursor de este nodo (`sync_cursor`).
  * El stock no viaja como numero fijo sino como movimientos: cada
    movimiento nuevo suma o resta su diferencia en el otro lado.
  * Si la misma fila cambio en los dos lados, gana la version mas reciente
    (para las tablas con fecha de modificacion); una venta anulada se queda
    anulada.
  * La instalacion en modo "nube" (Railway) no sube ni baja nada.
  * Los conflictos de venta simultanea se delegan a ConflictService.
"""
import json
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.extensions import db
from app.models.sync import SyncQueue, ConflictLog, SyncMetadata
from app.services.network_service import NetworkService
from app.utils.date_utils import nicaragua_now

log = logging.getLogger("sync.service")

# Cache de columnas remotas por tabla (se llena en el primer push).
_COLUMNAS_REMOTAS = {}

# Que tablas locales tienen columna estado_sync.
_CON_ESTADO_SYNC = {}

# Orden de sincronizacion: respeta dependencias de claves foraneas.
TABLAS_SYNC = [
    "roles",
    "usuarios",
    "categorias",
    "unidades_medida",
    "proveedores",
    "clientes",
    "mesas",
    "productos",
    "recetas",
    "receta_ingredientes",
    "receta_opciones_grupo",
    "receta_opciones_item",
    "inventario",
    "ventas",
    "detalle_ventas",
    "movimientos_inventario",
    "compras",
    "detalle_compras",
    "notificaciones",
    "cajas",
    "aperturas_caja",
    "movimientos_caja",
    "cierres_caja",
]

# Clave primaria de cada tabla sincronizable.
PK_POR_TABLA = {
    "roles": "id_rol",
    "usuarios": "id_usuario",
    "categorias": "id_categoria",
    "unidades_medida": "id_unidad",
    "proveedores": "id_proveedor",
    "clientes": "id_cliente",
    "mesas": "id_mesa",
    "productos": "id_producto",
    "recetas": "id_receta",
    "receta_ingredientes": "id_ingrediente",
    "receta_opciones_grupo": "id_grupo",
    "receta_opciones_item": "id_item",
    "inventario": "id_inventario",
    "ventas": "id_venta",
    "detalle_ventas": "id_detalle_venta",
    "movimientos_inventario": "id_movimiento",
    "compras": "id_compra",
    "detalle_compras": "id_detalle_compra",
    "notificaciones": "id_notificacion",
    "cajas": "id_caja",
    "aperturas_caja": "id_apertura",
    "movimientos_caja": "id_movimiento_caja",
    "cierres_caja": "id_cierre",
}

# Columna de marca temporal usada por el PULL para saber que filas de una
# tabla son "nuevas desde la ultima vez" (WHERE col_ts > ultimo_pull).
#
# Auditoria H-04: "ventas" usaba `fecha_venta`, que es la fecha en que se
# hizo la venta y NUNCA cambia despues -- ni al anularla ni al editar su
# cliente/metodo de pago (esos solo tocan `timestamp_local_actualizacion`).
# Efecto: si el push inmediato de una anulacion/edicion llegaba a fallar
# (ver H-05/H-06), NINGUN pull futuro la iba a recuperar, porque para el
# filtro por `fecha_venta` esa fila ya habia quedado "vieja" desde su
# creacion. Con `timestamp_local_actualizacion` (que se fija tanto al
# crear como en cada anulacion/edicion -- ver venta_service.py) el pull SI
# puede volver a ver la fila si algo la cambio despues de la ultima vez
# que se sincronizo, sin depender de que el push inmediato nunca falle.
#
# Se confirmo que `fecha_venta` solo se usa en otro lado del pipeline de
# sync (`conflict_service.verificar_venta_remota`, para detectar VENTAS
# NUEVAS conflictivas por producto/tiempo) -- ese uso es independiente del
# watermark del pull y no se toca aqui.
TIMESTAMP_POR_TABLA = {
    "usuarios": "fecha_creacion",
    "productos": "fecha_actualizacion",
    "recetas": "fecha_actualizacion",
    "inventario": "fecha_actualizacion",
    "ventas": "timestamp_local_actualizacion",
    "movimientos_inventario": "fecha_movimiento",
    "compras": "fecha_compra",
    "notificaciones": "fecha_creacion",
}


# Tablas con una fecha de "ultima modificacion" que la app mantiene al dia:
# si la misma fila cambio en los dos lados entre una sincronizacion y la
# siguiente, gana la version mas reciente, en las dos direcciones. En el
# resto de tablas gana lo que llegue primero a la nube (el restaurante sube
# antes de bajar).
TS_ACTUALIZACION = {
    "ventas": "timestamp_local_actualizacion",
    "productos": "fecha_actualizacion",
    "recetas": "fecha_actualizacion",
}

# Nombre del cursor de este nodo sobre el registro de cambios de la nube.
CURSOR_NUBE = "nube"
# Cuantos cambios ya aplicados se vuelven a revisar en cada ciclo: una
# transaccion de la nube que tardo en confirmarse puede quedar con un id
# menor que otro cambio que ya se bajo. Reaplicar es seguro (todo es
# idempotente) y evita perder ese cambio.
VENTANA_SOLAPE = 50
LOTE_PULL = 500
MAX_LOTES_PULL = 20
# Marca en sync_metadata (de la nube) con el mayor id ya borrado del
# registro de cambios por retencion (ver `podar_registro`).
META_PODA = "__poda_cola__"


def _delta_movimiento(fila):
    """Cuanto cambio el stock con este movimiento (+ entrada, - salida).

    `cantidad` se guarda siempre en positivo; el signo real sale de
    stock_nuevo - stock_anterior, que es exactamente lo que `mover()` aplico.
    """
    try:
        return Decimal(str(fila["stock_nuevo"])) - Decimal(str(fila["stock_anterior"]))
    except (KeyError, TypeError, ArithmeticError):
        return Decimal("0")


def _valor_sql(value):
    """Valor listo para un bind de SQL directo (sin perder precision)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return value


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (bytes, bytearray)):
        return None  # las imagenes binarias no viajan en el payload
    if isinstance(value, (dict, list)):
        # Columnas JSON (ej. detalle_ventas.personalizacion): pymysql las
        # devuelve ya decodificadas como dict/list, pero un bind param de
        # SQL no acepta eso directamente -- hay que volver a mandarlas como
        # texto JSON para que la columna remota las reciba bien.
        return json.dumps(value, default=str)
    return value


def _row_to_dict(row_mapping):
    return {k: _json_safe(v) for k, v in dict(row_mapping).items()}


def _parse_ts(value):
    """Convierte a `datetime` un valor de timestamp que puede venir como
    `datetime` (de una fila leida via ORM/driver) o como string (de un
    payload ya serializado, ver `_json_safe`). Usado por la resolucion de
    conflictos del pull (H-05) para poder comparar "cual es mas nuevo"."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def checksum(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class SyncService:
    """Motor de sincronizacion. Todos los metodos requieren app context."""

    _running = threading.Lock()

    # =================================================================
    # ENCOLADO
    # =================================================================
    @staticmethod
    def encolar(tabla, registro_id, operacion="INSERT", payload=None,
                usuario_id=None, timestamp=None, commit=True):
        """Registra una operacion local pendiente de subir a la nube."""
        from flask import current_app

        payload = payload or {}
        item = SyncQueue(
            operation_type=operacion,
            tabla_afectada=tabla,
            registro_id=registro_id,
            id_empresa=current_app.config.get("ID_EMPRESA", 1),
            timestamp_operacion=timestamp or nicaragua_now(),
            estado_sync="pendiente",
            payload=payload,
            usuario_origen=usuario_id,
            dispositivo_origen=current_app.config.get("DEVICE_ID", "local-01"),
            checksum_datos=checksum(payload) if payload else None,
        )
        db.session.add(item)
        if commit:
            db.session.commit()
        return item

    # =================================================================
    # PUSH  (local -> nube)
    # =================================================================
    @classmethod
    def push_pending_operations(cls, limite=None):
        from flask import current_app
        from app.services.conflict_service import ConflictService

        resultado = {"enviados": 0, "conflictos": 0, "errores": 0, "descartados": 0, "detalle": []}
        if cls._es_nube():
            resultado["mensaje"] = "Esta instalacion es la nube: no tiene nada que subir"
            return resultado
        if not NetworkService.is_online():
            resultado["mensaje"] = "Sin conexion: push omitido"
            return resultado

        limite = limite or current_app.config.get("SYNC_BATCH_SIZE", 200)
        engine = db.engines.get("cloud")

        pendientes = (
            SyncQueue.query.filter(SyncQueue.estado_sync.in_(["pendiente", "error"]))
            .order_by(SyncQueue.timestamp_operacion.asc(), SyncQueue.id_sync_queue.asc())
            .limit(limite)
            .all()
        )

        # Ordena por prioridad de tabla para no romper llaves foraneas.
        orden = {t: i for i, t in enumerate(TABLAS_SYNC)}
        pendientes.sort(key=lambda x: (orden.get(x.tabla_afectada, 99), x.timestamp_operacion))

        for op in pendientes:
            try:
                with engine.begin() as conn:
                    if op.tabla_afectada == "ventas" and op.operation_type == "INSERT":
                        conflicto = ConflictService.verificar_venta_remota(conn, op)
                        if conflicto:
                            op.estado_sync = "en_conflicto"
                            resultado["conflictos"] += 1
                            db.session.commit()
                            continue
                    aplicado = cls._aplicar_en_remoto(conn, op)
                    if aplicado:
                        # Constancia en el registro de cambios de la nube,
                        # para que otros equipos (una segunda caja) lo bajen.
                        cls._registrar_en_nube(conn, op)

                op.estado_sync = "sinc_remoto"
                op.timestamp_sincronizacion = nicaragua_now()
                op.ultimo_error = None
                if not aplicado:
                    op.ultimo_error = (
                        "No se subio: la nube ya tenia ese dato o una version mas reciente"
                    )
                    resultado["descartados"] += 1
                resultado["enviados"] += 1
                cls._marcar_registro_sincronizado(op)
                db.session.commit()
            except Exception as exc:  # noqa: BLE001
                db.session.rollback()
                op.intentos = (op.intentos or 0) + 1
                op.ultimo_error = str(exc)[:1000]
                op.estado_sync = "error" if op.intentos < 5 else "en_conflicto"
                db.session.commit()
                resultado["errores"] += 1
                resultado["detalle"].append(
                    {"id": op.id_sync_queue, "tabla": op.tabla_afectada, "error": str(exc)[:200]}
                )
                log.warning("Push fallo (%s#%s): %s", op.tabla_afectada, op.registro_id, exc)

        cls._actualizar_metadata("push", resultado["enviados"])
        return resultado

    # -----------------------------------------------------------------
    @staticmethod
    def _columnas_remotas(conn, tabla):
        """{columna: admite_null} de la tabla remota (cache por proceso)."""
        if tabla not in _COLUMNAS_REMOTAS:
            filas = conn.execute(
                text(
                    "SELECT COLUMN_NAME, IS_NULLABLE FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                ),
                {"t": tabla},
            ).mappings().all()
            _COLUMNAS_REMOTAS[tabla] = {
                f["COLUMN_NAME"]: f["IS_NULLABLE"] == "YES" for f in filas
            }
        return _COLUMNAS_REMOTAS[tabla]

    # -----------------------------------------------------------------
    @staticmethod
    def _fila_local_actual(tabla, registro_id):
        """Estado actual completo de la fila en la base local.

        El payload encolado puede ser parcial (p. ej. un UPDATE que solo toca
        un campo). Si esa fila todavia no existe en la nube, un INSERT parcial
        falla por columnas NOT NULL. Por eso se sube siempre la fila completa.
        """
        pk = PK_POR_TABLA.get(tabla)
        if not pk:
            return None
        try:
            fila = db.session.execute(
                text("SELECT * FROM " + tabla + " WHERE " + pk + " = :pk"),
                {"pk": registro_id},
            ).mappings().first()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return None
        if not fila:
            return None
        # Las imagenes no viajan en la sincronizacion: pesan cientos de KB y
        # la conexion del local es intermitente.
        return {
            k: _json_safe(v) for k, v in dict(fila).items()
            if not isinstance(v, (bytes, bytearray))
        }

    # -----------------------------------------------------------------
    @classmethod
    def _aplicar_en_remoto(cls, conn, op):
        """Ejecuta la operacion de `op` sobre la conexion remota.

        Devuelve False si no se aplico porque no hacia falta: la nube ya
        tiene una version mas reciente de esa fila (TS_ACTUALIZACION), la
        venta ya esta anulada alla, o el movimiento ya estaba subido. Lo
        que la nube tenga de mas nuevo lo baja el pull.
        """
        tabla = op.tabla_afectada
        pk = PK_POR_TABLA.get(tabla, "id")

        if op.operation_type == "DELETE":
            conn.execute(text("DELETE FROM " + tabla + " WHERE " + pk + " = :pk"),
                         {"pk": op.registro_id})
            return True

        # Fila completa tal como esta hoy aqui (incluidas las imagenes); si
        # ya no existe, lo que se encolo en su momento.
        fila = cls._fila_local_completa(tabla, op.registro_id)
        payload = fila if fila is not None else dict(op.payload or {})
        payload.setdefault(pk, op.registro_id)

        if tabla == "movimientos_inventario":
            return cls._subir_movimiento(conn, payload)

        # Solo columnas que la nube realmente tiene.
        columnas_remotas = cls._columnas_remotas(conn, tabla)
        if columnas_remotas:
            payload = {k: v for k, v in payload.items() if k in columnas_remotas}

        binarias = [k for k, v in payload.items() if isinstance(v, (bytes, bytearray))]
        remota = cls._fila_remota_para_comparar(conn, tabla, pk, op.registro_id, binarias)

        if remota is not None:
            anulando = tabla == "ventas" and payload.get("estado") == "anulada"
            # Una venta anulada en la nube se queda anulada.
            if tabla == "ventas" and remota.get("estado") == "anulada" and not anulando:
                return False
            # Si la nube cambio esa fila despues que aqui, gana la nube.
            col_ts = TS_ACTUALIZACION.get(tabla)
            if col_ts and not anulando:
                ts_local = _parse_ts(payload.get(col_ts))
                ts_remoto = _parse_ts(remota.get(col_ts))
                if ts_local and ts_remoto and ts_remoto > ts_local:
                    return False
            # Las imagenes pesan: solo viajan si cambiaron.
            for col in binarias:
                if remota.get("md5_" + col) == hashlib.md5(payload[col]).hexdigest():
                    payload.pop(col)

        if tabla == "inventario":
            # El stock viaja como movimientos (ver _subir_movimiento): aqui
            # solo los demas datos. Una fila nueva arranca en 0 y la llenan
            # los movimientos que vienen detras en la misma cola.
            if remota is not None:
                payload.pop("stock_actual", None)
            else:
                payload["stock_actual"] = 0

        # Una actualizacion sube solo las columnas que cambiaron aqui (las
        # anota sync_events): lo que la web haya cambiado en OTRAS columnas
        # de la misma fila se conserva (p. ej. iniciar sesion aqui toca el
        # ultimo acceso del usuario y no debe revertir un PIN cambiado en la
        # web). Si la fila aun no existe alla, va completa.
        cambios = (op.payload or {}).get("__cambios__") if op.operation_type == "UPDATE" else None
        parcial = cambios is not None and remota is not None
        if parcial:
            # Las fechas de modificacion van siempre: la app las pone al
            # guardar y, si no se mandan, MySQL de la nube pone su propia
            # hora (UTC) en las columnas con ON UPDATE CURRENT_TIMESTAMP.
            conservar = set(cambios) | {pk} | {
                c for c in ("fecha_actualizacion", "timestamp_local_actualizacion") if c in payload
            }
            payload = {k: v for k, v in payload.items() if k in conservar}

        if columnas_remotas.get("estado_sync") is not None:
            payload["estado_sync"] = "sinc_remoto"

        if parcial:
            # UPDATE y no INSERT ... ON DUPLICATE KEY: MySQL estricto exige
            # todas las columnas NOT NULL en el INSERT aunque la fila exista.
            valores = {k: _valor_sql(v) for k, v in payload.items()}
            asignaciones = ", ".join("`" + c + "` = :" + c for c in valores if c != pk)
            if asignaciones:
                conn.execute(
                    text("UPDATE " + tabla + " SET " + asignaciones + " WHERE `" + pk + "` = :" + pk),
                    valores,
                )
            return True

        # Un NULL se envia tal cual si la columna remota lo admite (asi se
        # propaga el borrado de un campo). Si es NOT NULL se omite para que
        # actue el valor por defecto de la nube en vez de fallar.
        payload = {
            k: _valor_sql(v) for k, v in payload.items()
            if v is not None or k == pk or columnas_remotas.get(k, True)
        }

        columnas = ", ".join("`" + c + "`" for c in payload)
        binds = ", ".join(":" + c for c in payload)
        updates = ", ".join("`" + c + "` = VALUES(`" + c + "`)" for c in payload if c != pk)

        sql = "INSERT INTO " + tabla + " (" + columnas + ") VALUES (" + binds + ")"
        if updates:
            sql += " ON DUPLICATE KEY UPDATE " + updates
        conn.execute(text(sql), payload)
        return True

    # -----------------------------------------------------------------
    @staticmethod
    def _fila_local_completa(tabla, registro_id):
        """Fila local tal cual (con imagenes y Decimal sin redondear)."""
        pk = PK_POR_TABLA.get(tabla)
        if not pk:
            return None
        try:
            fila = db.session.execute(
                text("SELECT * FROM " + tabla + " WHERE " + pk + " = :pk"),
                {"pk": registro_id},
            ).mappings().first()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return None
        return dict(fila) if fila else None

    # -----------------------------------------------------------------
    @staticmethod
    def _fila_remota_para_comparar(conn, tabla, pk, registro_id, binarias):
        """Lo minimo de la fila en la nube para decidir que subir (o None)."""
        columnas = ["`" + pk + "`"]
        col_ts = TS_ACTUALIZACION.get(tabla)
        if col_ts:
            columnas.append("`" + col_ts + "`")
        if tabla == "ventas":
            columnas.append("`estado`")
        for col in binarias:
            columnas.append("MD5(`" + col + "`) AS `md5_" + col + "`")
        fila = conn.execute(
            text("SELECT " + ", ".join(columnas) + " FROM " + tabla + " WHERE " + pk + " = :pk"),
            {"pk": registro_id},
        ).mappings().first()
        return dict(fila) if fila else None

    # -----------------------------------------------------------------
    @classmethod
    def _subir_movimiento(cls, conn, payload):
        """Sube un movimiento de inventario y aplica su diferencia al stock
        de la nube, en la misma transaccion. Si el movimiento ya estaba
        alla no se toca nada: su efecto ya se aplico la primera vez."""
        ya_estaba = conn.execute(
            text("SELECT 1 FROM movimientos_inventario WHERE id_movimiento = :pk"),
            {"pk": payload["id_movimiento"]},
        ).first()
        if ya_estaba:
            return False

        columnas_remotas = cls._columnas_remotas(conn, "movimientos_inventario")
        datos = {
            k: _valor_sql(v) for k, v in payload.items()
            if v is not None and (not columnas_remotas or k in columnas_remotas)
        }
        if columnas_remotas.get("estado_sync") is not None:
            datos["estado_sync"] = "sinc_remoto"
        conn.execute(
            text(
                "INSERT INTO movimientos_inventario ("
                + ", ".join("`" + c + "`" for c in datos)
                + ") VALUES (" + ", ".join(":" + c for c in datos) + ")"
            ),
            datos,
        )

        delta = _delta_movimiento(payload)
        if delta:
            id_inventario = conn.execute(
                text(
                    "SELECT id_inventario FROM inventario WHERE id_producto = :p "
                    "ORDER BY id_inventario LIMIT 1"
                ),
                {"p": payload["id_producto"]},
            ).scalar()
            if id_inventario is None:
                # Se reintenta en el siguiente ciclo, cuando ya haya subido
                # la fila de inventario de ese producto.
                raise RuntimeError(
                    "La nube todavia no tiene inventario del producto %s" % payload["id_producto"]
                )
            conn.execute(
                text(
                    "UPDATE inventario SET stock_actual = stock_actual + :d, "
                    "fecha_actualizacion = :f WHERE id_inventario = :i"
                ),
                {"d": delta, "f": nicaragua_now(), "i": id_inventario},
            )
        return True

    # -----------------------------------------------------------------
    @staticmethod
    def _registrar_en_nube(conn, op):
        """Anota la operacion ya aplicada en el registro de cambios de la
        nube, marcada con este equipo como origen (asi este nodo no se la
        vuelve a bajar, pero cualquier otro si)."""
        from flask import current_app

        ahora = nicaragua_now()
        conn.execute(
            text(
                "INSERT INTO sync_queue (operation_type, tabla_afectada, registro_id, "
                "id_empresa, timestamp_operacion, timestamp_sincronizacion, estado_sync, "
                "usuario_origen, dispositivo_origen, intentos, fecha_creacion) VALUES "
                "(:op, :tabla, :rid, :emp, :ts, :ahora, 'sinc_remoto', :usr, :disp, 0, :ahora)"
            ),
            {
                "op": op.operation_type,
                "tabla": op.tabla_afectada,
                "rid": op.registro_id,
                "emp": op.id_empresa or current_app.config.get("ID_EMPRESA", 1),
                "ts": op.timestamp_operacion or ahora,
                "ahora": ahora,
                "usr": op.usuario_origen,
                "disp": current_app.config.get("DEVICE_ID", "local-01"),
            },
        )

    # -----------------------------------------------------------------
    @staticmethod
    def _tiene_estado_sync(tabla):
        """Si la tabla local tiene columna estado_sync (con cache)."""
        if tabla not in _CON_ESTADO_SYNC:
            _CON_ESTADO_SYNC[tabla] = bool(
                db.session.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
                        "AND COLUMN_NAME = 'estado_sync'"
                    ),
                    {"t": tabla},
                ).scalar()
            )
        return _CON_ESTADO_SYNC[tabla]

    # -----------------------------------------------------------------
    @classmethod
    def _marcar_registro_sincronizado(cls, op):
        """Marca estado_sync='sinc_remoto' en la fila local original.

        No todas las tablas tienen esa columna (receta_ingredientes, por
        ejemplo). Antes se intentaba igual y el rollback del error deshacia
        tambien el cambio de estado de la propia cola, dejando la operacion
        como pendiente aunque ya se hubiera subido.
        """
        tabla = op.tabla_afectada
        pk = PK_POR_TABLA.get(tabla)
        if not pk or not cls._tiene_estado_sync(tabla):
            return
        db.session.execute(
            text("UPDATE " + tabla + " SET estado_sync = 'sinc_remoto' WHERE " + pk + " = :pk"),
            {"pk": op.registro_id},
        )

    # =================================================================
    # PULL  (nube -> local)
    # =================================================================
    @classmethod
    def pull_remote_changes(cls, tablas=None):
        """Baja a esta base lo que cambio en la nube.

        Lee el registro de cambios de la nube (`sync_queue` de alla) desde
        el cursor de este nodo, en orden, y para cada fila tocada trae su
        estado ACTUAL: si existe se escribe aqui, si ya no existe se borra
        aqui. Asi llegan todas las tablas y tambien los borrados, sin
        depender de fechas ni de un tope de filas por tabla.

        Antes se bajaba por marca de agua de fecha, solo en 8 tablas, sin
        borrados y con un LIMIT 500 que saltaba para siempre el resto.
        """
        resultado = {"aplicados": 0, "borrados": 0, "omitidos": 0, "por_tabla": {}, "errores": []}
        if cls._es_nube():
            resultado["mensaje"] = "Esta instalacion es la nube: no tiene de donde bajar"
            return resultado
        if not NetworkService.is_online():
            resultado["mensaje"] = "Sin conexion: pull omitido"
            return resultado

        from flask import current_app

        cursor = cls._cursor_nube()
        if cursor is None:
            resultado["mensaje"] = (
                "Este equipo aun no tiene punto de partida: ejecuta "
                "'flask bootstrap-nube' (instalacion nueva) o 'flask resync-nube'."
            )
            resultado["errores"].append({"tabla": "*", "error": resultado["mensaje"]})
            return resultado

        engine = db.engines.get("cloud")
        yo = current_app.config.get("DEVICE_ID", "local-01")
        tablas_ok = set(tablas or TABLAS_SYNC) & set(TABLAS_SYNC)

        try:
            with engine.connect() as conn:
                podado = cls._max_id_podado(conn)
                if podado and podado > cursor.ultimo_id:
                    # La nube ya borro (por antiguedad) cambios que este
                    # equipo no alcanzo a bajar: hay que copiar todo de nuevo.
                    resultado["requiere_resync"] = True
                    resultado["mensaje"] = (
                        "Este equipo estuvo desconectado mas tiempo del que la nube "
                        "guarda sus cambios: se necesita una resincronizacion completa."
                    )
                    return resultado
                desde = conn.execute(
                    text(
                        "SELECT MIN(id_sync_queue) FROM (SELECT id_sync_queue FROM sync_queue "
                        "WHERE id_sync_queue <= :c ORDER BY id_sync_queue DESC LIMIT :n) t"
                    ),
                    {"c": cursor.ultimo_id, "n": VENTANA_SOLAPE},
                ).scalar()
            desde = (desde - 1) if desde else cursor.ultimo_id

            ultimo_id = cursor.ultimo_id
            ultima_fecha = cursor.ultima_fecha
            for _ in range(MAX_LOTES_PULL):
                with engine.connect() as conn:
                    entradas = conn.execute(
                        text(
                            "SELECT id_sync_queue, tabla_afectada, registro_id, fecha_creacion "
                            "FROM sync_queue WHERE id_sync_queue > :desde "
                            "AND (dispositivo_origen IS NULL OR dispositivo_origen <> :yo) "
                            "ORDER BY id_sync_queue ASC LIMIT :lote"
                        ),
                        {"desde": desde, "yo": yo, "lote": LOTE_PULL},
                    ).mappings().all()
                    if not entradas:
                        break

                    tocados = {}
                    for e in entradas:
                        if e["tabla_afectada"] in tablas_ok:
                            tocados.setdefault(e["tabla_afectada"], set()).add(e["registro_id"])
                    filas_nube = {
                        tabla: cls._filas_nube(conn, tabla, ids) for tabla, ids in tocados.items()
                    }

                cls._aplicar_lote_local(tocados, filas_nube, resultado)

                desde = entradas[-1]["id_sync_queue"]
                if desde > ultimo_id:
                    ultimo_id = desde
                    ultima_fecha = entradas[-1]["fecha_creacion"]
                if len(entradas) < LOTE_PULL:
                    break

            cursor = cls._cursor_nube()
            cursor.ultimo_id = ultimo_id
            cursor.ultima_fecha = ultima_fecha
            meta = cls._get_metadata("__global__")
            meta.ultimo_pull = nicaragua_now()
            meta.ultima_sincronizacion = meta.ultimo_pull
            meta.registros_sincronizados = (
                (meta.registros_sincronizados or 0) + resultado["aplicados"] + resultado["borrados"]
            )
            meta.estado = "error" if resultado["errores"] else "sincronizado"
            meta.mensaje = (
                "; ".join(e["error"] for e in resultado["errores"][:5])[:500]
                if resultado["errores"] else None
            )
            db.session.commit()
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            resultado["errores"].append({"tabla": "*", "error": str(exc)[:200]})
            log.warning("Pull fallo: %s", exc)

        return resultado

    # -----------------------------------------------------------------
    @staticmethod
    def _es_nube():
        from flask import current_app

        return current_app.config.get("MODO_NODO", "local") == "nube"

    # -----------------------------------------------------------------
    _tabla_cursor_lista = False

    @classmethod
    def _cursor_nube(cls):
        """Cursor de este nodo sobre la nube (None si nunca se preparo)."""
        from app.models.sync import SyncCursor

        if not cls._tabla_cursor_lista:
            # Bases locales creadas antes de que existiera esta tabla.
            SyncCursor.__table__.create(bind=db.engine, checkfirst=True)
            cls._tabla_cursor_lista = True
        return db.session.get(SyncCursor, CURSOR_NUBE)

    @classmethod
    def fijar_cursor(cls, ultimo_id, ultima_fecha=None):
        """Punto de partida del pull: el registro de cambios de la nube ya
        esta reflejado aqui hasta `ultimo_id` (lo usan bootstrap y resync)."""
        from app.models.sync import SyncCursor

        cursor = cls._cursor_nube()
        if cursor is None:
            cursor = SyncCursor(nombre=CURSOR_NUBE)
            db.session.add(cursor)
        cursor.ultimo_id = int(ultimo_id or 0)
        cursor.ultima_fecha = ultima_fecha
        db.session.commit()
        return cursor

    @staticmethod
    def ultimo_id_nube(conn):
        """Mayor id del registro de cambios de la nube (0 si esta vacio)."""
        return conn.execute(text("SELECT COALESCE(MAX(id_sync_queue), 0) FROM sync_queue")).scalar()

    @staticmethod
    def _max_id_podado(conn):
        fila = conn.execute(
            text("SELECT registros_sincronizados FROM sync_metadata WHERE tabla_nombre = :t"),
            {"t": META_PODA},
        ).first()
        return int(fila[0]) if fila and fila[0] else 0

    # -----------------------------------------------------------------
    @staticmethod
    def _filas_nube(conn, tabla, ids):
        """{id: fila} con el estado actual en la nube de las filas pedidas."""
        pk = PK_POR_TABLA[tabla]
        filas = {}
        ids = sorted(ids)
        for i in range(0, len(ids), 200):
            parte = ids[i:i + 200]
            marcas = ", ".join(":id" + str(n) for n in range(len(parte)))
            for fila in conn.execute(
                text("SELECT * FROM " + tabla + " WHERE " + pk + " IN (" + marcas + ")"),
                {"id" + str(n): v for n, v in enumerate(parte)},
            ).mappings().all():
                filas[fila[pk]] = dict(fila)
        return filas

    # -----------------------------------------------------------------
    @classmethod
    def _aplicar_lote_local(cls, tocados, filas_nube, resultado):
        """Escribe aqui el estado de la nube de cada fila tocada.

        Primero lo que se borro (hijos antes que padres) y despues lo que
        existe (padres antes que hijos). Borrar primero importa: al editar
        una receta se borran sus ingredientes y se crean otros con los
        mismos (receta, producto); si la fila nueva entrara antes de borrar
        la vieja, MySQL las fusiona por esa llave unica y al borrar la vieja
        la receta se queda sin ingredientes.
        Cada fila va en su propio punto de guardado: una fila que falle no
        frena al resto ni al cursor. Sin chequeo de llaves foraneas mientras
        se aplica, igual que el bootstrap: la nube es la fuente consistente
        y un padre puede venir en el lote siguiente.
        """
        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            for tabla in reversed(TABLAS_SYNC):
                for rid in sorted(tocados.get(tabla, ())):
                    if rid not in filas_nube.get(tabla, {}):
                        cls._aplicar_con_resguardo(tabla, rid, resultado, None)
            for tabla in TABLAS_SYNC:
                for rid in sorted(tocados.get(tabla, ())):
                    fila = filas_nube.get(tabla, {}).get(rid)
                    if fila is not None:
                        cls._aplicar_con_resguardo(tabla, rid, resultado, fila)
        finally:
            db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            db.session.commit()

    @classmethod
    def _aplicar_con_resguardo(cls, tabla, rid, resultado, fila):
        punto = db.session.begin_nested()
        try:
            if fila is None:
                efecto = cls._borrar_local(tabla, rid)
            else:
                efecto = cls._aplicar_fila_local(tabla, fila)
            punto.commit()
        except Exception as exc:  # noqa: BLE001
            punto.rollback()
            resultado["errores"].append({"tabla": tabla, "error": "#%s: %s" % (rid, str(exc)[:160])})
            log.warning("Pull: no se pudo aplicar %s#%s: %s", tabla, rid, exc)
            return
        if efecto == "aplicado":
            resultado["aplicados"] += 1
            resultado["por_tabla"][tabla] = resultado["por_tabla"].get(tabla, 0) + 1
        elif efecto == "borrado":
            resultado["borrados"] += 1
            resultado["por_tabla"][tabla] = resultado["por_tabla"].get(tabla, 0) + 1
        elif efecto == "omitido":
            resultado["omitidos"] += 1

    # -----------------------------------------------------------------
    _COLUMNAS_LOCALES = {}

    @classmethod
    def _columnas_locales(cls, tabla):
        if tabla not in cls._COLUMNAS_LOCALES:
            cls._COLUMNAS_LOCALES[tabla] = set(
                db.session.execute(
                    text(
                        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                    ),
                    {"t": tabla},
                ).scalars().all()
            )
        return cls._COLUMNAS_LOCALES[tabla]

    @staticmethod
    def _tiene_pendiente_local(tabla, registro_id):
        """Si esta fila tiene cambios hechos aqui que aun no suben: mandan
        ellos hasta que se suban (el siguiente push los lleva a la nube)."""
        return SyncQueue.query.filter(
            SyncQueue.tabla_afectada == tabla,
            SyncQueue.registro_id == registro_id,
            SyncQueue.estado_sync.in_(["pendiente", "error"]),
        ).first() is not None

    # -----------------------------------------------------------------
    @classmethod
    def _aplicar_fila_local(cls, tabla, fila):
        """Escribe aqui la version de la nube de una fila (sin re-encolarla)."""
        pk = PK_POR_TABLA[tabla]
        columnas = cls._columnas_locales(tabla)
        datos = {k: _valor_sql(v) for k, v in fila.items() if k in columnas}

        if tabla == "movimientos_inventario":
            return cls._bajar_movimiento(datos)

        if cls._tiene_pendiente_local(tabla, datos[pk]):
            return "omitido"

        col_ts = TS_ACTUALIZACION.get(tabla)
        local = None
        if col_ts or tabla in ("ventas", "inventario"):
            extra = ", `estado`" if tabla == "ventas" else ""
            extra += (", `" + col_ts + "`") if col_ts else ""
            local = db.session.execute(
                text("SELECT `" + pk + "`" + extra + " FROM " + tabla + " WHERE " + pk + " = :pk"),
                {"pk": datos[pk]},
            ).mappings().first()

        if local is not None:
            anulando = tabla == "ventas" and datos.get("estado") == "anulada"
            # Una venta anulada aqui se queda anulada (ya subira).
            if tabla == "ventas" and local["estado"] == "anulada" and not anulando:
                return "omitido"
            if col_ts and not anulando:
                ts_local = _parse_ts(local[col_ts])
                ts_remoto = _parse_ts(datos.get(col_ts))
                if ts_local and ts_remoto and ts_local > ts_remoto:
                    return "omitido"

        if tabla == "inventario":
            # El stock lo ajustan los movimientos (ver _bajar_movimiento).
            if local is not None:
                datos.pop("stock_actual", None)
            else:
                datos["stock_actual"] = 0

        if "estado_sync" in columnas:
            datos["estado_sync"] = "sinc_remoto"

        nombres = ", ".join("`" + c + "`" for c in datos)
        binds = ", ".join(":" + c for c in datos)
        updates = ", ".join("`" + c + "` = VALUES(`" + c + "`)" for c in datos if c != pk)
        sql = "INSERT INTO " + tabla + " (" + nombres + ") VALUES (" + binds + ")"
        if updates:
            sql += " ON DUPLICATE KEY UPDATE " + updates
        db.session.execute(text(sql), datos)
        return "aplicado"

    # -----------------------------------------------------------------
    @staticmethod
    def _bajar_movimiento(datos):
        """Un movimiento de la nube: se guarda y su diferencia se aplica al
        stock de aqui. Si ya estaba, no se toca nada (ya se aplico)."""
        ya_estaba = db.session.execute(
            text("SELECT 1 FROM movimientos_inventario WHERE id_movimiento = :pk"),
            {"pk": datos["id_movimiento"]},
        ).first()
        if ya_estaba:
            return "omitido"

        datos = {k: v for k, v in datos.items() if v is not None}
        datos["estado_sync"] = "sinc_remoto"
        db.session.execute(
            text(
                "INSERT INTO movimientos_inventario ("
                + ", ".join("`" + c + "`" for c in datos)
                + ") VALUES (" + ", ".join(":" + c for c in datos) + ")"
            ),
            datos,
        )
        delta = _delta_movimiento(datos)
        if delta:
            id_inventario = db.session.execute(
                text(
                    "SELECT id_inventario FROM inventario WHERE id_producto = :p "
                    "ORDER BY id_inventario LIMIT 1"
                ),
                {"p": datos["id_producto"]},
            ).scalar()
            if id_inventario is None:
                log.warning(
                    "Pull: movimiento #%s sin fila de inventario local para el producto %s",
                    datos["id_movimiento"], datos["id_producto"],
                )
            else:
                db.session.execute(
                    text(
                        "UPDATE inventario SET stock_actual = stock_actual + :d, "
                        "fecha_actualizacion = :f WHERE id_inventario = :i"
                    ),
                    {"d": delta, "f": nicaragua_now(), "i": id_inventario},
                )
        return "aplicado"

    # -----------------------------------------------------------------
    @staticmethod
    def _borrar_local(tabla, registro_id):
        """La fila ya no existe en la nube: se borra aqui. Si tenia cambios
        locales sin subir se descartan (el borrado de la nube gana; si no,
        el push la volveria a crear alla)."""
        pk = PK_POR_TABLA[tabla]
        borradas = db.session.execute(
            text("DELETE FROM " + tabla + " WHERE " + pk + " = :pk"), {"pk": registro_id}
        ).rowcount
        if not borradas:
            return None
        SyncQueue.query.filter(
            SyncQueue.tabla_afectada == tabla,
            SyncQueue.registro_id == registro_id,
            SyncQueue.estado_sync.in_(["pendiente", "error"]),
        ).update({"estado_sync": "resuelto"}, synchronize_session=False)
        return "borrado"

    # -----------------------------------------------------------------
    @staticmethod
    def _upsert_local(tabla, datos):
        """Inserta/actualiza una fila remota en la BD local sin re-encolarla.

        Auditoria H-05 (conflictos de sync): antes esto sobreescribia SIEMPRE
        con lo que trajera el pull -- "el ultimo que llega gana", sin
        importar si el dato local era mas reciente. Asi fue exactamente
        como una venta anulada localmente pudo "revivir": si el push de la
        anulacion no habia llegado a tiempo, un pull que trajera la
        version vieja de la nube (todavia 'completada') la volvia a
        escribir encima.

        Politica de conflicto (LAST WRITE WINS por tiempo real, documentada
        aqui a proposito, no implicita): para las tablas que tienen una
        columna de timestamp registrada en TIMESTAMP_POR_TABLA, si la fila
        YA existe en local se compara su timestamp contra el que trae el
        pull -- gana quien sea mas reciente. En empate exacto se queda el
        local (ya esta aplicado, no hace falta re-escribirlo). Las tablas
        sin timestamp registrado (categorias, clientes, detalle_ventas,
        etc.) no tienen como compararse por ahora y mantienen el
        comportamiento anterior -- son de menor riesgo porque no se anulan
        ni editan despues de creadas de la misma forma que una venta.
        """
        pk = PK_POR_TABLA.get(tabla, "id")
        datos = {k: v for k, v in datos.items() if v is not None}
        if pk not in datos:
            return False

        col_ts = TIMESTAMP_POR_TABLA.get(tabla)
        if col_ts and col_ts in datos:
            ts_remoto = _parse_ts(datos[col_ts])
            if ts_remoto is not None:
                fila_local = db.session.execute(
                    text(f"SELECT `{col_ts}` FROM `{tabla}` WHERE `{pk}` = :pk"),
                    {"pk": datos[pk]},
                ).fetchone()
                if fila_local is not None and fila_local[0] is not None:
                    ts_local = _parse_ts(fila_local[0])
                    if ts_local is not None and ts_local > ts_remoto:
                        log.info(
                            "Pull descartado por conflicto (local mas nuevo): %s#%s "
                            "(local=%s > remoto=%s)",
                            tabla, datos[pk], ts_local, ts_remoto,
                        )
                        return False

        datos["estado_sync"] = "sinc_remoto"

        def _construir(d):
            columnas = ", ".join("`" + c + "`" for c in d)
            binds = ", ".join(":" + c for c in d)
            updates = ", ".join("`" + c + "` = VALUES(`" + c + "`)" for c in d if c != pk)
            sql = "INSERT INTO " + tabla + " (" + columnas + ") VALUES (" + binds + ")"
            if updates:
                sql += " ON DUPLICATE KEY UPDATE " + updates
            return sql

        try:
            db.session.execute(text(_construir(datos)), datos)
            return True
        except Exception:
            db.session.rollback()
            datos.pop("estado_sync", None)
            db.session.execute(text(_construir(datos)), datos)
            return True

    # =================================================================
    # CICLO COMPLETO
    # =================================================================
    @classmethod
    def sync_full(cls, disparador="manual"):
        """Ejecuta PUSH + PULL + resolucion de conflictos.

        Primero sube lo del restaurante y despues baja lo de la nube: asi lo
        que se baja ya trae incluido lo recien subido, y un cambio local que
        aun no llegaba a la nube no se pisa con la version vieja de alla.
        """
        from app.services.conflict_service import ConflictService

        if cls._es_nube():
            return {
                "ok": True,
                "online": True,
                "modo": "nube",
                "mensaje": "Esta instalacion es la nube; los equipos del restaurante "
                           "se sincronizan con ella.",
                "pendientes": 0,
            }

        if not cls._running.acquire(blocking=False):
            return {"ok": False, "mensaje": "Ya hay una sincronizacion en curso"}
        try:
            NetworkService.check_connectivity()
            if not NetworkService.is_online():
                return {
                    "ok": False,
                    "online": False,
                    "mensaje": "Sin conexion con la nube. Los datos quedan en cola local.",
                    "pendientes": cls.contar_pendientes(),
                }

            inicio = nicaragua_now()
            push = cls.push_pending_operations()
            pull = cls.pull_remote_changes()
            if pull.get("requiere_resync") and cls.contar_pendientes() == 0:
                # Todo lo de aqui ya esta arriba: es seguro copiar todo de nuevo.
                from app.services.bootstrap_service import resincronizar_desde_nube

                pull["resync"] = resincronizar_desde_nube()
            conflictos = ConflictService.resolver_pendientes()

            return {
                "ok": True,
                "online": True,
                "disparador": disparador,
                "inicio": inicio.isoformat(),
                "fin": nicaragua_now().isoformat(),
                "pull": pull,
                "push": push,
                "conflictos": conflictos,
                "pendientes": cls.contar_pendientes(),
            }
        finally:
            cls._running.release()

    # =================================================================
    # UTILIDADES
    # =================================================================
    @classmethod
    def contar_pendientes(cls):
        # En la nube la cola es solo el registro de cambios: nada "pendiente
        # de subir" (no hay a donde).
        if cls._es_nube():
            return 0
        return SyncQueue.query.filter(
            SyncQueue.estado_sync.in_(["pendiente", "error"])
        ).count()

    # -----------------------------------------------------------------
    @classmethod
    def podar_registro(cls):
        """Borra lo viejo de `sync_queue` para que no crezca sin limite.

        - En la nube: todo cambio con mas de RETENCION_COLA_DIAS. Se anota
          el mayor id borrado (META_PODA) para que un nodo que se quedo
          atras sepa que necesita una resincronizacion completa.
        - En el restaurante: lo ya subido o resuelto con mas de 30 dias
          (los errores y conflictos se quedan para poder revisarlos).
        """
        from flask import current_app

        if cls._es_nube():
            dias = current_app.config.get("RETENCION_COLA_DIAS", 90)
            limite = nicaragua_now() - timedelta(days=dias)
            hasta = db.session.execute(
                text("SELECT MAX(id_sync_queue) FROM sync_queue WHERE fecha_creacion < :l"),
                {"l": limite},
            ).scalar()
            if not hasta:
                return 0
            borradas = db.session.execute(
                text("DELETE FROM sync_queue WHERE id_sync_queue <= :h"), {"h": hasta}
            ).rowcount
            meta = cls._get_metadata(META_PODA)
            meta.registros_sincronizados = max(int(meta.registros_sincronizados or 0), int(hasta))
            meta.ultima_sincronizacion = nicaragua_now()
            meta.estado = "sincronizado"
            db.session.commit()
            return borradas

        limite = nicaragua_now() - timedelta(days=30)
        borradas = SyncQueue.query.filter(
            SyncQueue.estado_sync.in_(["sinc_remoto", "resuelto"]),
            SyncQueue.fecha_creacion < limite,
        ).delete(synchronize_session=False)
        db.session.commit()
        return borradas

    @staticmethod
    def _get_metadata(tabla):
        meta = SyncMetadata.query.filter_by(tabla_nombre=tabla).first()
        if not meta:
            meta = SyncMetadata(tabla_nombre=tabla, estado="pendiente")
            db.session.add(meta)
            db.session.commit()
        return meta

    @classmethod
    def _actualizar_metadata(cls, tipo, cantidad):
        meta = cls._get_metadata("__global__")
        ahora = nicaragua_now()
        meta.ultima_sincronizacion = ahora
        if tipo == "push":
            meta.ultimo_push = ahora
        else:
            meta.ultimo_pull = ahora
        meta.registros_sincronizados = (meta.registros_sincronizados or 0) + cantidad
        meta.estado = "sincronizado"
        db.session.commit()

    @classmethod
    def estado_general(cls):
        from flask import current_app

        pendientes = cls.contar_pendientes()
        conflictos = ConflictLog.query.filter_by(
            estado_resolucion="pendiente_resolucion"
        ).count()
        meta = SyncMetadata.query.filter_by(tabla_nombre="__global__").first()
        modo = current_app.config.get("MODO_NODO", "local")
        return {
            "modo": modo,
            "dispositivo": current_app.config.get("DEVICE_ID"),
            # La nube siempre esta "en linea" consigo misma: no se monitorea.
            "online": True if modo == "nube" else NetworkService.is_online(),
            "pendientes": pendientes,
            "conflictos_pendientes": conflictos,
            "ultima_sincronizacion": meta.ultima_sincronizacion.isoformat()
            if meta and meta.ultima_sincronizacion
            else None,
            "red": NetworkService.status(),
        }
