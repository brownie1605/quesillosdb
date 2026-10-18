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

def _rango_fechas(dias_por_defecto):
    """(desde, hasta) de ?inicio=YYYY-MM-DD&fin=YYYY-MM-DD; por defecto los
    ultimos `dias_por_defecto` dias hasta hoy."""
    from datetime import date, timedelta
    from app.utils.date_utils import nicaragua_now

    hoy = nicaragua_now().date()
    try:
        desde = date.fromisoformat(request.args.get("inicio")) if request.args.get("inicio") else None
        hasta = date.fromisoformat(request.args.get("fin")) if request.args.get("fin") else None
    except ValueError:
        desde = hasta = None
    hasta = hasta or hoy
    desde = desde or (hasta - timedelta(days=dias_por_defecto - 1))
    if desde > hasta:
        desde, hasta = hasta, desde
    return desde, hasta


@inventario_bp.route("/api/consumo", methods=["GET"])
@login_required
def api_consumo():
    """Cuanto se uso de cada producto por dia o por mes (?agrupar=dia|mes)."""
    desde, hasta = _rango_fechas(1)
    datos = InventarioService.consumo(desde, hasta, request.args.get("agrupar", "dia"))
    datos.update({"inicio": desde.isoformat(), "fin": hasta.isoformat()})
    return jsonify(datos)


@inventario_bp.route("/api/bajas", methods=["GET"])
@login_required
def api_bajas():
    from app.models import Usuario

    desde, hasta = _rango_fechas(30)
    filas = InventarioService.bajas(desde, hasta)
    usuarios = {u.id_usuario: u.nombre_completo for u in Usuario.query.all()}
    for f in filas:
        f["usuario"] = usuarios.get(f.pop("id_usuario"), "—")
    return jsonify({
        "inicio": desde.isoformat(), "fin": hasta.isoformat(),
        "motivos": list(InventarioService.MOTIVOS_BAJA),
        "bajas": filas,
        "total_costo": round(sum(f["costo"] for f in filas), 2),
    })


@inventario_bp.route("/api/bajas", methods=["POST"])
@login_required
def api_registrar_baja():
    from app.services.auditoria_service import registrar_auditoria
    from app.services.inventario_service import StockInsuficiente

    data = request.get_json(silent=True) or {}
    try:
        mov = InventarioService.registrar_baja(
            int(data.get("id_producto") or 0), data.get("cantidad"),
            data.get("motivo"), current_user.id_usuario, data.get("detalle"),
        )
    except StockInsuficiente as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 409
    except (ValueError, TypeError, ArithmeticError) as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e) or "Datos invalidos"}), 400
    registrar_auditoria("BAJA INVENTARIO", "Inventario", {
        "id_producto": mov.id_producto, "cantidad": float(mov.cantidad), "motivo": mov.observacion,
    })
    return jsonify({"success": True, "message": "Baja registrada"})


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
