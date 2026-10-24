"""Ataque: meter codigo en los datos de entrada.

- SQL injection: que un texto como  ' OR '1'='1  cambie la consulta y deje
  entrar sin contrasena, o borre/lea tablas.
- XSS: guardar  <script>...</script>  en un dato (nombre, cliente...) para
  que se ejecute en el navegador de otro empleado al verlo.
- Path traversal: pedir  /static/../.env  para leer archivos del servidor.

Defensas que se validan: SQLAlchemy con parametros enlazados (nunca texto
concatenado), autoescape de Jinja y rutas de archivos normalizadas.
"""
import os
import re

import pytest

from app.models import Usuario
from tests.security.conftest import login, obtener_csrf

PAYLOADS_SQL = [
    "' OR '1'='1",
    "' OR 1=1 -- ",
    "admin'--",
    "admin' #",
    "\" OR \"\"=\"",
    "'; DROP TABLE usuarios; --",
    "' UNION SELECT usuario, password_hash FROM usuarios --",
    "1' AND SLEEP(5) --",
]

RUTAS_CON_FILTRO_DE_FECHA = [
    "/dashboard",
    "/api/dashboard_charts",
    "/reportes/api/resumen_ventas",
    "/reportes/api/resumen_financiero",
    "/reportes/api/propinas",
    "/reportes/api/descuentos",
    "/reportes/api/exportar/ventas",
    "/clientes/api/platillos_por_cliente",
    "/inventario/api/consumo",
]

PAYLOADS_XSS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert(1)>",
    "\"><svg/onload=alert(1)>",
]


@pytest.mark.parametrize("payload", PAYLOADS_SQL)
def test_sql_injection_en_el_login_no_deja_entrar(app, datos_base, payload):
    cliente = app.test_client()
    for usuario, password in ((payload, "x"), ("admin", payload), (payload, payload)):
        r = login(cliente, usuario, password, ip="10.9.%d.1" % (hash(payload) % 200))
        assert r.status_code in (200, 429), "el servidor fallo (%s) con %r" % (r.status_code, payload)
        assert cliente.get("/ventas/pos").status_code in (302, 401), "entro con %r" % payload


def test_sql_injection_no_destruye_ni_altera_la_base(app, datos_base, db):
    cliente = app.test_client()
    antes = Usuario.query.count()
    for i, p in enumerate(PAYLOADS_SQL):
        login(cliente, p, p, ip="10.8.0.%d" % i)
    assert Usuario.query.count() == antes  # la tabla sigue ahi y completa
    assert Usuario.query.filter_by(usuario="admin").one().estado == "activo"


@pytest.mark.parametrize("payload", PAYLOADS_SQL)
def test_sql_injection_en_filtros_de_reportes(app, datos_base, db, payload):
    """Los filtros de fecha llegan por la URL: con un payload no debe haber
    error 500 (que delataria la consulta) ni cambios en la base."""
    cliente = app.test_client()
    login(cliente, "admin", "admin123")
    antes = Usuario.query.count()
    fallas = []
    for ruta in RUTAS_CON_FILTRO_DE_FECHA:
        r = cliente.get(ruta, query_string={"inicio": payload, "fin": payload})
        cuerpo = r.get_data(as_text=True).lower()
        if r.status_code >= 500 or "sql" in cuerpo or "syntax" in cuerpo:
            fallas.append("%s -> %s %s" % (ruta, r.status_code, cuerpo[:120]))
    assert not fallas, "\n".join(fallas)
    assert Usuario.query.count() == antes


@pytest.mark.parametrize("payload", PAYLOADS_XSS)
def test_xss_guardado_se_muestra_escapado(app, datos_base, db, payload):
    """Un nombre con HTML se muestra como texto, nunca como etiqueta viva."""
    admin = Usuario.query.filter_by(usuario="admin").one()
    admin.nombre_completo = payload
    db.session.commit()

    cliente = app.test_client()
    login(cliente, "admin", "admin123")
    html = cliente.get("/recetas/").get_data(as_text=True)
    assert payload not in html
    assert "&lt;" in html


def test_xss_reflejado_en_login_se_escapa(app, datos_base):
    cliente = app.test_client()
    for p in PAYLOADS_XSS:
        html = login(cliente, p, "x", ip="10.7.0.1").get_data(as_text=True)
        assert p not in html


def test_plantillas_no_desactivan_el_autoescape():
    """Revision estatica: ninguna plantilla marca datos como seguros a mano
    (|safe, autoescape false) salvo |tojson|safe, que ya viene escapado."""
    raiz = os.path.join(os.path.dirname(__file__), "..", "..", "app", "templates")
    peligrosos = []
    for carpeta, _, archivos in os.walk(raiz):
        for nombre in archivos:
            if not nombre.endswith(".html"):
                continue
            ruta = os.path.join(carpeta, nombre)
            with open(ruta, encoding="utf-8") as f:
                for n, linea in enumerate(f, 1):
                    sin_tojson = re.sub(r"tojson\s*\|\s*safe", "", linea)
                    if re.search(r"\|\s*safe\b|autoescape\s+false", sin_tojson):
                        peligrosos.append("%s:%d" % (ruta, n))
    assert not peligrosos, "Salida sin escapar:\n" + "\n".join(peligrosos)


@pytest.mark.parametrize("ruta", [
    "/static/../.env",
    "/static/..%2f..%2f.env",
    "/static/%2e%2e/%2e%2e/.env",
    "/static/../../app/config/config.py",
    "/static/..\\..\\.env",
])
def test_path_traversal_no_lee_archivos_del_servidor(app, ruta):
    r = app.test_client().get(ruta)
    assert r.status_code in (400, 404)
    cuerpo = r.get_data(as_text=True)
    assert "SECRET_KEY" not in cuerpo and "DB_LOCAL_PASSWORD" not in cuerpo


def test_errores_no_muestran_traza_ni_detalles_internos(app, datos_base):
    cliente = app.test_client()
    html = cliente.get("/no-existe-%s" % ("A" * 50)).get_data(as_text=True)
    assert "Traceback" not in html and "sqlalchemy" not in html.lower()
    assert not app.debug


def test_healthz_no_filtra_detalles_de_la_base(app, monkeypatch):
    """Si la base cae, /healthz (publico) responde 503 sin el texto del error,
    que puede traer host y usuario de MySQL."""
    from app.extensions import db

    def falla(*a, **k):
        raise RuntimeError("Can't connect to MySQL server on '10.0.0.5' (user 'root')")

    monkeypatch.setattr(db.session, "execute", falla)
    r = app.test_client().get("/healthz")
    assert r.status_code == 503
    assert "10.0.0.5" not in r.get_data(as_text=True)
    assert "root" not in r.get_data(as_text=True)
