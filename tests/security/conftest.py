"""Fixtures de la suite de seguridad.

A diferencia del resto de pruebas (tests/conftest.py), aqui los controles de
seguridad estan ENCENDIDOS: CSRF y limite de peticiones reales. Si se
apagaran, no se estaria probando lo que de verdad corre en el restaurante.
Se sobreescribe la fixture `app` para que `datos_base`, `db`, etc. del
conftest padre sigan funcionando con esta configuracion.
"""
import re

import pytest

from app import create_app
from app.config.config import Config
from app.extensions import db as _db, limiter


class SecureTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_BINDS = {}
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SYNC_ENABLED = False
    SECRET_KEY = "clave-de-prueba-de-seguridad"
    WTF_CSRF_ENABLED = True
    RATELIMIT_ENABLED = True


@pytest.fixture()
def app():
    aplicacion = create_app(SecureTestConfig, iniciar_jobs=False)
    with aplicacion.app_context():
        _db.create_all()
        limiter.reset()  # el limitador es global: cada prueba parte de cero
        yield aplicacion
        _db.session.remove()
        _db.drop_all()


def obtener_csrf(cliente, ruta="/login", ip="127.0.0.1"):
    """Lee el token CSRF del formulario, como lo haria un navegador."""
    html = cliente.get(ruta, environ_overrides={"REMOTE_ADDR": ip}).get_data(as_text=True)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html) or re.search(
        r'value="([^"]+)"[^>]*name="csrf_token"', html
    )
    assert m, "la pagina %s no trae token CSRF" % ruta
    return m.group(1)


def login(cliente, usuario, password, ip="10.0.0.1"):
    """POST /login con CSRF valido, simulando que viene de `ip`."""
    token = obtener_csrf(cliente, ip=ip)
    return cliente.post(
        "/login",
        data={"usuario": usuario, "password": password, "csrf_token": token},
        environ_overrides={"REMOTE_ADDR": ip},
    )
