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
    for ruta in ("/recetas/", "/cocina/pendientes", "/ventas/pos"):
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
        "/reset-password/admin@quesillos.test/Admin",
        data={"password": "482915", "password_confirm": "482915"},
    )
    assert r.status_code == 302

    db.session.refresh(admin)
    assert verificar_password(admin.password_hash, "482915") is True
    assert admin.codigo_recuperacion is None
    assert _login(cliente, "admin", "482915").status_code == 302


def test_contrasenas_que_no_coinciden_no_se_guardan(app, db, datos_base):
    admin = datos_base["admin"]
    admin.codigo_recuperacion = "111222"
    admin.codigo_expiry = datetime.now() + timedelta(minutes=15)
    hash_original = admin.password_hash
    db.session.commit()

    cliente = app.test_client()
    # El paso de reset ahora exige haber verificado el codigo antes (queda
    # en la sesion, ya no viaja en la URL).
    r = cliente.post("/verify-code/admin@quesillos.test/Admin", data={"codigo": "111222"})
    assert r.status_code == 302

    r = cliente.post(
        "/reset-password/admin@quesillos.test/Admin",
        data={"password": "unaClave1", "password_confirm": "otraClave2"},
    )
    assert r.status_code == 200
    db.session.refresh(admin)
    assert admin.password_hash == hash_original


def test_reset_password_sin_verificar_codigo_antes_redirige(app, db, datos_base):
    """El paso 3 ya no acepta el codigo por la URL: sin pasar por
    verify-code primero, no debe dejar cambiar la contrasena."""
    admin = datos_base["admin"]
    admin.codigo_recuperacion = "999888"
    admin.codigo_expiry = datetime.now() + timedelta(minutes=15)
    db.session.commit()

    cliente = app.test_client()
    r = cliente.post(
        "/reset-password/admin@quesillos.test/Admin",
        data={"password": "otraClave1", "password_confirm": "otraClave1"},
    )
    assert r.status_code == 302
    assert "forgot-password" in r.headers["Location"]


# ------------------------------------------------------------------ PIN de 4 a 6 numeros
import pytest  # noqa: E402


def _entrar_como_admin(app):
    cliente = app.test_client()
    assert _login(cliente, "admin", "admin123").status_code == 302
    return cliente


def _nuevo_usuario(pin, usuario="pinprueba"):
    return {"usuario": usuario, "nombre_completo": "Prueba Pin", "correo": f"{usuario}@t.test",
            "telefono": "88888888", "id_rol": 1, "password": pin}


@pytest.mark.parametrize("pin", ["1234", "12345", "123456", "0000"])
def test_crear_usuario_acepta_pin_de_4_a_6_numeros(app, db, datos_base, pin):
    r = _entrar_como_admin(app).post("/usuarios/api/crear", data=_nuevo_usuario(pin))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["success"] is True


@pytest.mark.parametrize("pin", ["", "123", "1234567", "12345678", "12ab56", "abcdef", "12 456", "١٢٣٤"])
def test_crear_usuario_rechaza_pin_que_no_sea_de_4_a_6_numeros(app, db, datos_base, pin):
    r = _entrar_como_admin(app).post("/usuarios/api/crear", data=_nuevo_usuario(pin))
    assert r.status_code == 400
    assert "4 a 6" in r.get_json()["message"]


def test_el_pin_nuevo_sirve_para_entrar(app, db, datos_base):
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_nuevo_usuario("4821")).status_code == 200
    assert _login(app.test_client(), "pinprueba", "4821").status_code == 302


def test_cambiar_mi_pin_acepta_4_y_rechaza_8(app, db, datos_base):
    cliente = _entrar_como_admin(app)
    r = cliente.post("/configuracion/api/cambiar_password",
                     json={"password_actual": "admin123", "password_nueva": "12345678"})
    assert r.status_code == 400 and "4 a 6" in r.get_json()["message"]
    r = cliente.post("/configuracion/api/cambiar_password",
                     json={"password_actual": "admin123", "password_nueva": "9087"})
    assert r.status_code == 200
    assert _login(app.test_client(), "admin", "9087").status_code == 302


# ------------------------------------------------------------------ usuarios sin correo y datos obligatorios
def _form(**kw):
    datos = {"nombre_completo": "Persona", "usuario": "u1", "correo": "", "telefono": "", "id_rol": 3, "password": "1234"}
    datos.update(kw)
    return datos


def test_se_pueden_crear_varios_usuarios_sin_correo(app, db, datos_base):
    """Antes el segundo usuario sin correo fallaba: 'El correo '' ya esta en uso'."""
    admin = _entrar_como_admin(app)
    for i in range(1, 4):
        r = admin.post("/usuarios/api/crear", data=_form(usuario=f"mesero{i}"))
        assert r.status_code == 200, r.get_json()
    from app.models import Usuario
    assert Usuario.query.filter(Usuario.usuario.like("mesero%"), Usuario.correo.is_(None)).count() == 3


def test_correo_repetido_si_se_rechaza(app, db, datos_base):
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_form(usuario="a1", correo="x@t.test")).status_code == 200
    r = admin.post("/usuarios/api/crear", data=_form(usuario="a2", correo="x@t.test"))
    assert r.status_code == 400 and "correo" in r.get_json()["message"]


@pytest.mark.parametrize("campo,valor,texto", [("usuario", "  ", "usuario"), ("nombre_completo", "", "nombre"), ("id_rol", "", "rol"), ("id_rol", 9999, "rol")])
def test_crear_exige_usuario_nombre_y_rol(app, db, datos_base, campo, valor, texto):
    r = _entrar_como_admin(app).post("/usuarios/api/crear", data=_form(**{campo: valor}))
    assert r.status_code == 400
    assert texto in r.get_json()["message"].lower()


def test_el_usuario_se_guarda_sin_espacios_y_puede_entrar(app, db, datos_base):
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_form(usuario="  carla  ", password="2468")).status_code == 200
    assert _login(app.test_client(), "carla", "2468").status_code == 302


def test_editar_un_usuario_sin_correo_aunque_otro_tampoco_tenga(app, db, datos_base):
    from app.models import Usuario
    admin = _entrar_como_admin(app)
    for n in ("m1", "m2"):
        assert admin.post("/usuarios/api/crear", data=_form(usuario=n)).status_code == 200
    m2 = Usuario.query.filter_by(usuario="m2").first()
    r = admin.put(f"/usuarios/api/editar/{m2.id_usuario}",
                  data={"nombre_completo": "Nuevo Nombre", "usuario": "m2", "correo": "", "telefono": "", "id_rol": 3, "password": ""})
    assert r.status_code == 200, r.get_json()
