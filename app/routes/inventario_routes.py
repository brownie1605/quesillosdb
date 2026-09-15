from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Inventario, Producto, Categoria
from app.services.inventario_service import InventarioService

from app.utils.decorators import require_roles

inventario_bp = Blueprint("inventario", __name__, url_prefix="/inventario")

@inventario_bp.before_request
def check_roles():
    return require_roles('Administrador', 'Cajero', 'Inventario')


@inventario_bp.route("/")
@login_required
def lista():
    return render_template("inventario/lista.html")

def _inventarios_por_producto(productos):
    """Una sola consulta para el inventario de todos los productos dados,
    en vez de una consulta por producto (N+1)."""
    ids = [p.id_producto for p in productos]
    if not ids:
        return {}
    return {inv.id_producto: inv for inv in Inventario.query.filter(Inventario.id_producto.in_(ids)).all()}


def _grupo_inventario(producto, categoria_nombre):
    """Agrupa cada producto en una de 4 vistas de Inventario:
    Limpieza / Lacteos / POS / Varios.

    'POS' = lo que se vende como plato terminado (tipo_producto='final'
    y se_vende) -- es exactamente lo mismo que se ofrece para pedir en
    la pantalla de Mesas (ver /ventas/api/productos?contexto=mesas).
    No se toca la categorizacion fina existente (Desayunos, Quesillos,
    etc.) -- este grupo es solo para la vista de Inventario."""
    if producto.tipo_producto == "final" and producto.se_vende:
        return "POS"
    nombre_cat = (categoria_nombre or "").strip().lower()
    if nombre_cat == "limpieza":
        return "Limpieza"
    if nombre_cat in ("lacteos", "lácteos"):
        return "Lácteos"
    return "Varios"


@inventario_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    productos = Producto.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    inventarios = _inventarios_por_producto(productos)
    categorias = {c.id_categoria: c.nombre for c in Categoria.query.all()}
    res = []
    for p in productos:
        inv = inventarios.get(p.id_producto)
        d = p.to_dict()
        d["stock_actual"] = float(inv.stock_actual) if inv else 0.0
        d["stock_minimo"] = float(inv.stock_minimo) if inv else 0.0
        d["id_inventario"] = inv.id_inventario if inv else None
        categoria_nombre = categorias.get(p.id_categoria)
        d["categoria_nombre"] = categoria_nombre or "Sin categoría"
        d["grupo_inventario"] = _grupo_inventario(p, categoria_nombre)
        res.append(d)
    return jsonify(res)


@inventario_bp.route("/movimientos")
@login_required
def movimientos():
    """Kardex simple: quien movio que, cuando y por que -- para poder
    responder esa pregunta cuando algo no cuadra en el inventario."""
    return render_template("inventario/movimientos.html")


@inventario_bp.route("/api/movimientos", methods=["GET"])
@login_required
def api_movimientos():
    from app.models import MovimientoInventario, Usuario

    id_producto = request.args.get("id_producto", type=int)
    tipo = request.args.get("tipo")

    q = MovimientoInventario.query.filter_by(id_empresa=current_user.id_empresa)
    if id_producto:
        q = q.filter_by(id_producto=id_producto)
    if tipo:
        q = q.filter_by(tipo_movimiento=tipo)

    filas = q.order_by(MovimientoInventario.fecha_movimiento.desc()).limit(500).all()
    usuarios = {u.id_usuario: u.nombre_completo for u in Usuario.query.all()}

    res = []
    for m in filas:
        d = m.to_dict()
        d["usuario"] = usuarios.get(m.id_usuario, "—")
        res.append(d)
    return jsonify(res)

@inventario_bp.route("/api/notificaciones", methods=["GET"])
@login_required
def api_notificaciones():
    productos = Producto.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    inventarios = _inventarios_por_producto(productos)
    alertas = []

    for p in productos:
        inv = inventarios.get(p.id_producto)
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
