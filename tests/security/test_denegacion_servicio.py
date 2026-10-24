"""Ataque: tumbar o saturar el sistema (DoS / DDoS a nivel de aplicacion).

- Inundacion de peticiones desde un equipo (flood).
- Esquivar el limite falsificando la cabecera X-Forwarded-For.
- Cuerpos gigantes, JSON anidado miles de niveles, formularios con miles de
  campos: buscan agotar memoria/CPU o reventar el parser.
- Subir un archivo malicioso disfrazado de imagen.

Estas pruebas corren dentro del proceso (cliente de pruebas de Flask). Las
que miden el servidor real bajo carga -- conexiones concurrentes,
slowloris, rafagas -- estan en scripts/seguridad/ataques.py (ver
docs/SEGURIDAD.md), porque necesitan sockets de verdad.
"""
import io
import json

import pytest

from app.utils.imagenes import leer_imagen_validada
from tests.security.conftest import login


def test_inundacion_desde_una_ip_se_corta_y_otra_ip_sigue_atendida(app, datos_base):
    """El atacante recibe 429 (barato de responder: no toca la base) y un
    empleado en otro equipo sigue trabajando normal."""
    cliente = app.test_client()
    atacante = {"REMOTE_ADDR": "192.168.1.66"}
    codigos = [cliente.get("/healthz", environ_overrides=atacante).status_code for _ in range(260)]
    assert 429 in codigos
    assert codigos.count(429) >= 50

    empleado = {"REMOTE_ADDR": "192.168.1.20"}
    assert cliente.get("/healthz", environ_overrides=empleado).status_code == 200


def test_falsificar_x_forwarded_for_no_esquiva_el_limite(app, datos_base):
    """Sin proxy de confianza configurado, la IP es la del socket: cambiar
    X-Forwarded-For en cada peticion no reinicia el contador."""
    cliente = app.test_client()
    codigos = []
    for i in range(260):
        r = cliente.get(
            "/healthz",
            headers={"X-Forwarded-For": "1.2.%d.%d" % (i // 250, i % 250), "X-Real-IP": "8.8.8.%d" % (i % 250)},
            environ_overrides={"REMOTE_ADDR": "192.168.1.77"},
        )
        codigos.append(r.status_code)
    assert 429 in codigos


def test_cuerpo_gigante_se_rechaza_con_413(app, datos_base):
    """MAX_CONTENT_LENGTH = 8 MB: un POST de 20 MB se corta sin leerlo."""
    cliente = app.test_client()
    login(cliente, "admin", "admin123")
    r = cliente.post(
        "/productos/api/crear",
        data=b"A" * (20 * 1024 * 1024),
        content_type="application/octet-stream",
    )
    assert r.status_code == 413


def test_formulario_con_miles_de_campos_no_tumba_el_servidor(app, datos_base):
    cliente = app.test_client()
    campos = "&".join("c%d=x" % i for i in range(20000))
    r = cliente.post("/login", data=campos, content_type="application/x-www-form-urlencoded")
    assert r.status_code in (400, 413, 429)


def test_json_anidado_miles_de_niveles_no_da_error_500(app, datos_base):
    """Una "bomba" de anidamiento ([[[[...]]]] x 100,000) agota la pila del
    parser de JSON. Debe terminar en un error del cliente, no en un 500 ni
    en un proceso caido."""
    cliente = app.test_client()
    login(cliente, "admin", "admin123")
    bomba = "[" * 100000 + "]" * 100000
    r = cliente.post("/clientes/api/crear", data=bomba, content_type="application/json")
    assert r.status_code in (400, 413), r.status_code
    # y el servidor sigue respondiendo
    assert cliente.get("/healthz").status_code == 200


def test_json_con_texto_enorme_en_un_campo(app, datos_base):
    cliente = app.test_client()
    login(cliente, "admin", "admin123")
    r = cliente.post("/clientes/api/crear", data=json.dumps({"nombre": "X" * (7 * 1024 * 1024)}),
                     content_type="application/json")
    assert r.status_code < 500 or r.status_code == 413


@pytest.mark.parametrize("nombre,contenido", [
    ("shell.png", b"<?php system($_GET['c']); ?>"),
    ("pagina.jpg", b"<html><script>alert(1)</script></html>"),
    ("imagen.gif", b"MZ\x90\x00 ejecutable de windows"),
    ("foto.webp", b"RIFF\x00\x00\x00\x00AVI LIST"),
    ("malo.svg", b"<svg onload=alert(1)>"),
    ("doble.png.exe", b"\x89PNG\r\n\x1a\n"),
])
def test_archivo_disfrazado_de_imagen_se_rechaza(nombre, contenido):
    from werkzeug.datastructures import FileStorage

    with pytest.raises(ValueError):
        leer_imagen_validada(FileStorage(stream=io.BytesIO(contenido), filename=nombre))


def test_imagen_real_si_se_acepta():
    from werkzeug.datastructures import FileStorage

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    datos, mime = leer_imagen_validada(FileStorage(stream=io.BytesIO(png), filename="ok.png"))
    assert mime == "image/png" and datos == png


def test_imagen_de_mas_de_5mb_se_rechaza():
    from werkzeug.datastructures import FileStorage

    grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024)
    with pytest.raises(ValueError):
        leer_imagen_validada(FileStorage(stream=io.BytesIO(grande), filename="g.png"))
