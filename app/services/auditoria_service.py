from flask import request
from flask_login import current_user
from app.extensions import db
from app.models.auditoria import Auditoria
import json

def registrar_auditoria(accion, modulo, detalles=None):
    """
    Registra una acción en el log de auditoría.
    """
    try:
        if not current_user.is_authenticated:
            return
            
        action_map = {
            "NUEVA VENTA": "crear",
            "CREAR USUARIO": "crear",
            "EDITAR USUARIO": "update",
            "ELIMINAR USUARIO": "delete",
            "LOGIN": "login",
            "LOGOUT": "logout"
        }
        mapped_action = action_map.get(accion, "update")

        ip = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent') if request else None
        id_usr_str = str(current_user.id_usuario)
        id_ref = str(detalles)[:64] if detalles else None

        auditoria = Auditoria(
            id_user=id_usr_str,
            action=mapped_action,
            entity_affected=modulo[:100],
            id_reference=id_ref,
            ip=ip,
            device=user_agent[:120] if user_agent else None
        )
        db.session.add(auditoria)
        db.session.commit()
    except Exception as e:
        print(f"Error registrando auditoría: {e}")
        db.session.rollback()
