"""Cola de sincronizacion y comportamiento offline."""
from app.models.sync import SyncQueue, SyncMetadata
from app.services.sync_service import SyncService, TABLAS_SYNC, PK_POR_TABLA
from app.services.network_service import NetworkService
from app.services.venta_service import VentaService


def test_una_venta_offline_encola_todas_sus_operaciones(app, db, datos_base, quesillo):
    SyncQueue.query.delete()
    db.session.commit()

    venta = VentaService.registrar_venta(
        datos_base["cajero"],
        [{"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 60.0}],
    )

    tablas = {q.tabla_afectada for q in SyncQueue.query.all()}
    assert "ventas" in tablas
    assert "detalle_ventas" in tablas
    assert "movimientos_inventario" in tablas
    assert "inventario" in tablas

    en_cola = SyncQueue.query.filter_by(tabla_afectada="ventas", registro_id=venta.id_venta).first()
    assert en_cola is not None
    assert en_cola.estado_sync == "pendiente"
    assert en_cola.payload["total"] == float(venta.total)
    assert en_cola.checksum_datos


def test_offline_no_bloquea_la_venta(app, db, datos_base, quesillo):
    """Sin conexion la venta se registra igual y queda pendiente."""
    assert NetworkService.is_online() is False  # el bind cloud no existe en tests

    venta = VentaService.registrar_venta(
        datos_base["cajero"],
        [{"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 60.0}],
    )
    assert venta.id_venta is not None
    assert venta.estado == "completada"
    assert venta.estado_sync == "pendiente"
    assert venta.uuid_venta


def test_diez_ventas_offline_quedan_todas_en_cola(app, db, datos_base, quesillo):
    SyncQueue.query.delete()
    db.session.commit()

    for _ in range(10):
        VentaService.registrar_venta(
            datos_base["cajero"],
            [{"id_producto": quesillo["final"].id_producto, "cantidad": 1, "precio": 60.0}],
        )

    ventas_en_cola = SyncQueue.query.filter_by(tabla_afectada="ventas").count()
    assert ventas_en_cola == 10
    assert SyncService.contar_pendientes() >= 10


def test_push_sin_conexion_no_falla(app, datos_base):
    resultado = SyncService.push_pending_operations()
    assert resultado["enviados"] == 0
    assert "mensaje" in resultado


def test_pull_sin_conexion_no_falla(app, datos_base):
    resultado = SyncService.pull_remote_changes()
    assert resultado["aplicados"] == 0
    assert "mensaje" in resultado


def test_sync_full_sin_conexion_reporta_offline(app, datos_base):
    resultado = SyncService.sync_full()
    assert resultado["ok"] is False
    assert resultado["online"] is False


def test_estado_general_expone_lo_necesario(app, datos_base):
    estado = SyncService.estado_general()
    for clave in ("online", "pendientes", "conflictos_pendientes", "red"):
        assert clave in estado


def test_toda_tabla_sincronizable_tiene_clave_primaria():
    for tabla in TABLAS_SYNC:
        assert tabla in PK_POR_TABLA, "Falta la PK de " + tabla


def test_metadata_se_crea_bajo_demanda(app, datos_base):
    meta = SyncService._get_metadata("productos")
    assert meta.tabla_nombre == "productos"
    assert SyncMetadata.query.filter_by(tabla_nombre="productos").count() == 1
    # No se duplica
    SyncService._get_metadata("productos")
    assert SyncMetadata.query.filter_by(tabla_nombre="productos").count() == 1
