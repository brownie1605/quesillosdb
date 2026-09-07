"""Respaldo de la base de datos, sin depender de `mysqldump`.

Por que no usar mysqldump: no siempre esta instalado ni en el PATH (esta
misma maquina de desarrollo no lo tiene), y una vez el sistema viva en
Railway tampoco se puede asumir que el binario este disponible ahi. Esta
version es pure-Python: recorre las tablas via SQLAlchemy y escribe un
.sql.gz con CREATE TABLE + INSERT de cada fila, restaurable con
`mysql < archivo.sql` (o `gunzip -c archivo.sql.gz | mysql ...`) en
cualquier MySQL, sin depender de ninguna herramienta externa.
"""
import gzip
import logging
import os
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from app.extensions import db

log = logging.getLogger("backup")

# quesillos-pos/bd/respaldos -- ya existe, ya esta en .gitignore.
CARPETA_DEFECTO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "bd", "respaldos",
)


class BackupService:

    # -----------------------------------------------------------------
    @staticmethod
    def _tablas(conn):
        return [f[0] for f in conn.execute(text("SHOW TABLES")).fetchall()]

    # -----------------------------------------------------------------
    @staticmethod
    def _escapar_valor(v):
        if v is None:
            return "NULL"
        if isinstance(v, (bytes, bytearray)):
            return ("0x" + v.hex()) if v else "''"
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{s}'"

    # -----------------------------------------------------------------
    @staticmethod
    def crear_backup(nombre_bind="local", carpeta=None, prefijo=None):
        """Vuelca schema + datos de TODAS las tablas del bind indicado
        ('local' o 'cloud') a un .sql.gz con fecha/hora en el nombre.
        Devuelve la ruta del archivo creado."""
        carpeta = carpeta or CARPETA_DEFECTO
        os.makedirs(carpeta, exist_ok=True)

        engine = db.engine if nombre_bind == "local" else db.engines.get(nombre_bind)
        if engine is None:
            raise ValueError(f"No hay motor de base de datos configurado para '{nombre_bind}'")

        prefijo = prefijo or nombre_bind
        ahora = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = os.path.join(carpeta, f"{prefijo}_{ahora}.sql.gz")
        # Sufijo unico en el .tmp (no en el nombre final): evita que dos
        # respaldos disparados casi al mismo segundo -- ej. el job
        # automatico y un `flask backup-ahora` manual -- escriban sobre el
        # mismo archivo temporal a la vez.
        ruta_tmp = ruta + f".{uuid.uuid4().hex[:8]}.tmp"

        with engine.connect() as conn:
            tablas = BackupService._tablas(conn)
            with gzip.open(ruta_tmp, "wt", encoding="utf-8") as f:
                f.write(f"-- Respaldo Quesillos POS ({nombre_bind}) - {datetime.now().isoformat()}\n")
                f.write("SET FOREIGN_KEY_CHECKS=0;\n\n")
                for tabla in tablas:
                    crear = conn.execute(text(f"SHOW CREATE TABLE `{tabla}`")).fetchone()
                    f.write(f"DROP TABLE IF EXISTS `{tabla}`;\n{crear[1]};\n\n")

                    filas = conn.execute(text(f"SELECT * FROM `{tabla}`")).mappings().fetchall()
                    if not filas:
                        continue
                    columnas = list(filas[0].keys())
                    cols_sql = ", ".join(f"`{c}`" for c in columnas)
                    f.write(f"-- {len(filas)} filas\n")
                    for fila in filas:
                        valores = ", ".join(BackupService._escapar_valor(fila[c]) for c in columnas)
                        f.write(f"INSERT INTO `{tabla}` ({cols_sql}) VALUES ({valores});\n")
                    f.write("\n")
                f.write("SET FOREIGN_KEY_CHECKS=1;\n")

        # Escribir a .tmp y renombrar al final: si el proceso se corta a
        # medias (se va la luz, etc.), nunca queda un backup a medio
        # escribir con el nombre "bueno" confundiendo una restauracion.
        os.replace(ruta_tmp, ruta)

        tamano_kb = os.path.getsize(ruta) / 1024
        log.info("Respaldo creado: %s (%.1f KB, %d tablas)", ruta, tamano_kb, len(tablas))
        return ruta

    # -----------------------------------------------------------------
    @staticmethod
    def limpiar_viejos(carpeta=None, dias_retener=14, prefijo=None):
        """Borra respaldos mas viejos que `dias_retener`. Devuelve los
        nombres de archivo eliminados."""
        carpeta = carpeta or CARPETA_DEFECTO
        if not os.path.isdir(carpeta):
            return []
        limite = datetime.now() - timedelta(days=dias_retener)
        eliminados = []
        for nombre in os.listdir(carpeta):
            if not nombre.endswith(".sql.gz"):
                continue
            if prefijo and not nombre.startswith(prefijo):
                continue
            ruta = os.path.join(carpeta, nombre)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(ruta))
                if mtime < limite:
                    os.remove(ruta)
                    eliminados.append(nombre)
            except OSError:
                continue
        if eliminados:
            log.info("Respaldos eliminados por retencion (%s dias): %s", dias_retener, eliminados)
        return eliminados
