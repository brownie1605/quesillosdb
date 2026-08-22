"""Resolucion de conflictos: gana la venta con el timestamp menor."""
from datetime import timedelta

from app.extensions import db as _db
from app.models.sync import ConflictLog, SyncQueue
from app.models.notificacion import Notificacion
from app.services.conflict_service import ConflictService, MENSAJE_AGOTADO
from app.services.inventario_service import InventarioService
from app.services.venta_service import VentaService
from app.utils.date_utils import nicaragua_now


def _venta_de_prueba(datos_base, quesillo):
    return VentaService.registrar_venta(
        datos_base["cajero"],
        [{"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 60.0}],
    )


def _conflicto(venta, ts_local, ts_remoto, usuario_remoto=None):
    c = ConflictLog(
        tabla_afectada="ventas",
        registro_id=venta.id_venta,
        id_empresa=1,
        datos_local={"id_venta": venta.id_venta, "numero_venta": venta.numero_venta},
        timestamp_local=ts_local,
        usuario_local=venta.id_usuario,
        datos_remoto={},          # sin id remoto: no intenta tocar la nube
        timestamp_remoto=ts_remoto,
        usuario_remoto=usuario_remoto,
        tipo_conflicto="venta_simultanea",
        estado_resolucion="pendiente_resolucion",
    )
    _db.session.add(c)
    _db.session.commit()
    return c


def test_gana_la_venta_local_si_ocurrio_primero(app, db, datos_base, quesillo):
    venta = _venta_de_prueba(datos_base, quesillo)
    ahora = nicaragua_now()
    c = _conflicto(venta, ahora, ahora + timedelta(seconds=5))

    resultado = ConflictService.resolve_concurrent_sale(c.id_conflicto)

    assert resultado["ganador"] == "local"
    assert c.estado_resolucion == "resuelto_auto"
    assert c.resolucion_tipo == "prioridad_local"
    assert venta.estado == "completada"
    # La venta local se reencola para forzar su subida
    en_cola = SyncQueue.query.filter_by(tabla_afectada="ventas", registro_id=venta.id_venta).first()
    assert en_cola.estado_sync == "pendiente"


def test_gana_la_nube_si_vendio_primero_y_se_anula_la_local(app, db, datos_base, quesillo):
    venta = _venta_de_prueba(datos_base, quesillo)
    ahora = nicaragua_now()
    c = _conflicto(venta, ahora, ahora - timedelta(seconds=5))

    resultado = ConflictService.resolve_concurrent_sale(c.id_conflicto)

    assert resultado["ganador"] == "remoto"
    assert venta.estado == "anulada"
    assert venta.motivo_anulacion == MENSAJE_AGOTADO


def test_el_usuario_perdedor_recibe_la_alerta(app, db, datos_base, quesillo):
    venta = _venta_de_prueba(datos_base, quesillo)
    ahora = nicaragua_now()
    c = _conflicto(venta, ahora, ahora - timedelta(seconds=10))

    ConflictService.resolve_concurrent_sale(c.id_conflicto)

    aviso = Notificacion.query.filter_by(id_usuario=venta.id_usuario, tipo="error").first()
    assert aviso is not None
    assert MENSAJE_AGOTADO in aviso.mensaje
    assert aviso.titulo == "Venta anulada"


def test_al_anular_se_devuelven_los_insumos(app, db, datos_base, quesillo):
    antes = InventarioService.stock_de(quesillo["tortilla"].id_producto)
    venta = _venta_de_prueba(datos_base, quesillo)
    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes - 2

    ahora = nicaragua_now()
    c = _conflicto(venta, ahora, ahora - timedelta(seconds=1))
    ConflictService.resolve_concurrent_sale(c.id_conflicto)

    assert InventarioService.stock_de(quesillo["tortilla"].id_producto) == antes


def test_sin_hora_remota_la_nube_manda(app, db, datos_base, quesillo):
    """Si no se puede comparar, la nube es la fuente de verdad del stock."""
    venta = _venta_de_prueba(datos_base, quesillo)
    c = _conflicto(venta, nicaragua_now(), None)

    resultado = ConflictService.resolve_concurrent_sale(c.id_conflicto)

    assert resultado["ganador"] == "remoto"
    assert venta.estado == "anulada"


def test_resolver_pendientes_procesa_todo(app, db, datos_base, quesillo):
    ahora = nicaragua_now()
    v1 = _venta_de_prueba(datos_base, quesillo)
    v2 = _venta_de_prueba(datos_base, quesillo)
    _conflicto(v1, ahora, ahora + timedelta(seconds=3))       # gana local
    _conflicto(v2, ahora, ahora - timedelta(seconds=3))       # gana nube

    resultado = ConflictService.resolver_pendientes()

    assert resultado["resueltos"] == 2
    assert resultado["gano_local"] == 1
    assert resultado["gano_remoto"] == 1
    assert ConflictLog.query.filter_by(estado_resolucion="pendiente_resolucion").count() == 0


def test_resolucion_manual_del_administrador(app, db, datos_base, quesillo):
    venta = _venta_de_prueba(datos_base, quesillo)
    ahora = nicaragua_now()
    c = _conflicto(venta, ahora, ahora + timedelta(seconds=5))

    ConflictService.resolver_manual(
        c.id_conflicto, "prioridad_remoto", datos_base["admin"].id_usuario, "Revisado en caja"
    )

    assert c.estado_resolucion == "resuelto_manual"
    assert c.resuelto_por == datos_base["admin"].id_usuario
    assert venta.estado == "anulada"


def test_un_conflicto_no_se_resuelve_dos_veces(app, db, datos_base, quesillo):
    venta = _venta_de_prueba(datos_base, quesillo)
    ahora = nicaragua_now()
    c = _conflicto(venta, ahora, ahora - timedelta(seconds=2))

    assert ConflictService.resolve_concurrent_sale(c.id_conflicto) is not None
    assert ConflictService.resolve_concurrent_sale(c.id_conflicto) is None
