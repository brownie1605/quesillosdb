"""Reglas de operacion de mesas y caja: caja abierta para atender, cerrar caja
solo con mesas cobradas, mesas vacias disponibles, meseros sin anular ni ver
Clientes, y avisos de una mesa que se borran al cerrarla."""
import pytest

from app.models import Mesa, Notificacion, Venta
from app.services.mesa_service import MesaService
from app.services.notificacion_service import NotificacionService
from app.services.venta_service import VentaService


@pytest.fixture()
def mesa(app, db):
    m = Mesa(nombre="Mesa 1", tipo="mesa", capacidad=4, orden=1)
    db.session.add(m)
    db.session.commit()
    return m


def _item(producto, cantidad=1):
    return {"id_producto": producto.id_producto, "cantidad": cantidad, "precio": float(producto.precio_venta)}


def _entrar(app, usuario, password):
    c = app.test_client()
    r = c.post("/login", data={"usuario": usuario, "password": password}, follow_redirects=False)
    assert r.status_code == 302
    return c


def _crear_usuario(app, datos_base, rol, usuario, pin="4821"):
    admin = _entrar(app, "admin", "admin123")
    r = admin.post("/usuarios/api/crear", data={
        "nombre_completo": "Persona Prueba", "usuario": usuario, "correo": "", "telefono": "",
        "id_rol": datos_base["roles"][rol].id_rol, "password": pin})
    assert r.status_code == 200, r.get_json()
    return _entrar(app, usuario, pin)


def _cerrar_caja_en_bd(db, datos_base):
    datos_base["apertura_caja"].estado = "cerrada"
    db.session.commit()


# ------------------------------------------------------------------ 1. caja abierta para atender
def test_con_caja_cerrada_no_se_puede_atender_una_mesa(app, db, datos_base, quesillo, mesa):
    _cerrar_caja_en_bd(db, datos_base)
    admin = _entrar(app, "admin", "admin123")

    r = admin.post(f"/mesas/api/{mesa.id_mesa}/agregar", json={"items": [_item(quesillo["final"])]})
    assert r.status_code == 400 and "caja" in r.get_json()["message"].lower()
    db.session.refresh(mesa)
    assert mesa.estado == "libre" and mesa.id_venta_actual is None

    r = admin.get(f"/mesas/{mesa.id_mesa}/pedido", follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/mesas/")

    html = admin.get("/mesas/").get_data(as_text=True)
    assert "La caja está cerrada" in html


def test_con_caja_abierta_si_se_atiende(app, db, datos_base, quesillo, mesa):
    admin = _entrar(app, "admin", "admin123")
    assert admin.get(f"/mesas/{mesa.id_mesa}/pedido").status_code == 200
    r = admin.post(f"/mesas/api/{mesa.id_mesa}/agregar", json={"items": [_item(quesillo["final"])]})
    assert r.status_code == 200 and r.get_json()["success"] is True
    assert "La caja está cerrada" not in admin.get("/mesas/").get_data(as_text=True)


def test_una_mesa_ya_abierta_se_sigue_viendo_aunque_cierren_la_caja(app, db, datos_base, quesillo, mesa):
    VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    _cerrar_caja_en_bd(db, datos_base)
    admin = _entrar(app, "admin", "admin123")
    assert admin.get(f"/mesas/{mesa.id_mesa}/pedido").status_code == 200


# ------------------------------------------------------------------ 2. cerrar caja
def test_no_se_cierra_la_caja_con_mesas_abiertas(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    admin = _entrar(app, "admin", "admin123")

    r = admin.post("/caja/api/cerrar", json={"monto_real": 0})
    assert r.status_code == 400
    assert "Mesa 1" in r.get_json()["message"]

    VentaService.cobrar_mesa(venta, datos_base["cajero"], monto_recibido=1000)
    r = admin.post("/caja/api/cerrar", json={"monto_real": 0})
    assert r.status_code == 200, r.get_json()


# ------------------------------------------------------------------ 3. mesas vacias disponibles
def test_al_quitar_el_ultimo_producto_la_mesa_queda_disponible(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    VentaService.quitar_item(venta, venta.detalles[0].id_detalle_venta, datos_base["cajero"])
    db.session.refresh(mesa)
    assert mesa.estado == "libre" and mesa.id_venta_actual is None
    assert venta.estado == "anulada"


def test_quitar_un_producto_de_varios_deja_la_mesa_ocupada(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(
        mesa, datos_base["cajero"], cart=[_item(quesillo["final"]), _item(quesillo["tortilla"])])
    VentaService.quitar_item(venta, venta.detalles[0].id_detalle_venta, datos_base["cajero"])
    db.session.refresh(mesa)
    assert mesa.estado == "ocupada" and venta.estado == "pendiente"


def test_la_lista_de_mesas_libera_las_que_estan_vacias(app, db, datos_base, mesa):
    VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[])      # ocupada pero sin nada adentro
    assert mesa.estado == "ocupada"
    admin = _entrar(app, "admin", "admin123")
    assert admin.get("/mesas/").status_code == 200
    db.session.refresh(mesa)
    assert mesa.estado == "libre" and mesa.id_venta_actual is None


def test_la_lista_de_mesas_no_toca_una_mesa_con_productos(app, db, datos_base, quesillo, mesa):
    VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    admin = _entrar(app, "admin", "admin123")
    admin.get("/mesas/")
    db.session.refresh(mesa)
    assert mesa.estado == "ocupada"


# ------------------------------------------------------------------ 4. meseros no anulan
def test_el_mesero_no_puede_anular_una_factura(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    VentaService.cobrar_mesa(venta, datos_base["cajero"], monto_recibido=1000)
    mesero = _crear_usuario(app, datos_base, "Mesero", "mesero_a")

    r = mesero.post(f"/ventas/api/{venta.id_venta}/anular", json={"motivo": "x"})
    assert r.status_code == 403
    db.session.refresh(venta)
    assert venta.estado == "completada"

    assert "const PUEDE_ANULAR = false" in mesero.get("/ventas/historial").get_data(as_text=True)
    admin = _entrar(app, "admin", "admin123")
    assert "const PUEDE_ANULAR = true" in admin.get("/ventas/historial").get_data(as_text=True)


# ------------------------------------------------------------------ 7. avisos de la mesa
def test_al_cerrar_la_mesa_se_borran_sus_avisos_y_quedan_los_de_stock(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    NotificacionService.avisar_nuevo_pedido(mesa.id_mesa, "Raquel")
    NotificacionService.crear("⏰ Pedido demorado", 'El pedido de "Mesa 1" lleva 30 min sin cerrarse.',
                              tipo="warning", url_accion=f"/mesas/{mesa.id_mesa}/pedido")
    NotificacionService.crear("Stock bajo", "Quedan 2 de Quesillo", tipo="warning", url_accion="/productos/")
    # un aviso de OTRA mesa no debe tocarse
    NotificacionService.avisar_nuevo_pedido(999, "Raquel")
    assert Notificacion.query.count() == 4

    VentaService.cobrar_mesa(venta, datos_base["cajero"], monto_recibido=1000)

    restantes = {n.url_accion for n in Notificacion.query.all()}
    assert restantes == {"/productos/", "/cocina/pendientes?mesa=999"}


def test_los_avisos_viejos_de_nuevo_pedido_tambien_se_borran_por_el_nombre_de_la_mesa(app, db, datos_base, quesillo, mesa):
    venta = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    NotificacionService.crear("🍳 Nuevo pedido para preparar", "Mesa 1: se agregaron productos a la cuenta.",
                              url_accion="/cocina/pendientes")
    NotificacionService.crear("🍳 Nuevo pedido para preparar", "Mesa 10: se agregaron productos a la cuenta.",
                              url_accion="/cocina/pendientes")
    VentaService.cobrar_mesa(venta, datos_base["cajero"], monto_recibido=1000)
    assert [n.mensaje for n in Notificacion.query.all()] == ["Mesa 10: se agregaron productos a la cuenta."]


def test_si_la_mesa_sigue_con_otra_cuenta_sus_avisos_se_quedan(app, db, datos_base, quesillo, mesa):
    v1 = VentaService.abrir_mesa(mesa, datos_base["cajero"], cart=[_item(quesillo["final"])])
    # segunda cuenta pendiente de la misma mesa (como cuando se separa)
    from app.models import DetalleVenta
    otra = Venta(id_empresa=1, id_sucursal=1, id_usuario=datos_base["cajero"].id_usuario, id_mesa=mesa.id_mesa,
                 numero_venta="X-1", uuid_venta="uuid-otra-cuenta", estado="pendiente", total=0, subtotal=0)
    db.session.add(otra)
    db.session.flush()
    db.session.add(DetalleVenta(id_venta=otra.id_venta, id_producto=quesillo["final"].id_producto,
                                cantidad=1, precio_unitario=quesillo["final"].precio_venta,
                                subtotal=quesillo["final"].precio_venta))
    db.session.commit()
    NotificacionService.avisar_nuevo_pedido(mesa.id_mesa, "Raquel")

    VentaService.cobrar_mesa(v1, datos_base["cajero"], monto_recibido=1000)
    db.session.refresh(mesa)
    assert mesa.estado == "ocupada"
    assert Notificacion.query.count() == 1


# ------------------------------------------------------------------ 8. clientes
def test_el_mesero_no_ve_clientes_pero_si_puede_elegir_uno_para_la_mesa(app, db, datos_base, mesa):
    mesero = _crear_usuario(app, datos_base, "Mesero", "mesero_b")

    r = mesero.get("/clientes/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/mesas/")
    assert mesero.get("/clientes/api/list").status_code in (302, 401, 403)

    html = mesero.get("/mesas/").get_data(as_text=True)
    assert "🙂 Clientes" not in html
    assert mesero.get("/ventas/api/clientes").status_code == 200   # la lista para asignarlo a la mesa


def test_caja_y_administracion_si_ven_clientes(app, db, datos_base):
    cajero = _crear_usuario(app, datos_base, "Cajero", "cajero_b")
    assert "🙂 Clientes" in cajero.get("/mesas/").get_data(as_text=True)
    assert cajero.get("/clientes/").status_code == 200
    admin = _entrar(app, "admin", "admin123")
    assert "🙂 Clientes" in admin.get("/mesas/").get_data(as_text=True)
    assert admin.get("/clientes/").status_code == 200
