from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.utils.decorators import require_roles
from app.models.auditoria import Auditoria
from app.extensions import db
from datetime import datetime

auditoria_bp = Blueprint("auditoria", __name__)

@auditoria_bp.before_request
def check_roles():
    return require_roles("Administrador")

@auditoria_bp.route("/auditoria")
@login_required
def index():
    return render_template("auditoria/index.html")

@auditoria_bp.route("/api/auditoria")
@login_required
def api_auditoria():
    from app.models.usuario import Usuario
    
    # Get all user IDs for the current company
    usuarios_empresa = Usuario.query.filter_by(id_empresa=current_user.id_empresa).all()
    user_ids = [str(u.id_usuario) for u in usuarios_empresa]
    
    if not user_ids:
        return jsonify([])
        
    # Fetch audits only for those users
    query = Auditoria.query.filter(Auditoria.id_user.in_(user_ids))
    
    # Ordenar por fecha descendente
    query = query.order_by(Auditoria.date.desc())
    
    # Limitar a los últimos 500 registros para no sobrecargar
    auditorias = query.limit(500).all()
    
    return jsonify([a.to_dict() for a in auditorias])
