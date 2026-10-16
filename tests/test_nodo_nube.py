"""La instalacion en modo "nube" (Railway) no intenta sincronizarse consigo
misma, y cada instalacion reporta su modo.

La sincronizacion real entre dos bases esta en
tests/sync/nodo_local_nube_real_mysql.py (necesita MySQL).
"""
from app.services.sync_service import SyncService


def test_la_nube_no_se_sincroniza_consigo_misma(app, datos_base):
    app.config["MODO_NODO"] = "nube"
    try:
        estado = SyncService.estado_general()
        assert estado["modo"] == "nube"
        assert estado["online"] is True
        assert estado["pendientes"] == 0
        assert SyncService.sync_full()["modo"] == "nube"
        assert SyncService.push_pending_operations()["enviados"] == 0
        assert SyncService.pull_remote_changes()["aplicados"] == 0
    finally:
        app.config["MODO_NODO"] = "local"


def test_el_restaurante_reporta_su_modo(app, datos_base):
    estado = SyncService.estado_general()
    assert estado["modo"] == "local"
