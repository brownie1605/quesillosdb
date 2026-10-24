"""Ataque: acceder a funciones del sistema sin iniciar sesion, o con un rol
que no corresponde. Y: enviar formularios desde otra pagina (CSRF).

Defensa que se valida: toda ruta exige sesion salvo una lista blanca
explicita; todo POST exige token CSRF; el rol Cajero no llega a lo del Admin.
"""
import re

import pytest

from tests.security.conftest import login

# Unicas rutas que pueden responder sin sesion (login, recuperacion de
# contrasena, salud para el monitor, PWA y archivos estaticos).
RUTAS_PUBLICAS = {
    "/", "/login", "/forgot-password", "/healthz", "/sw.js",
    "/api/roles-publicos", "/api/sync/health",
    "/api/forgot-password", "/api/verify-code", "/api/reset-password",
    "/verify-code/<email>/<rol>", "/verify_code/<email>/<rol>",
    "/reset-password/<email>/<rol>", "/static/<path:filename>",
    "/verificar-2fa",
}


def _url(regla):
    return re.sub(r"<(?:[a-z]+:)?[^>]+>", "1", regla)


def _reglas(app):
    for r in app.url_map.iter_rules():
        if r.rule not in RUTAS_PUBLICAS:
            yield r


def test_ninguna_ruta_privada_responde_sin_sesion(app, datos_base):
    """Barrido de TODAS las rutas registradas, con todos sus metodos."""
    cliente = app.test_client()
    expuestas = []
    for regla in _reglas(app):
        for metodo in regla.methods - {"HEAD", "OPTIONS"}:
            r = cliente.open(_url(regla.rule), method=metodo)
            # 302 a login, 401/403 o 400 (CSRF) son rechazos validos; 200 no.
            if r.status_code in (200, 201, 204):
                expuestas.append("%s %s -> %s" % (metodo, regla.rule, r.status_code))
    assert not expuestas, "Rutas privadas accesibles sin sesion:\n" + "\n".join(expuestas)


def test_todo_post_sin_token_csrf_es_rechazado(app, datos_base):
    """Un sitio ajeno no puede hacer que el navegador de un empleado envie
    un formulario: sin token CSRF, todo POST/PUT/DELETE/PATCH muere en 400."""
    cliente = app.test_client()
    login(cliente, "admin", "admin123")
    aceptados = []
    for regla in app.url_map.iter_rules():
        if regla.rule.startswith("/static"):
            continue
        for metodo in regla.methods & {"POST", "PUT", "DELETE", "PATCH"}:
            r = cliente.open(_url(regla.rule), method=metodo)
            if r.status_code != 400:
                aceptados.append("%s %s -> %s" % (metodo, regla.rule, r.status_code))
    assert not aceptados, "Rutas que aceptan POST sin CSRF:\n" + "\n".join(aceptados)


def test_cajero_no_entra_a_rutas_de_admin(app, datos_base):
    cliente = app.test_client()
    login(cliente, "cajero", "cajero123")
    # /configuracion/ NO va aqui: es autoservicio (tu propia contrasena y 2FA)
    # y es correcto que cualquier rol entre.
    for ruta in ("/recetas/", "/usuarios/", "/auditoria"):
        r = cliente.get(ruta)
        assert r.status_code in (302, 403), "%s -> %s" % (ruta, r.status_code)


def test_cookie_de_sesion_sin_acceso_desde_javascript(app, datos_base):
    cliente = app.test_client()
    r = login(cliente, "admin", "admin123")
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_cookie_falsificada_no_inicia_sesion(app, datos_base):
    """Sin la SECRET_KEY nadie puede fabricar una sesion de Admin."""
    cliente = app.test_client()
    cliente.set_cookie("session", "eyJfdXNlcl9pZCI6IjEiLCJfZnJlc2giOnRydWV9.aaaa.bbbb")
    assert cliente.get("/ventas/pos").status_code in (302, 401)


def test_logout_invalida_la_sesion(app, datos_base):
    cliente = app.test_client()
    login(cliente, "admin", "admin123")
    assert cliente.get("/recetas/").status_code == 200
    cliente.get("/logout")
    assert cliente.get("/recetas/").status_code in (302, 401)
