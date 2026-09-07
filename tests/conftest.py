"""Fixtures de prueba: base SQLite en memoria, sin tocar MySQL ni la nube."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.config.config import Config  # noqa: E402


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_BINDS = {}
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SYNC_ENABLED = False
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SECRET_KEY = "test"


@pytest.fixture()
def app():
    aplicacion = create_app(TestConfig, iniciar_jobs=False)
    with aplicacion.app_context():
        _db.create_all()
        yield aplicacion
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def datos_base(app, db):
    """Empresa, sucursal, roles, unidades y un usuario admin."""
    from app.models import Empresa, Sucursal, Rol, UnidadMedida, Usuario
    from app.services.auth_service import generar_password
    from app.utils.date_utils import nicaragua_now

    db.session.add(Empresa(id_empresa=1, nombre="Quesillos Lo Nuestro", estado="activo"))
    db.session.add(Sucursal(id_sucursal=1, id_empresa=1, nombre="Principal", estado="activo"))
    db.session.flush()

    roles = {}
    for nombre in ("Admin", "Cajero", "Mesero", "Cocinero"):
        r = Rol(id_empresa=1, nombre=nombre, estado="activo")
        db.session.add(r)
        db.session.flush()
        roles[nombre] = r

    unidades = {}
    for nombre, abrev in (("Unidad", "und"), ("Litro", "L"), ("Onza", "oz")):
        u = UnidadMedida(nombre=nombre, abreviatura=abrev, estado="activo")
        db.session.add(u)
        db.session.flush()
        unidades[abrev] = u

    admin = Usuario(
        id_empresa=1, id_sucursal=1, id_rol=roles["Admin"].id_rol,
        usuario="admin", nombre_completo="Administrador",
        correo="admin@quesillos.test", password_hash=generar_password("admin123"),
        estado="activo", fecha_creacion=nicaragua_now(),
    )
    cajero = Usuario(
        id_empresa=1, id_sucursal=1, id_rol=roles["Cajero"].id_rol,
        usuario="cajero", nombre_completo="Cajero Uno",
        correo="cajero@quesillos.test", password_hash=generar_password("cajero123"),
        estado="activo", fecha_creacion=nicaragua_now(),
    )
    db.session.add_all([admin, cajero])
    db.session.commit()

    # Desde que una venta exige turno de caja abierto, se abre uno por
    # defecto aqui: la gran mayoria de pruebas de venta no estan probando
    # esta regla en si, solo necesitan poder cobrar.
    from app.services.caja_service import CajaService

    apertura = CajaService.abrir_turno(cajero, 0)

    return {
        "roles": roles, "unidades": unidades, "admin": admin, "cajero": cajero,
        "apertura_caja": apertura,
    }


@pytest.fixture()
def quesillo(app, db, datos_base):
    """Crea el ejemplo del negocio: Quesillo con 4 insumos."""
    from app.models import Producto, Inventario
    from app.services.receta_service import RecetaService

    u = datos_base["unidades"]

    def crear(nombre, tipo, compra, venta, unidad, stock):
        p = Producto(
            id_empresa=1, nombre=nombre, tipo_producto=tipo,
            precio_compra=compra, precio_venta=venta,
            id_unidad=unidad.id_unidad, estado="activo",
            es_ingrediente_receta=(tipo == "insumo"),
        )
        db.session.add(p)
        db.session.flush()
        db.session.add(
            Inventario(id_producto=p.id_producto, id_sucursal=1,
                       stock_actual=stock, stock_minimo=0, stock_maximo=stock * 2)
        )
        db.session.flush()
        return p

    tortilla = crear("Tortilla", "insumo", 1.5, 3.0, u["und"], 100)
    crema = crear("Crema", "insumo", 60.0, 90.0, u["L"], 10)
    cebolla = crear("Cebolla", "insumo", 2.0, 5.0, u["oz"], 120)
    queso = crear("Quesillo insumo", "insumo", 25.0, 40.0, u["und"], 20)
    final = crear("Quesillo Lo Nuestro", "final", 0, 60.0, u["und"], 0)
    db.session.commit()

    receta = RecetaService.crear_receta(
        final.id_producto,
        {"nombre": "Quesillo Lo Nuestro", "rendimiento": 1},
        [
            {"id_producto": tortilla.id_producto, "cantidad_necesaria": 2, "id_unidad": u["und"].id_unidad},
            {"id_producto": crema.id_producto, "cantidad_necesaria": 0.25, "id_unidad": u["L"].id_unidad},
            {"id_producto": cebolla.id_producto, "cantidad_necesaria": 6, "id_unidad": u["oz"].id_unidad},
            {"id_producto": queso.id_producto, "cantidad_necesaria": 1, "id_unidad": u["und"].id_unidad},
        ],
        datos_base["admin"].id_usuario,
    )

    return {
        "final": final, "receta": receta, "tortilla": tortilla,
        "crema": crema, "cebolla": cebolla, "queso": queso,
    }
