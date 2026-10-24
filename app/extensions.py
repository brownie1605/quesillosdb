# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
# Sin cors_allowed_origins="*": con "*" cualquier pagina web abierta en el
# navegador de un empleado podia abrir un WebSocket a la caja con la cookie
# de sesion de ese empleado (Cross-Site WebSocket Hijacking). Por defecto
# Flask-SocketIO solo acepta el mismo origen, que cubre a todo equipo del
# local que entre por la IP/nombre del servidor.
socketio = SocketIO(async_mode="threading")
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])
