"""Prueba de punta a punta: restaurante (nodo local) <-> nube, con MySQL real.

Crea DOS bases de prueba en el MySQL de ESTA maquina:

    qpos_prueba_nube  -> hace de la nube (Railway), en modo "nube"
    qpos_prueba_rest  -> hace de la PC del restaurante, en modo "local"

y sincroniza de verdad entre ellas: ventas sin internet, ventas a la vez en
los dos lados, recetas editadas en la web, anulaciones, borrados, usuarios,
compras, conflictos de "ultima unidad" y una resincronizacion completa. Al
final las dos bases deben quedar iguales (mismas filas y mismo stock).

No toca la nube real ni la base local del sistema: solo esas dos bases de
prueba, que borra al terminar (pasa --conservar para dejarlas y revisarlas).

No se llama test_*.py a proposito: usa SQL de MySQL y `pytest tests/` (que
corre sobre SQLite en memoria) no debe recolectarla. Correr a mano:

    python tests/sync/nodo_local_nube_real_mysql.py
"""
import logging
import os
import sys
import time
from contextlib import contextmanager
from decimal import Decimal

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))
os.environ["SYNC_ENABLED"] = "false"
logging.disable(logging.WARNING)

import pymysql  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import create_app  # noqa: E402
from app.config.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services import sync_events  # noqa: E402
from app.services.network_service import NetworkService  # noqa: E402
from app.services.sync_service import SyncService, TABLAS_SYNC, PK_POR_TABLA  # noqa: E402

HOST = os.environ.get("DB_LOCAL_HOST", "localhost")
PUERTO = int(os.environ.get("DB_LOCAL_PORT", 3306))
USUARIO = os.environ.get("DB_LOCAL_USER", "root")
CLAVE = os.environ.get("DB_LOCAL_PASSWORD", "")
NUBE, REST = "qpos_prueba_nube", "qpos_prueba_rest"

if HOST not in ("localhost", "127.0.0.1"):
    sys.exit("Esta prueba solo corre contra el MySQL de esta maquina (DB_LOCAL_HOST=localhost).")


def _uri(nombre):
    return "mysql+pymysql://%s:%s@%s:%s/%s?charset=utf8mb4" % (USUARIO, CLAVE, HOST, PUERTO, nombre)


def _admin_mysql(sentencias):
    con = pymysql.connect(host=HOST, port=PUERTO, user=USUARIO, password=CLAVE)
    try:
        with con.cursor() as c:
            for s in sentencias:
                c.execute(s)
        con.commit()
    finally:
        con.close()


class _Base(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SYNC_ENABLED = False


class NubeCfg(_Base):
    MODO_NODO = "nube"
    DEVICE_ID = "nube"
    SQLALCHEMY_DATABASE_URI = _uri(NUBE)
    SQLALCHEMY_BINDS = {"cloud": _uri(NUBE)}


class RestCfg(_Base):
    MODO_NODO = "local"
    ID_NODO = 2
    DEVICE_ID = "restaurante-01"
    SQLALCHEMY_DATABASE_URI = _uri(REST)
    SQLALCHEMY_BINDS = {"cloud": _uri(NUBE)}


FALLAS = []


def check(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLA ") + mensaje)
    if not condicion:
        FALLAS.append(mensaje)


# ---------------------------------------------------------------------------
_admin_mysql([
    "DROP DATABASE IF EXISTS " + NUBE,
    "DROP DATABASE IF EXISTS " + REST,
    "CREATE DATABASE " + NUBE + " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
    "CREATE DATABASE " + REST + " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
])
app_nube = create_app(NubeCfg, iniciar_jobs=False)
app_rest = create_app(RestCfg, iniciar_jobs=False)


@contextmanager
def en(app):
    """Trabajar "dentro" de un nodo. sync_events guarda el dispositivo de
    origen por proceso (en produccion hay una sola app por proceso), asi que
    se reconfigura al cambiar de nodo."""
    sync_events.configurar(app)
    with app.app_context():
        try:
            yield
        finally:
            db.session.remove()


def sin_internet():
    """El restaurante pierde internet: nada se sube al momento."""
    NetworkService._is_online = False


def sincronizar(etiqueta, exigir_sin_errores=True):
    with en(app_rest):
        r = SyncService.sync_full(disparador="prueba")
    push, pull = r.get("push", {}), r.get("pull", {})
    resumen = "subidos=%s bajados=%s borrados=%s conflictos=%s" % (
        push.get("enviados"), pull.get("aplicados"), pull.get("borrados"), push.get("conflictos"))
    if exigir_sin_errores:
        errores = (push.get("detalle") or []) + (pull.get("errores") or [])
        check(r.get("ok") and not errores, "%s: sincroniza sin errores (%s) %s"
              % (etiqueta, resumen, errores[:2] if errores else ""))
    return r


def stocks(app):
    with en(app):
        return {
            pid: Decimal(str(s)) for pid, s in db.session.execute(
                text("SELECT id_producto, stock_actual FROM inventario")
            )
        }


def ids(app, tabla):
    with en(app):
        pk = PK_POR_TABLA[tabla]
        return set(db.session.execute(text("SELECT " + pk + " FROM " + tabla)).scalars().all())


def valor(app, sql, **params):
    with en(app):
        return db.session.execute(text(sql), params).scalar()


def comparar_todo(etiqueta):
    """Las dos bases deben tener las mismas filas y el mismo stock."""
    distintas = []
    for tabla in TABLAS_SYNC:
        a, b = ids(app_nube, tabla), ids(app_rest, tabla)
        if a != b:
            distintas.append("%s (solo nube: %s, solo restaurante: %s)"
                             % (tabla, sorted(a - b)[:5], sorted(b - a)[:5]))
    check(not distintas, "%s: mismas filas en las %s tablas %s"
          % (etiqueta, len(TABLAS_SYNC), distintas[:3] if distintas else ""))
    sn, sr = stocks(app_nube), stocks(app_rest)
    dif = {p: (sn.get(p), sr.get(p)) for p in set(sn) | set(sr) if sn.get(p) != sr.get(p)}
    check(not dif, "%s: mismo stock en los dos lados %s" % (etiqueta, dif if dif else ""))


def usuario(nombre):
    from app.models import Usuario

    return Usuario.query.filter_by(usuario=nombre).first()


def vender(nombre_usuario, id_producto, cantidad=1, opcion=None):
    from app.services.venta_service import VentaService

    item = {"id_producto": id_producto, "cantidad": cantidad, "precio": 0}
    if opcion:
        item["opciones"] = [opcion]
    return VentaService.registrar_venta(usuario(nombre_usuario), [item]).id_venta


def item_opcion(id_insumo):
    from app.models.receta import RecetaOpcionItem

    return RecetaOpcionItem.query.filter_by(id_producto_insumo=id_insumo).first().id_item


# ===========================================================================
try:
    print("\n== Preparando la nube de prueba")
    P = {}
    with en(app_nube):
        from app.models import (Empresa, Sucursal, Rol, UnidadMedida, Usuario,
                                Producto, Mesa, Cliente)
        from app.services.auth_service import generar_password
        from app.services.caja_service import CajaService
        from app.services.inventario_service import InventarioService
        from app.services.receta_service import RecetaService
        from app.utils.date_utils import nicaragua_now

        db.create_all()
        db.session.add(Empresa(id_empresa=1, nombre="Quesillos Lo Nuestro", estado="activo"))
        db.session.add(Sucursal(id_sucursal=1, id_empresa=1, nombre="Principal", estado="activo"))
        db.session.flush()
        rol = Rol(id_empresa=1, nombre="Admin", estado="activo")
        und = UnidadMedida(nombre="Unidad", abreviatura="und", estado="activo")
        db.session.add_all([rol, und])
        db.session.flush()
        ID_UNIDAD = und.id_unidad
        for nombre in ("admin", "web", "rest"):
            db.session.add(Usuario(
                id_empresa=1, id_sucursal=1, id_rol=rol.id_rol, usuario=nombre,
                nombre_completo=nombre.title(), correo=nombre + "@q.test",
                password_hash=generar_password("1234"), estado="activo",
                fecha_creacion=nicaragua_now(),
            ))
        db.session.commit()
        admin = usuario("admin")

        def producto(nombre, tipo, precio=0, stock=None):
            p = Producto(id_empresa=1, nombre=nombre, tipo_producto=tipo, precio_compra=10,
                         precio_venta=precio, id_unidad=ID_UNIDAD, estado="activo",
                         es_ingrediente_receta=(tipo == "insumo"))
            db.session.add(p)
            db.session.flush()
            InventarioService.obtener_o_crear(p.id_producto)
            if stock:
                InventarioService.mover(p.id_producto, stock, "compra", usuario("admin").id_usuario,
                                        observacion="Stock inicial")
            db.session.commit()
            P[nombre] = p.id_producto
            return p.id_producto

        for nombre, stock in (("Toalla", 50), ("Trenza", 50), ("Huevo", 50), ("Chorizo", 20),
                              ("Jamon", 20), ("Fajitas res", 10), ("Fajitas pollo", 10)):
            producto(nombre, "insumo", stock=stock)
        producto("Superquesillo", "final", 120)
        producto("Fajitas bowl", "final", 300)
        producto("Desayuno tipico", "final", 180)
        producto("Gaseosa", "final", 40, stock=1)
        producto("Agua", "final", 30, stock=1)

        def opcion(nombre, insumo):
            return {"nombre": nombre, "id_producto_insumo": P[insumo], "cantidad": 1}

        RecetaService.crear_receta(
            P["Superquesillo"], {"modo_preparacion": "1 toalla, 1 trenza"},
            [{"id_producto": P["Toalla"], "cantidad_necesaria": 1},
             {"id_producto": P["Trenza"], "cantidad_necesaria": 1}], admin.id_usuario)
        RecetaService.crear_receta(
            P["Fajitas bowl"], {"modo_preparacion": "1 fajitas de pollo o de res"}, [],
            admin.id_usuario, grupos_opciones=[{"nombre": "Fajitas", "obligatorio": True, "items": [
                opcion("Pollo", "Fajitas pollo"), opcion("Res", "Fajitas res")]}])
        RecetaService.crear_receta(
            P["Desayuno tipico"], {"modo_preparacion": "2 huevos + opcion"},
            [{"id_producto": P["Huevo"], "cantidad_necesaria": 2}], admin.id_usuario,
            grupos_opciones=[{"nombre": "Opcion", "obligatorio": True, "items": [
                opcion("Chorizo", "Chorizo"), opcion("Jamon", "Jamon")]}])
        db.session.add_all([Mesa(nombre="Mesa 1"), Mesa(nombre="Mesa 2")])
        db.session.commit()
        CajaService.abrir_turno(usuario("web"), 0)

        estado = SyncService.estado_general()
        check(estado["modo"] == "nube" and estado["online"] and estado["pendientes"] == 0,
              "la nube se reporta 'En la nube' sin pendientes (%s)" % estado["modo"])
        check(SyncService.sync_full().get("modo") == "nube", "la nube no intenta sincronizarse consigo misma")

    print("\n== Instalando el restaurante desde la nube (bootstrap)")
    with en(app_rest):
        from app.services.bootstrap_service import copiar_desde_nube

        db.create_all()
        NetworkService.check_connectivity()
        SyncService.fijar_cursor(copiar_desde_nube()["cursor"])
    comparar_todo("Bootstrap")

    print("\n== Venta en la web MIENTRAS el restaurante copia la nube (foto consistente)")
    # La instalacion y la resincronizacion se hacen con la web en uso. Si cada
    # tabla se leyera en su propia conexion, una venta que caiga entre la
    # lectura de `inventario` y la de `movimientos_inventario` dejaria el
    # movimiento copiado pero el stock sin descontar (y el pull lo daria por
    # ya aplicado): stock de mas, para siempre.
    from app.services import bootstrap_service

    _columnas_original = bootstrap_service._columnas_locales
    _en_medio = {"hecho": False}

    def _venta_en_medio(tabla):
        if tabla == "cajas" and not _en_medio["hecho"]:   # justo despues de `inventario`
            _en_medio["hecho"] = True
            with en(app_nube):
                vender("web", P["Superquesillo"], 1)
        return _columnas_original(tabla)

    bootstrap_service._columnas_locales = _venta_en_medio
    try:
        with en(app_rest):
            SyncService.fijar_cursor(copiar_desde_nube()["cursor"])
    finally:
        bootstrap_service._columnas_locales = _columnas_original
    check(_en_medio["hecho"], "la venta de la web cayo en medio de la copia")
    sincronizar("Primer ciclo despues de copiar con una venta en medio")
    comparar_todo("Copia con una venta en medio")

    print("\n== Numeracion de IDs por nodo")
    with en(app_nube):
        c = Cliente(nombre="Cliente web")
        db.session.add(c)
        db.session.commit()
        id_web = c.id_cliente
    with en(app_rest):
        c = Cliente(nombre="Cliente restaurante")
        db.session.add(c)
        db.session.commit()
        id_rest = c.id_cliente
    check(id_web % 10 == 1 and id_rest % 10 == 2,
          "la nube numera ...1 y el restaurante ...2 (%s, %s)" % (id_web, id_rest))
    sincronizar("Clientes creados en los dos lados")
    comparar_todo("Clientes")

    print("\n== Venta en el restaurante SIN internet")
    sin_internet()
    with en(app_rest):
        v_offline = vender("rest", P["Superquesillo"], 2)
    toalla_n = stocks(app_nube)[P["Toalla"]]
    check(stocks(app_rest)[P["Toalla"]] == toalla_n - 2,
          "sin internet: el restaurante descuenta (Toalla %s) y la nube no se entera (%s)"
          % (stocks(app_rest)[P["Toalla"]], toalla_n))
    with en(app_rest):
        check(SyncService.contar_pendientes() > 0, "sin internet: la venta queda en cola")
    sincronizar("Vuelve el internet")
    check(valor(app_nube, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_offline) == "completada",
          "la venta del restaurante llega a la nube")
    comparar_todo("Venta offline")

    print("\n== Ventas a la vez en la web y en el restaurante")
    sin_internet()
    with en(app_nube):
        v_web = vender("web", P["Superquesillo"], 1)
    with en(app_rest):
        v_rest = vender("rest", P["Superquesillo"], 3)
    sincronizar("Ventas simultaneas")
    check(valor(app_rest, "SELECT COUNT(*) FROM detalle_ventas WHERE id_venta = :v", v=v_web) == 1,
          "la venta de la web baja al restaurante con su detalle")
    comparar_todo("Ventas simultaneas")

    print("\n== Receta de solo opciones (Fajitas bowl de res) y anulacion")
    sin_internet()
    res_antes = stocks(app_rest)[P["Fajitas res"]]
    with en(app_rest):
        v_faj = vender("rest", P["Fajitas bowl"], 1, opcion=item_opcion(P["Fajitas res"]))
    check(stocks(app_rest)[P["Fajitas res"]] == res_antes - 1, "vender Fajitas bowl de res descuenta 1 fajitas de res")
    with en(app_rest):
        from app.services.venta_service import VentaService

        VentaService.anular_venta(v_faj, usuario("rest"), "Prueba")
    check(stocks(app_rest)[P["Fajitas res"]] == res_antes,
          "anularla devuelve la fajitas de res (antes no devolvia nada)")
    with en(app_rest):
        v_des = vender("rest", P["Desayuno tipico"], 1, opcion=item_opcion(P["Jamon"]))
        VentaService.anular_venta(v_des, usuario("rest"), "Prueba")
    check(stocks(app_rest)[P["Jamon"]] == stocks(app_nube)[P["Jamon"]],
          "anular un Desayuno tipico devuelve tambien el jamon elegido")
    sincronizar("Anulaciones")
    check(valor(app_nube, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_faj) == "anulada",
          "la anulacion llega a la nube")
    comparar_todo("Anulaciones")

    print("\n== Anular en la web una venta hecha en el restaurante")
    with en(app_nube):
        VentaService.anular_venta(v_offline, usuario("web"), "Anulada desde la web")
    sincronizar("Anulacion en la web")
    check(valor(app_rest, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_offline) == "anulada",
          "el restaurante ve la venta anulada desde la web")
    comparar_todo("Anulacion en la web")

    print("\n== Receta editada en la web")
    with en(app_nube):
        RecetaService.guardar_desde_producto(
            P["Superquesillo"], "Ahora 2 toallas, sin trenza",
            [{"id_producto": P["Toalla"], "cantidad_necesaria": 2}], True, usuario("admin").id_usuario)
    sincronizar("Receta editada")
    with en(app_rest):
        from app.models.receta import Receta

        r = Receta.query.filter_by(id_producto=P["Superquesillo"]).first()
        ingredientes = sorted((i.id_producto, float(i.cantidad_necesaria)) for i in r.ingredientes)
    check(ingredientes == [(P["Toalla"], 2.0)],
          "el restaurante tiene la receta nueva y ya no la vieja (%s)" % ingredientes)
    comparar_todo("Receta editada")

    print("\n== Usuario desactivado y cambio de PIN en la web")
    with en(app_nube):
        u = usuario("rest")
        u.password_hash = generar_password("9999")
        db.session.commit()
        u2 = usuario("web")
        u2.estado = "inactivo"
        db.session.commit()
    sincronizar("Usuarios")
    with en(app_rest):
        from app.services.auth_service import verificar_password

        check(verificar_password(usuario("rest").password_hash, "9999"), "el PIN nuevo funciona en el restaurante")
        check(usuario("web").estado == "inactivo", "el usuario desactivado en la web tambien queda inactivo aqui")
    with en(app_nube):
        usuario("web").estado = "activo"
        db.session.commit()
    sincronizar("Usuario reactivado")

    print("\n== La web y el restaurante tocan la MISMA fila (columnas distintas)")
    sin_internet()
    with en(app_nube):
        u = usuario("rest")
        u.password_hash = generar_password("5555")
        u.estado = "inactivo"
        Mesa.query.filter_by(nombre="Mesa 1").first().nombre = "Terraza 1"
        db.session.commit()
    with en(app_rest):
        # Alguien inicia sesion en el restaurante: se toca el ultimo acceso.
        usuario("rest").ultimo_acceso = nicaragua_now()
        Mesa.query.filter_by(nombre="Mesa 1").first().estado = "ocupada"
        db.session.commit()
    sincronizar("Misma fila en los dos lados")
    with en(app_nube):
        u = usuario("rest")
        check(verificar_password(u.password_hash, "5555") and u.estado == "inactivo",
              "el PIN nuevo y la desactivacion hechos en la web NO se revierten desde el restaurante")
        check(u.ultimo_acceso is not None, "el ultimo acceso del restaurante tambien llega a la nube")
        m = Mesa.query.filter_by(nombre="Terraza 1").first()
        check(m is not None and m.estado == "ocupada",
              "la mesa queda con el nombre de la web y ocupada por el restaurante")
    with en(app_rest):
        u = usuario("rest")
        check(verificar_password(u.password_hash, "5555") and u.estado == "inactivo",
              "el restaurante recibe el PIN nuevo y la desactivacion")
        m = Mesa.query.filter_by(nombre="Terraza 1").first()
        check(m is not None and m.estado == "ocupada", "el restaurante ve la mesa renombrada y ocupada")
    with en(app_nube):
        u = usuario("rest")
        u.password_hash = generar_password("9999")
        u.estado = "activo"
        db.session.commit()
    sincronizar("Usuario restaurado")
    comparar_todo("Misma fila")

    print("\n== Compra en la web mientras el restaurante vende")
    sin_internet()
    with en(app_nube):
        InventarioService.registrar_compra(P["Toalla"], 10, 12, usuario("admin").id_usuario, commit=True)
    with en(app_rest):
        vender("rest", P["Superquesillo"], 1)
    sincronizar("Compra + venta")
    comparar_todo("Compra + venta (nada se pisa)")

    print("\n== Borrado en la web")
    with en(app_nube):
        db.session.delete(Mesa.query.filter_by(nombre="Mesa 2").first())
        db.session.commit()
    sincronizar("Borrado")
    check(valor(app_rest, "SELECT COUNT(*) FROM mesas WHERE nombre = 'Mesa 2'") == 0,
          "la mesa borrada en la web desaparece del restaurante")
    comparar_todo("Borrado")

    print("\n== Ultima unidad: la web vendio primero")
    sin_internet()
    with en(app_nube):
        v_g_web = vender("web", P["Gaseosa"], 1)
    time.sleep(1.1)  # la hora se guarda sin milisegundos: en empate gana la nube
    with en(app_rest):
        v_g_rest = vender("rest", P["Gaseosa"], 1)
    sincronizar("Conflicto (1)", exigir_sin_errores=False)
    sincronizar("Conflicto (2)", exigir_sin_errores=False)
    sincronizar("Conflicto (3)")
    check(valor(app_nube, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_g_web) == "completada"
          and valor(app_rest, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_g_rest) == "anulada"
          and valor(app_nube, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_g_rest) == "anulada",
          "gana la web; la del restaurante queda anulada en los dos lados")
    check(stocks(app_nube)[P["Gaseosa"]] == 0, "la Gaseosa queda en 0 (no negativa)")
    comparar_todo("Conflicto, gana la web")

    print("\n== Ultima unidad: el restaurante vendio primero")
    sin_internet()
    with en(app_rest):
        v_a_rest = vender("rest", P["Agua"], 1)
    time.sleep(1.1)
    with en(app_nube):
        v_a_web = vender("web", P["Agua"], 1)
    sincronizar("Conflicto (1)", exigir_sin_errores=False)
    sincronizar("Conflicto (2)", exigir_sin_errores=False)
    sincronizar("Conflicto (3)")
    check(valor(app_nube, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_a_rest) == "completada"
          and valor(app_nube, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_a_web) == "anulada"
          and valor(app_rest, "SELECT estado FROM ventas WHERE id_venta = :v", v=v_a_web) == "anulada",
          "gana el restaurante; la de la web queda anulada en los dos lados")
    check(stocks(app_nube)[P["Agua"]] == 0, "el Agua queda en 0 (no negativa)")
    comparar_todo("Conflicto, gana el restaurante")

    print("\n== Restaurante desconectado mas tiempo del que la nube guarda cambios")
    with en(app_nube):
        app_nube.config["RETENCION_COLA_DIAS"] = 0
        producto("Producto nuevo en la web", "final", 50)
        borradas = SyncService.podar_registro()
        app_nube.config["RETENCION_COLA_DIAS"] = 90
    check(borradas > 0, "la nube borra su registro viejo (%s filas)" % borradas)
    r = sincronizar("Resincronizacion automatica")
    check(bool(r.get("pull", {}).get("resync")), "el restaurante detecta el hueco y se resincroniza solo")
    check(P["Producto nuevo en la web"] in ids(app_rest, "productos"),
          "el producto creado en la web llega igual")
    comparar_todo("Resincronizacion")

    print("\n== Errores pendientes en la cola del restaurante")
    with en(app_rest):
        from app.models.sync import SyncQueue

        atascados = SyncQueue.query.filter(SyncQueue.estado_sync.in_(["pendiente", "error", "en_conflicto"])).count()
    check(atascados == 0, "no queda nada atascado en la cola del restaurante (%s)" % atascados)

finally:
    for app in (app_nube, app_rest):
        with app.app_context():
            db.session.remove()
            for engine in db.engines.values():
                engine.dispose()
    if "--conservar" in sys.argv:
        print("\nBases conservadas: %s y %s" % (NUBE, REST))
    else:
        _admin_mysql(["DROP DATABASE IF EXISTS " + NUBE, "DROP DATABASE IF EXISTS " + REST])

print("\n" + ("TODO OK" if not FALLAS else "%s FALLA(S):\n  - %s" % (len(FALLAS), "\n  - ".join(FALLAS))))
sys.exit(1 if FALLAS else 0)
