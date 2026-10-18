"""Cierre de caja: inicial + ventas en efectivo - gastos del turno = esperado."""
from decimal import Decimal

from app.models.compra import Compra
from app.services.caja_service import CajaService
from app.services.venta_service import VentaService
from app.utils.date_utils import nicaragua_now


def _gasto(db, datos_base, monto, estado="completada", tipo="varios"):
    db.session.add(Compra(
        id_empresa=1, id_sucursal=1, id_usuario=datos_base["admin"].id_usuario,
        numero_compra=Compra.generar_numero("GV"), subtotal=monto, total=monto,
        estado=estado, tipo_compra=tipo, descripcion_gasto="Gas", fecha_compra=nicaragua_now(),
    ))
    db.session.commit()


def test_gastos_del_turno_se_restan_del_efectivo(app, db, datos_base, quesillo):
    apertura = CajaService.apertura_actual()
    apertura.monto_inicial = Decimal("500")
    db.session.commit()
    cart = [{"id_producto": quesillo["final"].id_producto, "cantidad": 2, "precio": 0}]   # C$ 120
    VentaService.registrar_venta(datos_base["cajero"], cart, metodo_pago="Efectivo")
    VentaService.registrar_venta(datos_base["cajero"], cart, metodo_pago="Tarjeta BAC")
    _gasto(db, datos_base, 30)
    _gasto(db, datos_base, 45, tipo="productos")
    _gasto(db, datos_base, 999, estado="cancelada")       # cancelada: no cuenta

    r = CajaService.resumen_turno(apertura)
    assert r["efectivo_en_ventas"] == Decimal("120")
    assert r["ventas_otros_metodos"] == Decimal("120")
    assert r["total_gastos"] == Decimal("75")
    assert len(r["gastos"]) == 2
    assert r["monto_esperado"] == Decimal("545")          # 500 + 120 - 75


def test_el_cierre_guarda_los_gastos_como_egresos(app, db, datos_base, quesillo):
    _gasto(db, datos_base, 40)
    cierre = CajaService.cerrar_turno(datos_base["cajero"], 0)
    assert cierre.total_egresos == Decimal("40")
    assert cierre.monto_esperado == Decimal("-40")
