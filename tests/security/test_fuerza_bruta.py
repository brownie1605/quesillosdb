"""Ataque: adivinar contrasenas o codigos probando muchas combinaciones
(fuerza bruta / credential stuffing), y descubrir que usuarios existen.

Defensas que se validan: limite de peticiones por IP y por usuario, bloqueo
temporal de la cuenta, y respuestas que no revelan si el usuario existe.
"""
from datetime import datetime, timedelta

import pyotp

from app.models import Usuario
from app.models.usuario import RecuperacionPassword
from tests.security.conftest import login, obtener_csrf


def test_el_mismo_usuario_se_corta_a_los_6_intentos_aunque_cambie_de_ip(app, datos_base):
    """Un atacante distribuido (muchas IP) contra UNA cuenta: el limite por
    usuario lo corta aunque cada IP haya hecho un solo intento."""
    cliente = app.test_client()
    codigos = [
        login(cliente, "admin", "clave-mala-%d" % i, ip="10.1.0.%d" % i).status_code
        for i in range(1, 9)
    ]
    assert 429 in codigos
    assert codigos.index(429) <= 5  # a lo mucho el 6to intento


def test_una_sola_ip_probando_usuarios_distintos_se_corta(app, datos_base):
    """Un solo equipo lanzando un diccionario de usuarios: el limite por IP
    (15/min) lo corta aunque cada nombre se pruebe una sola vez."""
    cliente = app.test_client()
    token = obtener_csrf(cliente, ip="10.2.0.1")
    codigos = [
        cliente.post(
            "/login",
            data={"usuario": "usuario%d" % i, "password": "x", "csrf_token": token},
            environ_overrides={"REMOTE_ADDR": "10.2.0.1"},
        ).status_code
        for i in range(25)
    ]
    assert 429 in codigos
    assert codigos.index(429) <= 15


def test_cuenta_se_bloquea_tras_5_fallos_y_rechaza_hasta_la_clave_correcta(app, datos_base, db):
    cliente = app.test_client()
    for i in range(5):
        login(cliente, "cajero", "mala", ip="10.3.0.%d" % i)
    cajero = Usuario.query.filter_by(usuario="cajero").one()
    assert cajero.bloqueado_hasta and cajero.bloqueado_hasta > datetime.now()
    # Con la contrasena CORRECTA tampoco entra mientras dure el bloqueo.
    # 200 = se queda en el formulario; 429 = ya lo corto el limite por usuario.
    r = login(cliente, "cajero", "cajero123", ip="10.3.1.1")
    assert r.status_code in (200, 429)
    assert cliente.get("/ventas/pos").status_code in (302, 401)


def test_usuario_inexistente_y_clave_mala_dan_la_misma_respuesta(app, datos_base):
    """No se debe poder distinguir 'no existe' de 'clave incorrecta'."""
    cliente = app.test_client()
    a = login(cliente, "admin", "mala", ip="10.4.0.1")
    b = login(cliente, "fantasma", "mala", ip="10.4.0.2")
    assert a.status_code == b.status_code == 200
    assert (a.get_data() == b.get_data()) or (
        "incorrectos" in a.get_data(as_text=True) and "incorrectos" in b.get_data(as_text=True)
    )


def test_recuperar_contrasena_no_revela_si_el_correo_existe(app, datos_base):
    cliente = app.test_client()
    token = obtener_csrf(cliente, "/forgot-password")
    existe = cliente.post("/api/forgot-password", json={"correo": "admin@quesillos.test", "rol": "Admin"},
                          headers={"X-CSRFToken": token})
    no_existe = cliente.post("/api/forgot-password", json={"correo": "nadie@x.com", "rol": "Admin"},
                             headers={"X-CSRFToken": token})
    assert existe.status_code == no_existe.status_code
    assert existe.get_json()["message"] == no_existe.get_json()["message"]


def test_codigo_de_recuperacion_se_invalida_tras_5_fallos_por_la_api(app, datos_base, db):
    """El codigo es de 6 digitos (1 millon). Tras 5 fallos debe morir, tambien
    por la API JSON (antes solo moria el de la via web)."""
    cliente = app.test_client()
    token = obtener_csrf(cliente, "/forgot-password")
    cabeceras = {"X-CSRFToken": token}
    cliente.post("/api/forgot-password", json={"correo": "admin@quesillos.test", "rol": "Admin"},
                 headers=cabeceras)
    real = RecuperacionPassword.query.filter_by(usado=False).one().codigo

    for _ in range(5):
        r = cliente.post("/api/verify-code", json={"correo": "admin@quesillos.test", "codigo": "000000"},
                         headers=cabeceras)
        assert r.get_json()["success"] is False

    # Ya con el codigo REAL, no sirve: hay que pedir uno nuevo.
    r = cliente.post("/api/verify-code", json={"correo": "admin@quesillos.test", "codigo": real},
                     headers=cabeceras)
    assert r.get_json()["success"] is False


def test_codigos_de_recuperacion_no_son_predecibles(app):
    """Deben salir de `secrets` (CSPRNG), no de `random`: 200 codigos sin
    repetirse en bloque y con todos los digitos representados."""
    from app.routes.auth_routes import _generar_codigo

    codigos = {_generar_codigo() for _ in range(200)}
    assert len(codigos) > 190
    assert all(len(c) == 6 and c.isdigit() for c in codigos)
    assert len({d for c in codigos for d in c}) == 10


def test_2fa_bloquea_la_cuenta_tras_5_codigos_malos(app, datos_base, db):
    """Quien ya sabe la contrasena no puede probar los 1,000,000 de codigos
    TOTP: a los 5 fallos la cuenta se bloquea, aunque cambie de IP."""
    secreto = pyotp.random_base32()
    admin = Usuario.query.filter_by(usuario="admin").one()
    admin.totp_secret = secreto
    admin.totp_habilitado = True
    db.session.commit()

    cliente = app.test_client()
    assert login(cliente, "admin", "admin123").status_code == 302  # pasa al 2do paso
    for i in range(5):
        token = obtener_csrf(cliente, "/verificar-2fa")
        cliente.post("/verificar-2fa", data={"codigo": "00000%d" % i, "csrf_token": token},
                     environ_overrides={"REMOTE_ADDR": "10.5.0.%d" % i})
    db.session.refresh(admin)
    assert admin.bloqueado_hasta and admin.bloqueado_hasta > datetime.now()

    # Ni siquiera el codigo CORRECTO entra mientras dura el bloqueo.
    token = obtener_csrf(cliente)
    r = cliente.post("/verificar-2fa",
                     data={"codigo": pyotp.TOTP(secreto).now(), "csrf_token": token})
    assert cliente.get("/ventas/pos").status_code in (302, 401)
    assert r.status_code in (302, 200)
