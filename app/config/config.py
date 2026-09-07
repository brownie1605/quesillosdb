import os
import secrets
from dotenv import load_dotenv

load_dotenv()


def _mysql_uri(user, password, host, port, name):
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


# Si falta SECRET_KEY en el .env, antes se usaba un valor fijo escrito en
# este archivo ("quesillos-lo-nuestro-dev-key") -- con esa clave adivinable
# cualquiera puede firmar su propia cookie de sesion y entrar como
# cualquier usuario, incluido Admin, sin saber ninguna contrasena. Ahora,
# si falta, se genera una aleatoria en cada arranque: sigue sin ser lo
# ideal (cierra sesion a todos al reiniciar), pero ya no es adivinable, y
# la inestabilidad es una señal clara de que hay que configurarla en .env.
_SECRET_KEY_FALLBACK = secrets.token_hex(32)


class Config:
    """Configuracion base del sistema hibrido Local <-> Nube."""

    SECRET_KEY = os.getenv("SECRET_KEY") or _SECRET_KEY_FALLBACK

    # Sin esto, con FLASK_ENV=production (debug=False) Jinja cachea las
    # plantillas compiladas en memoria y un cambio en un .html no se ve
    # hasta reiniciar el proceso -- confundio varias veces durante
    # desarrollo. Costo en produccion real: nulo para este tamano de app
    # (una sola maquina, trafico bajo), y evita ese reinicio manual.
    TEMPLATES_AUTO_RELOAD = True

    # ------------------------------------------------------------------
    # Cookie de sesion: sin esto, Flask usa los defaults del navegador
    # (razonables, pero mejor fijarlos explicitos). SESSION_COOKIE_SECURE
    # se activa solo si de verdad se sirve por HTTPS -- si se pone en True
    # sin HTTPS, el navegador jamas manda la cookie y nadie puede loguearse.
    # ------------------------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME_SECONDS", 8 * 60 * 60))  # 8h

    # Limite global de tamano de subida (ej. imagenes de producto/usuario):
    # sin esto, Flask acepta cuerpos de request de cualquier tamano.
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB

    # ------------------------------------------------------------------
    # CSRF (Flask-WTF). Sin tiempo limite propio: dura lo que dure la
    # sesion (PERMANENT_SESSION_LIFETIME) en vez de expirar aparte a la
    # hora -- una caja con una mesa abierta mucho rato no debe toparse
    # con un "token invalido" al momento de cobrar.
    # ------------------------------------------------------------------
    WTF_CSRF_TIME_LIMIT = None

    # ------------------------------------------------------------------
    # Rate limiting (Flask-Limiter). Storage en memoria: valido porque el
    # Procfile corre un solo worker (ver notas de Flask-SocketIO async_mode
    # "threading", que ya exige un solo proceso).
    # ------------------------------------------------------------------
    RATELIMIT_STORAGE_URI = "memory://"

    # ------------------------------------------------------------------
    # Base de datos LOCAL (motor primario: la app SIEMPRE escribe aqui)
    # ------------------------------------------------------------------
    DB_LOCAL_USER = os.getenv("DB_LOCAL_USER", "root")
    DB_LOCAL_PASSWORD = os.getenv("DB_LOCAL_PASSWORD", "")
    DB_LOCAL_HOST = os.getenv("DB_LOCAL_HOST", "localhost")
    DB_LOCAL_PORT = os.getenv("DB_LOCAL_PORT", "3306")
    DB_LOCAL_NAME = os.getenv("DB_LOCAL_NAME", "quesillos_local")

    SQLALCHEMY_DATABASE_URI = _mysql_uri(
        DB_LOCAL_USER, DB_LOCAL_PASSWORD, DB_LOCAL_HOST, DB_LOCAL_PORT, DB_LOCAL_NAME
    )

    # ------------------------------------------------------------------
    # Base de datos REMOTA (nube - Railway). Bind secundario "cloud".
    # ------------------------------------------------------------------
    DB_REMOTE_USER = os.getenv("DB_REMOTE_USER", os.getenv("DB_USER", "root"))
    DB_REMOTE_PASSWORD = os.getenv("DB_REMOTE_PASSWORD", os.getenv("DB_PASSWORD", ""))
    DB_REMOTE_HOST = os.getenv("DB_REMOTE_HOST", os.getenv("DB_HOST", ""))
    DB_REMOTE_PORT = os.getenv("DB_REMOTE_PORT", os.getenv("DB_PORT", "3306"))
    DB_REMOTE_NAME = os.getenv("DB_REMOTE_NAME", os.getenv("DB_NAME", "pos_inventario_cloud"))

    SQLALCHEMY_BINDS = {
        "cloud": _mysql_uri(
            DB_REMOTE_USER, DB_REMOTE_PASSWORD, DB_REMOTE_HOST, DB_REMOTE_PORT, DB_REMOTE_NAME
        )
    }

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 10,
        "max_overflow": 20,
    }

    # ------------------------------------------------------------------
    # Sincronizacion
    # ------------------------------------------------------------------
    SYNC_ENABLED = os.getenv("SYNC_ENABLED", "true").lower() == "true"
    SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", 120))       # segundos entre syncs
    NETWORK_CHECK_INTERVAL = int(os.getenv("NETWORK_CHECK_INTERVAL", 30))
    SYNC_TIMEOUT = int(os.getenv("SYNC_TIMEOUT", 30))
    SYNC_BATCH_SIZE = int(os.getenv("SYNC_BATCH_SIZE", 200))

    # ------------------------------------------------------------------
    # Respaldos automaticos (independientes de la sincronizacion)
    # ------------------------------------------------------------------
    BACKUP_INTERVALO_HORAS = int(os.getenv("BACKUP_INTERVALO_HORAS", 24))
    BACKUP_RETENCION_DIAS = int(os.getenv("BACKUP_RETENCION_DIAS", 14))

    # Empresa / sucursal fijas (instalacion de 1 sola sucursal)
    ID_EMPRESA = int(os.getenv("ID_EMPRESA", 1))
    ID_SUCURSAL = int(os.getenv("ID_SUCURSAL", 1))
    DEVICE_ID = os.getenv("DEVICE_ID", "local-01")

    # Rango de IDs reservado para los registros creados en ESTA maquina.
    # La nube usa 1..999999; lo local empieza en LOCAL_ID_OFFSET.
    # Evita que un INSERT local pise un registro distinto con el mismo id
    # en la nube al sincronizar.
    LOCAL_ID_OFFSET = int(os.getenv("LOCAL_ID_OFFSET", 1000000))

    # ------------------------------------------------------------------
    # Correo (recuperacion de contrasena con codigo de 6 digitos)
    # ------------------------------------------------------------------
    MAIL_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("SMTP_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.getenv("SMTP_USER", "quesilloslonuestro26@gmail.com")
    MAIL_PASSWORD = os.getenv("SMTP_PASS", "")
    MAIL_DEFAULT_SENDER = (
        os.getenv("MAIL_SENDER_NAME", "Quesillos Lo Nuestro"),
        os.getenv("SMTP_USER", "quesilloslonuestro26@gmail.com"),
    )
    PASSWORD_RECOVERY_TIMEOUT = int(os.getenv("PASSWORD_RECOVERY_TIMEOUT", 900))
