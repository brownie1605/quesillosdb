"""API de sincronizacion y estado de conectividad."""
from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user

from app.extensions import db
from app.models.sync import SyncQueue, ConflictLog
from app.services.network_service import NetworkService
from app.services.sync_service import SyncService
from app.services.conflict_service import ConflictService
from app.utils.decorators import require_roles, usuario_tiene_rol

sync_bp = Blueprint("sync", __name__)


# ------------------------------------------------------------------ salud
@sync_bp.route("/api/sync/health", methods=["GET"])
def health():
    """Endpoint publico de salud (no requiere login)."""
    from app.utils.date_utils import nicaragua_now

    return jsonify({"status": "ok", "timestamp": nicaragua_now().isoformat()})


# ------------------------------------------------------------------ estado
@sync_bp.route("/api/sync/status", methods=["GET"])
@login_required
def status():
    return jsonify(SyncService.estado_general())


@sync_bp.route("/api/sync/check", methods=["POST", "GET"])
@login_required
def check():
    online = NetworkService.check_connectivity()
    return jsonify({"online": online, "red": NetworkService.status()})


# ------------------------------------------------------------------ acciones
@sync_bp.route("/api/sync/now", methods=["POST"])
@login_required
def sync_now():
    """Sincronizacion manual ('Sincronizar ahora')."""
    resultado = SyncService.sync_full(disparador="manual:" + str(current_user.id_usuario))
    return jsonify(resultado)


@sync_bp.route("/api/sync/push", methods=["POST"])
@login_required
def push():
    NetworkService.check_connectivity()
    return jsonify(SyncService.push_pending_operations())


@sync_bp.route("/api/sync/pull", methods=["POST", "GET"])
@login_required
def pull():
    NetworkService.check_connectivity()
    tablas = request.args.getlist("tabla") or None
    return jsonify(SyncService.pull_remote_changes(tablas))


# ------------------------------------------------------------------ cola
@sync_bp.route("/api/sync/queue", methods=["GET"])
@login_required
def queue():
    estado = request.args.get("estado")
    q = SyncQueue.query
    if estado:
        q = q.filter_by(estado_sync=estado)
    items = q.order_by(SyncQueue.id_sync_queue.desc()).limit(200).all()
    return jsonify([i.to_dict() for i in items])


# ------------------------------------------------------------------ conflictos
@sync_bp.route("/api/conflicts", methods=["GET"])
@login_required
def conflicts():
    estado = request.args.get("estado", "pendiente_resolucion")
    q = ConflictLog.query
    if estado != "todos":
        q = q.filter_by(estado_resolucion=estado)
    items = q.order_by(ConflictLog.timestamp_deteccion.desc()).limit(100).all()
    return jsonify([c.to_dict() for c in items])


@sync_bp.route("/api/sync/conflict/resolve", methods=["POST"])
@login_required
def resolve_conflict():
    if not usuario_tiene_rol("Admin", "Administrador"):
        return jsonify({"success": False, "message": "Solo el administrador puede resolver conflictos"}), 403

    data = request.get_json(silent=True) or {}
    conflict_id = data.get("conflict_id")
    resolucion = data.get("resolution", "prioridad_remoto")
    if not conflict_id:
        return jsonify({"success": False, "message": "conflict_id requerido"}), 400
    try:
        res = ConflictService.resolver_manual(
            int(conflict_id), resolucion, current_user.id_usuario, data.get("notas")
        )
        return jsonify({"success": True, "conflicto": res})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@sync_bp.route("/api/sync/conflict/auto", methods=["POST"])
@login_required
def resolve_auto():
    return jsonify(ConflictService.resolver_pendientes())


# ------------------------------------------------------------------ panel
@sync_bp.route("/sincronizacion")
@login_required
def panel():
    guard = require_roles("Admin", "Administrador")
    if guard is not None:
        return guard
    return render_template("sync/panel.html")
