"""Autenticacion, roles y recuperacion de contrasena."""
from datetime import datetime, timedelta

from app.services.auth_service import verificar_password, generar_password


def _login(cliente, usuario, password):
    return cliente.post(
        "/login", data={"usuario": usuario, "password": password}, follow_redirects=False
    )


# ------------------------------------------------------------------ login
def test_login_correcto_redirige(app, datos_base):
    cliente = app.test_client()
    r = _login(cliente, "admin", "admin123")
    assert r.status_code == 302


def test_login_con_password_incorrecta_no_entra(app, datos_base):
    cliente = app.test_client()
    r = _login(cliente, "admin", "malaclave")
    assert r.status_code == 200  # vuelve a mostrar el formulario


def test_hash_de_password_funciona():
    h = generar_password("secreta123")
    assert h != "secreta123"
    assert verificar_password(h, "secreta123") is True
    assert verificar_password(h, "otra") is False


# ------------------------------------------------------------------ roles
def test_rutas_protegidas_exigen_sesion(app, datos_base):
    cliente = app.test_client()
    for ruta in ("/recetas/", "/insumos/", "/cocina/pendientes", "/ventas/pos"):
        r = cliente.get(ruta)
        assert r.status_code in (302, 401), ruta


def test_el_cajero_no_entra_a_recetas(app, datos_base):
    cliente = app.test_client()
    _login(cliente, "cajero", "cajero123")
    r = cliente.get("/recetas/")
    assert r.status_code == 302  # redirigido, sin permiso


def test_el_admin_si_entra_a_recetas(app, datos_base):
    cliente = app.test_client()
    _login(cliente, "admin", "admin123")
    r = cliente.get("/recetas/")
    assert r.status_code == 200


def test_helper_de_roles(app, datos_base):
    admin = datos_base["admin"]
    cajero = datos_base["cajero"]
    assert admin.es_admin is True
    assert admin.tiene_rol("Admin") is True
    assert cajero.es_admin is False
    assert cajero.tiene_rol("Cajero") is True
    assert cajero.tiene_rol("Cocinero") is False


def test_el_cajero_si_entra_al_punto_de_venta(app, datos_base):
    cliente = app.test_client()
    _login(cliente, "cajero", "cajero123")
    assert cliente.get("/ventas/pos").status_code == 200


# --------------------------------------------- recuperacion de contrasena
def test_formulario_de_recuperacion_lista_los_roles(app, datos_base):
    cliente = app.test_client()
    r = cliente.get("/forgot-password")
    assert r.status_code == 200
    cuerpo = r.get_data(as_text=True)
    for rol in ("Admin", "Cajero", "Mesero", "Cocinero"):
        assert rol in cuerpo


def test_correo_o_rol_incorrecto_no_genera_codigo(app, db, datos_base):
    cliente = app.test_client()
    cliente.post(
        "/forgot-password",
        data={"email": "admin@quesillos.test", "rol": "Cocinero"},  # rol equivocado
        follow_redirects=True,
    )
    db.session.refresh(datos_base["admin"])
    assert datos_base["admin"].codigo_recuperacion is None


def test_correo_y_rol_correctos_generan_codigo_de_6_digitos(app, db, datos_base):
    cliente = app.test_client()
    cliente.post(
        "/forgot-password",
        data={"email": "admin@quesillos.test", "rol": "Admin"},
        follow_redirects=False,
    )
    db.session.refresh(datos_base["admin"])
    codigo = datos_base["admin"].codigo_recuperacion
    assert codigo is not None
    assert len(codigo) == 6 and codigo.isdigit()
    assert datos_base["admin"].codigo_expiry > datetime.now()


def test_codigo_incorrecto_no_deja_pasar(app, db, datos_base):
    admin = datos_base["admin"]
    admin.codigo_recuperacion = "123456"
    admin.codigo_expiry = datetime.now() + timedelta(minutes=15)
    db.session.commit()

    cliente = app.test_client()
    r = cliente.post(
        "/verify-code/admin@quesillos.test/Admin", data={"codigo": "999999"}
    )
    assert r.status_code == 200
    assert "incorrecto" in r.get_data(as_text=True).lower()


def test_codigo_expirado_manda_a_pedir_otro(app, db, datos_base):
    admin = datos_base["admin"]
    admin.codigo_recuperacion = "123456"
    admin.codigo_expiry = datetime.now() - timedelta(minutes=1)
    db.session.commit()

    cliente = app.test_client()
    r = cliente.post("/verify-code/admin@quesillos.test/Admin", data={"codigo": "123456"})
    assert r.status_code == 302
    assert "forgot-password" in r.headers["Location"]


def test_flujo_completo_cambia_la_contrasena(app, db, datos_base):
    admin = datos_base["admin"]
    admin.codigo_recuperacion = "654321"
    admin.codigo_expiry = datetime.now() + timedelta(minutes=15)
    db.session.commit()

    cliente = app.test_client()
    r = cliente.post("/verify-code/admin@quesillos.test/Admin", data={"codigo": "654321"})
    assert r.status_code == 302

    r = cliente.post(
        "/reset-password/admin@quesillos.test/Admin/654321",
        data={"password": "nuevaClave1", "password_confirm": "nuevaClave1"},
    )
    assert r.status_code == 302

    db.session.refresh(admin)
    assert verificar_password(admin.password_hash, "nuevaClave1") is True
    assert admin.codigo_recuperacion is None
    assert _login(cliente, "admin", "nuevaClave1").status_code == 302


def test_contrasenas_que_no_coinciden_no_se_guardan(app, db, datos_base):
    admin = datos_base["admin"]
    admin.codigo_recuperacion = "111222"
    admin.codigo_expiry = datetime.now() + timedelta(minutes=15)
    hash_original = admin.password_hash
    db.session.commit()

    cliente = app.test_client()
    r = cliente.post(
        "/reset-password/admin@quesillos.test/Admin/111222",
        data={"password": "unaClave1", "password_confirm": "otraClave2"},
    )
    assert r.status_code == 200
    db.session.refresh(admin)
    assert admin.password_hash == hash_original
