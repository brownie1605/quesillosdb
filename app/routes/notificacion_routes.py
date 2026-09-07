"""Notificaciones del usuario (incluye avisos de venta anulada por conflicto)."""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.notificacion import Notificacion

notificacion_bp = Blueprint("notificacion", __name__, url_prefix="/api/notificaciones")


@notificacion_bp.route("/", methods=["GET"])
@login_required
def listar():
    solo_no_leidas = request.args.get("no_leidas") == "1"
    q = Notificacion.query.filter(
        (Notificacion.id_usuario == current_user.id_usuario)
        | (Notificacion.id_usuario.is_(None))
    )
    if solo_no_leidas:
        q = q.filter(Notificacion.leida.is_(False))
    items = q.order_by(Notificacion.fecha_creacion.desc()).limit(50).all()
    return jsonify(
        {
            "notificaciones": [n.to_dict() for n in items],
            "no_leidas": sum(1 for n in items if not n.leida),
        }
    )


@notificacion_bp.route("/<int:id_notificacion>/leer", methods=["POST"])
@login_required
def marcar_leida(id_notificacion):
    n = Notificacion.query.get_or_404(id_notificacion)
    if n.id_usuario and n.id_usuario != current_user.id_usuario:
        return jsonify({"success": False, "message": "Acceso denegado"}), 403
    n.leida = True
    db.session.commit()
    return jsonify({"success": True})


@notificacion_bp.route("/leer-todas", methods=["POST"])
@login_required
def marcar_todas():
    # Igual que en listar(): casi todas las notificaciones son "para todos"
    # (id_usuario=None), asi que hay que marcar tanto las propias como las
    # de broadcast -- si no, el boton no limpia nada en la practica.
    Notificacion.query.filter(
        (Notificacion.id_usuario == current_user.id_usuario)
        | (Notificacion.id_usuario.is_(None)),
        Notificacion.leida.is_(False),
    ).update({"leida": True}, synchronize_session=False)
    db.session.commit()
    return jsonify({"success": True})
