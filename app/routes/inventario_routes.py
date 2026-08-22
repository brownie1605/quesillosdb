from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Inventario, Producto

from app.utils.decorators import require_roles

inventario_bp = Blueprint("inventario", __name__, url_prefix="/inventario")

@inventario_bp.before_request
def check_roles():
    return require_roles('Administrador', 'Cajero', 'Inventario')


@inventario_bp.route("/")
@login_required
def lista():
    return render_template("inventario/lista.html")

@inventario_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    productos = Producto.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    res = []
    for p in productos:
        inv = Inventario.query.filter_by(id_producto=p.id_producto).first()
        d = p.to_dict()
        d["stock_actual"] = float(inv.stock_actual) if inv else 0.0
        d["stock_minimo"] = float(inv.stock_minimo) if inv else 0.0
        d["id_inventario"] = inv.id_inventario if inv else None
        res.append(d)
    return jsonify(res)

@inventario_bp.route("/api/editar_stock/<int:id>", methods=["PUT"])
@login_required
def api_editar_stock(id):
    data = request.json
    try:
        inv = Inventario.query.filter_by(id_producto=id).first()
        if not inv:
            # Create if doesn't exist
            inv = Inventario(
                id_sucursal=current_user.id_sucursal,
                id_producto=id,
                stock_actual=0.0,
                stock_minimo=0.0
            )
            db.session.add(inv)
            
        inv.stock_actual = float(data.get("stock_actual", inv.stock_actual))
        inv.stock_minimo = float(data.get("stock_minimo", inv.stock_minimo))
        
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@inventario_bp.route("/api/notificaciones", methods=["GET"])
@login_required
def api_notificaciones():
    productos = Producto.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    alertas = []
    
    for p in productos:
        inv = Inventario.query.filter_by(id_producto=p.id_producto).first()
        if inv:
            stock = float(inv.stock_actual)
            minimo = float(inv.stock_minimo)
            if stock <= minimo:
                alertas.append({
                    "id_producto": p.id_producto,
                    "nombre": p.nombre,
                    "mensaje": f'El producto "{p.nombre}" tiene una cantidad de {stock} lo cual está bajo el mínimo ({minimo}).',
                    "fecha": "Justo ahora"
                })
                
    return jsonify(alertas)
