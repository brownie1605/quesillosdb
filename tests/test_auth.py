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


# ------------------------------------------------------------------ desbloqueo, reactivacion y roles
def _borrar(cliente, id_usuario):
    return cliente.delete(f"/usuarios/api/eliminar/{id_usuario}")


def test_cambiar_el_pin_desbloquea_la_cuenta(app, db, datos_base):
    from app.models import Usuario
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_form(usuario="bloq", password="4821")).status_code == 200
    u = Usuario.query.filter_by(usuario="bloq").first()
    u.bloqueado_hasta = datetime.now() + timedelta(minutes=15)               # como tras 5 intentos fallidos
    u.intentos_fallidos = 3
    db.session.commit()
    assert _login(app.test_client(), "bloq", "4821").status_code == 200      # bloqueado: ni el PIN bueno entra
    r = admin.put(f"/usuarios/api/editar/{u.id_usuario}",
                  data={"nombre_completo": "Persona", "usuario": "bloq", "correo": "", "telefono": "", "id_rol": 3, "password": "7531"})
    assert r.status_code == 200
    assert _login(app.test_client(), "bloq", "7531").status_code == 302      # con el PIN nuevo entra enseguida


def test_editar_sin_cambiar_el_pin_no_desbloquea(app, db, datos_base):
    from app.models import Usuario
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_form(usuario="bloq2", password="4821")).status_code == 200
    u = Usuario.query.filter_by(usuario="bloq2").first()
    u.bloqueado_hasta = datetime.now() + timedelta(minutes=15)
    db.session.commit()
    admin.put(f"/usuarios/api/editar/{u.id_usuario}",
              data={"nombre_completo": "Otro Nombre", "usuario": "bloq2", "correo": "", "telefono": "", "id_rol": 3, "password": ""})
    db.session.refresh(u)
    assert u.bloqueado_hasta is not None


def test_crear_con_el_nombre_de_un_eliminado_reactiva_esa_cuenta(app, db, datos_base):
    from app.models import Usuario
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_form(usuario="vuelve", nombre_completo="Primera Persona", password="1111")).status_code == 200
    u = Usuario.query.filter_by(usuario="vuelve").first()
    id_original = u.id_usuario
    u.totp_habilitado = True; u.totp_secret = "SECRETOVIEJO"; u.imagen_datos = b"x"; u.imagen_url = "/usuarios/imagen/1"
    db.session.commit()
    assert _borrar(admin, id_original).status_code == 200
    assert _login(app.test_client(), "vuelve", "1111").status_code == 200    # eliminado: no entra

    r = admin.post("/usuarios/api/crear", data=_form(usuario="vuelve", nombre_completo="Segunda Persona", password="2222", id_rol=2))
    assert r.status_code == 200 and r.get_json().get("reactivado") is True
    assert Usuario.query.filter_by(usuario="vuelve").count() == 1            # misma cuenta, no una fila duplicada
    db.session.refresh(u)
    assert u.id_usuario == id_original and u.estado == "activo"
    assert u.nombre_completo == "Segunda Persona" and u.id_rol == 2
    assert u.totp_habilitado is False and u.totp_secret is None              # sin el 2FA de la persona anterior
    assert u.imagen_datos is None and u.imagen_url is None                   # sin la foto de la anterior
    assert _login(app.test_client(), "vuelve", "1111").status_code == 200    # el PIN viejo ya no sirve
    assert _login(app.test_client(), "vuelve", "2222").status_code == 302    # el nuevo si


def test_un_usuario_activo_o_de_otra_empresa_no_se_reactiva(app, db, datos_base):
    from app.models import Empresa, Usuario
    from app.services.auth_service import generar_password
    from app.utils.date_utils import nicaragua_now
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_form(usuario="activo1")).status_code == 200
    r = admin.post("/usuarios/api/crear", data=_form(usuario="activo1"))
    assert r.status_code == 400 and "ya está en uso" in r.get_json()["message"]

    db.session.add(Empresa(id_empresa=2, nombre="Otra", estado="activo"))
    db.session.add(Usuario(id_empresa=2, id_sucursal=2, id_rol=datos_base["roles"]["Mesero"].id_rol, usuario="ajeno",
                           nombre_completo="De Otra Empresa", password_hash=generar_password("1234"),
                           estado="inactivo", fecha_creacion=nicaragua_now()))
    db.session.commit()
    r = admin.post("/usuarios/api/crear", data=_form(usuario="ajeno"))
    assert r.status_code == 400 and "ya está en uso" in r.get_json()["message"]


def _roles_visibles(cliente):
    return cliente.get("/usuarios/api/roles").get_json()


def test_la_lista_de_roles_es_de_mi_empresa_y_sin_repetidos_sin_uso(app, db, datos_base):
    from app.models import Empresa, Rol
    db.session.add(Empresa(id_empresa=2, nombre="Otra", estado="activo"))
    db.session.flush()
    repetido = Rol(id_empresa=1, nombre="Cajero", estado="activo")           # duplicado de Cajero, sin personas
    ajeno = Rol(id_empresa=2, nombre="Gerente", estado="activo")             # de otra empresa
    db.session.add_all([repetido, ajeno]); db.session.commit()

    roles = _roles_visibles(_entrar_como_admin(app))
    nombres = [r["nombre"] for r in roles]
    assert sorted(nombres) == sorted(["Admin", "Cajero", "Mesero", "Cocinero"])
    assert "Gerente" not in nombres
    assert repetido.id_rol not in [r["id_rol"] for r in roles]


def test_un_rol_repetido_con_personas_asignadas_se_conserva(app, db, datos_base):
    from app.models import Rol
    repetido = Rol(id_empresa=1, nombre="Cajero", estado="activo")
    db.session.add(repetido); db.session.commit()
    admin = _entrar_como_admin(app)
    assert admin.post("/usuarios/api/crear", data=_form(usuario="con_rol_repetido", id_rol=repetido.id_rol)).status_code == 200
    ids = [r["id_rol"] for r in _roles_visibles(admin) if r["nombre"] == "Cajero"]
    assert repetido.id_rol in ids and datos_base["roles"]["Cajero"].id_rol in ids   # ninguno queda sin mostrarse


def test_no_se_puede_asignar_un_rol_de_otra_empresa(app, db, datos_base):
    from app.models import Empresa, Rol, Usuario
    db.session.add(Empresa(id_empresa=2, nombre="Otra", estado="activo")); db.session.flush()
    ajeno = Rol(id_empresa=2, nombre="Gerente", estado="activo"); db.session.add(ajeno); db.session.commit()
    admin = _entrar_como_admin(app)
    r = admin.post("/usuarios/api/crear", data=_form(usuario="rol_ajeno", id_rol=ajeno.id_rol))
    assert r.status_code == 400 and "rol" in r.get_json()["message"].lower()

    assert admin.post("/usuarios/api/crear", data=_form(usuario="rol_ok")).status_code == 200
    u = Usuario.query.filter_by(usuario="rol_ok").first()
    r = admin.put(f"/usuarios/api/editar/{u.id_usuario}",
                  data={"nombre_completo": "P", "usuario": "rol_ok", "correo": "", "telefono": "", "id_rol": ajeno.id_rol, "password": ""})
    assert r.status_code == 400


def test_un_rol_de_otra_empresa_con_personas_activas_sigue_visible(app, db, datos_base):
    """Dato viejo: un usuario de mi empresa con un rol (de otra empresa) que aqui no existe. Debe verse."""
    from app.models import Empresa, Rol, Usuario
    db.session.add(Empresa(id_empresa=2, nombre="Otra", estado="activo")); db.session.flush()
    ajeno = Rol(id_empresa=2, nombre="Gerente", estado="activo"); db.session.add(ajeno); db.session.commit()
    cajero = Usuario.query.filter_by(usuario="cajero").first()
    cajero.id_rol = ajeno.id_rol
    db.session.commit()
    assert ajeno.id_rol in [r["id_rol"] for r in _roles_visibles(_entrar_como_admin(app))]


def test_un_rol_de_otra_empresa_con_el_mismo_nombre_que_uno_mio_no_se_muestra(app, db, datos_base):
    """Si no, el unico 'Cajero' que se ve seria uno que el servidor rechaza al crear usuarios."""
    from app.models import Empresa, Rol, Usuario
    db.session.add(Empresa(id_empresa=2, nombre="Otra", estado="activo")); db.session.flush()
    ajeno = Rol(id_empresa=2, nombre="Cajero", estado="activo"); db.session.add(ajeno); db.session.commit()
    Usuario.query.filter_by(usuario="cajero").first().id_rol = ajeno.id_rol
    db.session.commit()
    admin = _entrar_como_admin(app)
    roles = _roles_visibles(admin)
    assert ajeno.id_rol not in [r["id_rol"] for r in roles]
    propio = [r["id_rol"] for r in roles if r["nombre"] == "Cajero"]
    assert propio == [datos_base["roles"]["Cajero"].id_rol]
    assert admin.post("/usuarios/api/crear", data=_form(usuario="nuevo_cajero", id_rol=propio[0])).status_code == 200


def test_quien_tiene_un_rol_de_otra_empresa_se_ve_con_el_rol_propio_del_mismo_nombre(app, db, datos_base):
    """Se ve con su rol de siempre al editarlo; al guardar queda con el de la empresa."""
    from app.models import Empresa, Rol, Usuario
    db.session.add(Empresa(id_empresa=2, nombre="Otra", estado="activo")); db.session.flush()
    ajeno = Rol(id_empresa=2, nombre="Cajero", estado="activo"); db.session.add(ajeno); db.session.commit()
    cajero = Usuario.query.filter_by(usuario="cajero").first()
    cajero.id_rol = ajeno.id_rol
    db.session.commit()
    admin = _entrar_como_admin(app)
    fila = next(u for u in admin.get("/usuarios/api/list").get_json() if u["usuario"] == "cajero")
    assert fila["id_rol"] == datos_base["roles"]["Cajero"].id_rol and fila["rol_nombre"] == "Cajero"
    r = admin.put(f"/usuarios/api/editar/{cajero.id_usuario}",
                  data={"nombre_completo": "Cajero Uno", "usuario": "cajero", "correo": "", "telefono": "",
                        "id_rol": fila["id_rol"], "password": ""})
    assert r.status_code == 200
    db.session.refresh(cajero)
    assert cajero.id_rol == datos_base["roles"]["Cajero"].id_rol
