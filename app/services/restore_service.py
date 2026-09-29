"""Restauracion de un backup generado por BackupService.

Auditoria H-01: existia la generacion del backup (BackupService) pero
ningun camino para restaurarlo -- un backup que nunca se ha restaurado
con exito no puede considerarse "probado". Este servicio cierra eso, con
una regla dura: NUNCA asume un destino. La base a restaurar SIEMPRE viene
de la variable de entorno `RESTORE_TARGET` (una URI completa tipo
`mysql+pymysql://usuario:clave@host:3306/base_de_prueba`) -- si esa URI
coincide con cualquiera de las bases que la app ya usa (DB_LOCAL_* o
DB_REMOTE_*, es decir produccion/desarrollo real), se exige una
confirmacion explicita ademas (ver `flask restaurar-backup --help`).
"""
import gzip
import logging
import os
import re

import pymysql
from pymysql.constants import CLIENT
from sqlalchemy.engine import make_url

from app.config.config import Config
from app.services.backup_service import CARPETA_DEFECTO

log = logging.getLogger("backup.restore")


class RestoreError(Exception):
    pass


class RestoreService:

    # -----------------------------------------------------------------
    @staticmethod
    def _resolver_archivo(archivo):
        """Acepta una ruta local (dentro de `bd/respaldos`) o el nombre de
        un backup que solo existe en R2 -- nunca una ruta/URL arbitraria
        fuera de esos dos lugares conocidos (evita "descarga arbitraria de
        archivos", explicitamente prohibido por la auditoria)."""
        ruta_local = archivo if os.path.isabs(archivo) else os.path.join(CARPETA_DEFECTO, os.path.basename(archivo))
        ruta_local = os.path.abspath(ruta_local)
        carpeta_abs = os.path.abspath(CARPETA_DEFECTO)
        if ruta_local != carpeta_abs and not ruta_local.startswith(carpeta_abs + os.sep):
            raise RestoreError(f"Ruta fuera de la carpeta de respaldos permitida ({carpeta_abs})")

        if os.path.isfile(ruta_local):
            return ruta_local

        from app.services.backup_service import BackupService

        cliente, bucket = BackupService._cliente_r2()
        if cliente is None:
            raise RestoreError(
                f"No se encontro '{os.path.basename(archivo)}' en {carpeta_abs} y R2 no esta configurado "
                "(o el archivo tampoco existe alli)."
            )

        clave = f"respaldos/{os.path.basename(archivo)}"
        os.makedirs(carpeta_abs, exist_ok=True)
        try:
            cliente.download_file(bucket, clave, ruta_local)
        except Exception as e:  # noqa: BLE001
            raise RestoreError(f"No se pudo bajar '{clave}' de R2: {e}") from e
        return ruta_local

    # -----------------------------------------------------------------
    @staticmethod
    def _leer_y_verificar(ruta):
        try:
            with gzip.open(ruta, "rt", encoding="utf-8") as f:
                contenido = f.read()
        except Exception as e:  # noqa: BLE001
            raise RestoreError(f"El archivo no es un .sql.gz valido o esta corrupto: {e}") from e

        if not contenido.strip():
            raise RestoreError("El backup esta vacio")
        if "SET FOREIGN_KEY_CHECKS" not in contenido:
            raise RestoreError(
                "El archivo no tiene la forma esperada de un backup de Quesillos POS "
                "(falta el encabezado SET FOREIGN_KEY_CHECKS) -- se rechaza por seguridad."
            )
        return contenido

    # -----------------------------------------------------------------
    @staticmethod
    def _es_bd_conocida(url_destino):
        """True si la URI destino apunta al mismo host+BD que la app ya usa
        (local o cloud) -- esas nunca deben pisarse por accidente con un
        restore silencioso."""
        candidatos = [Config.SQLALCHEMY_DATABASE_URI] + list(Config.SQLALCHEMY_BINDS.values())
        for cand in candidatos:
            if not cand:
                continue
            try:
                u = make_url(cand)
            except Exception:  # noqa: BLE001
                continue
            if u.host == url_destino.host and u.database == url_destino.database:
                return True
        return False

    # -----------------------------------------------------------------
    @staticmethod
    def restaurar(archivo, confirmar_produccion=False):
        """Restaura `archivo` (ruta local o nombre en R2) sobre la BD que
        indique RESTORE_TARGET. Lanza RestoreError si algo no cumple las
        condiciones de seguridad; nunca ejecuta nada contra un destino no
        confirmado."""
        destino_raw = os.getenv("RESTORE_TARGET")
        if not destino_raw:
            raise RestoreError(
                "Falta la variable de entorno RESTORE_TARGET (URI completa de la BD "
                "DESTINO, ej. mysql+pymysql://usuario:clave@host:3306/base_de_prueba). "
                "No se asume ningun destino por defecto a proposito -- sin esto, no se "
                "restaura nada."
            )

        try:
            url_destino = make_url(destino_raw)
        except Exception as e:  # noqa: BLE001
            raise RestoreError(f"RESTORE_TARGET no es una URI de BD valida: {e}") from e

        if RestoreService._es_bd_conocida(url_destino):
            if not confirmar_produccion:
                raise RestoreError(
                    f"RESTORE_TARGET ({url_destino.host}/{url_destino.database}) coincide con "
                    "una base que esta app ya usa (local o cloud) -- esto reemplazaria datos "
                    "reales. Si de verdad es lo que quieres, vuelve a correr el comando "
                    "agregando --confirmar-produccion."
                )
            log.warning(
                "Restauracion CONFIRMADA contra una base conocida de la app: %s/%s",
                url_destino.host, url_destino.database,
            )

        ruta = RestoreService._resolver_archivo(archivo)
        contenido = RestoreService._leer_y_verificar(ruta)

        # Auditoria H-01 (descubierto al construir esta misma prueba de
        # restore, contra una BD separada real -- no se asumio que la
        # primera version funcionara): las vistas rotas conocidas (ver
        # hallazgo M-05 de la auditoria) pueden hacer que OTRAS vistas que
        # dependen de ellas fallen tambien al recrearse, y un solo
        # cursor.execute() con CLIENT_MULTI_STATEMENTS aborta TODO el
        # resto del stream en el primer error de cualquier parte. Por eso
        # las tablas (con sus datos) se restauran en un solo bloque
        # atomico -- eso rara vez falla, son datos reales de un origen que
        # ya funcionaba -- y las vistas se restauran una por una,
        # salteando con un aviso la que falle, igual que ya hace el propio
        # backup con las vistas rotas al generarse.
        marcador = "-- ==================== VISTAS ====================\n\n"
        if marcador in contenido:
            parte_tablas, parte_vistas = contenido.split(marcador, 1)
        else:
            parte_tablas, parte_vistas = contenido, ""

        conexion = pymysql.connect(
            host=url_destino.host,
            port=url_destino.port or 3306,
            user=url_destino.username,
            password=url_destino.password or "",
            database=url_destino.database,
            charset="utf8mb4",
            client_flag=CLIENT.MULTI_STATEMENTS,
        )
        vistas_omitidas = []
        try:
            with conexion.cursor() as cursor:
                cursor.execute(parte_tablas)
                while cursor.nextset():
                    pass
            conexion.commit()

            bloques_vistas = [
                b.strip() for b in re.split(r"(?=^DROP VIEW IF EXISTS)", parte_vistas, flags=re.MULTILINE)
                if b.strip() and not b.strip().startswith("--")
            ]

            def _nombre_de(bloque):
                m = re.search(r"DROP VIEW IF EXISTS `(\w+)`", bloque)
                return m.group(1) if m else "?"

            def _intentar(bloque):
                try:
                    with conexion.cursor() as cursor:
                        cursor.execute(bloque)
                        while cursor.nextset():
                            pass
                    conexion.commit()
                    return None
                except Exception as e:  # noqa: BLE001
                    conexion.rollback()
                    return str(e)

            # Una vista puede referenciar a OTRA vista que en el archivo
            # aparece mas adelante (el orden es solo alfabetico, no por
            # dependencias) -- si se crea antes de que su dependencia
            # exista, falla con "table doesn't exist" aunque la vista en
            # si este perfectamente bien. Por eso se reintenta una vez mas
            # el lote completo de fallidas al final: para entonces, las
            # vistas de las que dependian (si tambien eran validas) ya
            # deberian existir. Lo que siga fallando despues del reintento
            # si se omite de verdad (rota, o dependencia rota).
            pendientes = bloques_vistas
            for intento in (1, 2):
                fallidas = []
                for bloque in pendientes:
                    error = _intentar(bloque)
                    if error is not None:
                        fallidas.append(bloque)
                        if intento == 2:
                            nombre_vista = _nombre_de(bloque)
                            vistas_omitidas.append(nombre_vista)
                            log.warning("Restore: se omitio la vista '%s' por error: %s", nombre_vista, error)
                pendientes = fallidas
                if not pendientes:
                    break
        except Exception as e:  # noqa: BLE001
            conexion.rollback()
            raise RestoreError(f"Fallo al restaurar las tablas contra el destino: {e}") from e
        finally:
            conexion.close()

        reporte = RestoreService._verificar_resultado(url_destino, parte_tablas, ruta)
        reporte["vistas_omitidas"] = vistas_omitidas
        if vistas_omitidas:
            reporte["resumen"] += f" -- {len(vistas_omitidas)} vista(s) omitida(s): {vistas_omitidas}"
        return reporte

    # -----------------------------------------------------------------
    @staticmethod
    def _verificar_resultado(url_destino, contenido, ruta):
        """Cuenta cuantas filas trae el backup por tabla (un INSERT por
        fila, ver BackupService) y las compara contra lo que de verdad
        quedo en el destino -- sin esto, "el comando no tiro error" no es
        lo mismo que "los datos de verdad quedaron ahi"."""
        esperados = {}
        for match in re.finditer(r"^INSERT INTO `(\w+)`", contenido, re.MULTILINE):
            tabla = match.group(1)
            esperados[tabla] = esperados.get(tabla, 0) + 1

        conexion = pymysql.connect(
            host=url_destino.host, port=url_destino.port or 3306,
            user=url_destino.username, password=url_destino.password or "",
            database=url_destino.database, charset="utf8mb4",
        )
        detalle = []
        ok = True
        try:
            with conexion.cursor() as cursor:
                for tabla, esperado in sorted(esperados.items()):
                    cursor.execute(f"SELECT COUNT(*) FROM `{tabla}`")
                    real = cursor.fetchone()[0]
                    if real != esperado:
                        ok = False
                    detalle.append(
                        f"{tabla}: esperadas={esperado} reales={real} "
                        f"[{'OK' if real == esperado else 'DIFERENTE'}]"
                    )
        finally:
            conexion.close()

        return {
            "ok": ok,
            "archivo": ruta,
            "destino": f"{url_destino.host}/{url_destino.database}",
            "tablas_verificadas": len(esperados),
            "resumen": (
                f"Restauracion {'EXITOSA' if ok else 'CON DIFERENCIAS -- revisar detalle'} "
                f"contra {url_destino.host}/{url_destino.database} "
                f"({len(esperados)} tablas verificadas)"
            ),
            "detalle": detalle,
        }
