import os
from dotenv import load_dotenv

load_dotenv()


def _mysql_uri(user, password, host, port, name):
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


class Config:
    """Configuracion base del sistema hibrido Local <-> Nube."""

    SECRET_KEY = os.getenv("SECRET_KEY", "quesillos-lo-nuestro-dev-key")

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

    # Empresa / sucursal fijas (instalacion de 1 sola sucursal)
    ID_EMPRESA = int(os.getenv("ID_EMPRESA", 1))
    ID_SUCURSAL = int(os.getenv("ID_SUCURSAL", 1))
    DEVICE_ID = os.getenv("DEVICE_ID", "local-01")

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
