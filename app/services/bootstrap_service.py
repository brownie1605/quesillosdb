"""Preparacion inicial de la base local a partir de la nube.

Dos piezas que evitan que la sincronizacion corrompa datos:

1. `copiar_desde_nube()` — trae el catalogo y el historial de la nube a la
   base local, para que ambas partan del mismo estado.

2. `aplicar_offset_ids()` — reserva un rango de IDs para esta maquina
   (por defecto desde 1 000 000). La nube sigue usando 1..999999, asi que
   un INSERT hecho aqui nunca puede pisar un registro distinto de la nube
   cuando se sube con `INSERT ... ON DUPLICATE KEY UPDATE`.
"""
import logging

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.services.sync_service import PK_POR_TABLA

log = logging.getLogger("bootstrap")

# Orden de copia: respeta las dependencias de claves foraneas.
ORDEN_COPIA = [
    "empresas",
    "sucursales",
    "roles",
    "permisos",
    "rol_permiso",
    "usuarios",
    "categorias",
    "marcas",
    "unidades_medida",
    "proveedores",
    "clientes",
    "productos",
    "recetas",
    "receta_ingredientes",
    "receta_opciones_grupo",
    "receta_opciones_item",
    "inventario",
    "cajas",
    "compras",
    "detalle_compras",
    "ventas",
    "detalle_ventas",
    "movimientos_inventario",
    "configuraciones",
    "notificaciones",
]

# Tablas cuyos IDs se generan en ambos lados y por tanto necesitan rango propio.
TABLAS_CON_OFFSET = [
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
    "clientes",
    "proveedores",
    "categorias",
    "marcas",
    "usuarios",
    "notificaciones",
    "movimientos_caja",
    "aperturas_caja",
    "cierres_caja",
]


def _columnas_locales(tabla):
    filas = db.session.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
        ),
        {"t": tabla},
    ).scalars().all()
    return set(filas)


def _tabla_existe_local(tabla):
    return bool(
        db.session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
            ),
            {"t": tabla},
        ).scalar()
    )


def _upsert(tabla, datos, clave):
    columnas = ", ".join("`" + c + "`" for c in datos)
    binds = ", ".join(":" + c for c in datos)
    updates = ", ".join("`" + c + "` = VALUES(`" + c + "`)" for c in datos if c != clave)
    consulta = "INSERT INTO " + tabla + " (" + columnas + ") VALUES (" + binds + ")"
    if updates:
        consulta += " ON DUPLICATE KEY UPDATE " + updates
    return consulta


def _sin_binarios(datos):
    """Misma fila pero sin columnas binarias (imagenes)."""
    return {
        k: v for k, v in datos.items()
        if not isinstance(v, (bytes, bytearray))
    }


# ---------------------------------------------------------------------------
def copiar_desde_nube(tablas=None, limite_por_tabla=None):
    """Copia la nube -> local. No borra nada: usa upsert por clave primaria."""
    engine = db.engines.get("cloud")
    if engine is None:
        raise RuntimeError("No hay conexion configurada con la nube")

    tablas = tablas or ORDEN_COPIA
    resumen = {"copiados": 0, "por_tabla": {}, "errores": []}

    for tabla in tablas:
        if not _tabla_existe_local(tabla):
            continue
        pk = PK_POR_TABLA.get(tabla)
        columnas_ok = _columnas_locales(tabla)

        try:
            with engine.connect() as conn:
                sql = "SELECT * FROM " + tabla
                if limite_por_tabla:
                    sql += " LIMIT " + str(int(limite_por_tabla))
                filas = conn.execute(text(sql)).mappings().all()

            insertados = 0
            fallidas = 0
            for fila in filas:
                datos = {
                    k: v for k, v in dict(fila).items()
                    if k in columnas_ok and v is not None
                }
                if not datos:
                    continue
                if "estado_sync" in columnas_ok:
                    datos["estado_sync"] = "sinc_remoto"

                clave = pk or next(iter(datos))
                ultimo_error = None
                # Una fila mala (p. ej. una imagen enorme) no debe tumbar la tabla:
                # se reintenta sin las columnas binarias antes de darla por perdida.
                for intento in (datos, _sin_binarios(datos)):
                    try:
                        # El commit por fila devuelve la conexion al pool, asi que
                        # la variable de sesion hay que reafirmarla cada vez.
                        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                        db.session.execute(text(_upsert(tabla, intento, clave)), intento)
                        db.session.commit()
                        insertados += 1
                        break
                    except Exception as exc:  # noqa: BLE001
                        db.session.rollback()
                        ultimo_error = exc
                else:
                    fallidas += 1
                    log.warning("Fila %s de %s omitida: %s",
                                datos.get(clave), tabla, str(ultimo_error)[:150])

            resumen["copiados"] += insertados
            resumen["por_tabla"][tabla] = insertados
            if fallidas:
                resumen["errores"].append(
                    {"tabla": tabla, "error": str(fallidas) + " fila(s) omitida(s)"}
                )
            log.info("Copiadas %s filas de %s", insertados, tabla)
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            resumen["errores"].append({"tabla": tabla, "error": str(exc)[:200]})
            log.warning("Fallo copiando %s: %s", tabla, exc)

    db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    db.session.commit()
    return resumen


# ---------------------------------------------------------------------------
def _proximo_auto_increment(tabla):
    """AUTO_INCREMENT actual de la tabla.

    `information_schema.TABLES` puede devolver un valor cacheado/desactualizado
    justo despues de un ALTER o de borrar filas; `ANALYZE TABLE` fuerza a MySQL
    a recalcularlo antes de leerlo, para no reportar falsos riesgos de colision.
    """
    db.session.execute(text("ANALYZE TABLE " + tabla))
    return db.session.execute(
        text(
            "SELECT AUTO_INCREMENT FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
        ),
        {"t": tabla},
    ).scalar()


def aplicar_offset_ids(offset=None):
    """Mueve el AUTO_INCREMENT local al rango reservado para esta maquina."""
    offset = offset or current_app.config.get("LOCAL_ID_OFFSET", 1000000)
    resumen = {"offset": offset, "aplicado": [], "omitido": []}

    for tabla in TABLAS_CON_OFFSET:
        if not _tabla_existe_local(tabla):
            continue
        actual = _proximo_auto_increment(tabla)

        if actual and actual >= offset:
            resumen["omitido"].append(tabla)   # ya esta en el rango local
            continue

        db.session.execute(text("ALTER TABLE " + tabla + " AUTO_INCREMENT = " + str(offset)))
        resumen["aplicado"].append(tabla)

    db.session.commit()
    log.info("Offset %s aplicado a %s tablas", offset, len(resumen["aplicado"]))
    return resumen


# ---------------------------------------------------------------------------
def verificar_rangos():
    """Reporta si alguna tabla local podria colisionar con la nube."""
    offset = current_app.config.get("LOCAL_ID_OFFSET", 1000000)
    riesgos = []

    for tabla in TABLAS_CON_OFFSET:
        if not _tabla_existe_local(tabla):
            continue
        pk = PK_POR_TABLA.get(tabla)
        if not pk:
            continue
        siguiente = _proximo_auto_increment(tabla)
        if siguiente and siguiente < offset:
            riesgos.append(
                {"tabla": tabla, "proximo_id": siguiente, "offset_esperado": offset}
            )

    return {"offset": offset, "en_riesgo": riesgos, "ok": not riesgos}
