"""Modulo de insumos.

Un insumo es un producto que se usa como ingrediente de recetas Y que ademas
puede venderse directamente al cliente (ej. "Tortilla docena" a C$25).
"""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Producto, Inventario, UnidadMedida, Categoria, RecetaIngrediente, Receta
from app.services.inventario_service import InventarioService
from app.services.auditoria_service import registrar_auditoria
from app.utils.decorators import require_roles, usuario_tiene_rol
from app.utils.date_utils import nicaragua_now

insumo_bp = Blueprint("insumo", __name__, url_prefix="/insumos")


@insumo_bp.before_request
def check_roles():
    # Todos los roles pueden consultar insumos; la escritura se valida por vista.
    return require_roles("Admin", "Administrador", "Cocinero", "Cajero", "Mesero")


def _solo_escritura():
    if not usuario_tiene_rol("Admin", "Administrador", "Cocinero"):
        return jsonify(
            {"success": False, "message": "Solo Admin y Cocinero pueden modificar insumos"}
        ), 403
    return None


# ---------------------------------------------------------------- vistas
@insumo_bp.route("/")
@login_required
def lista():
    unidades = UnidadMedida.query.filter_by(estado="activo").all()
    categorias = Categoria.query.filter_by(estado="activo").all()
    return render_template("insumos/lista.html", unidades=unidades, categorias=categorias)


# ---------------------------------------------------------------- API
@insumo_bp.route("/api/lista", methods=["GET"])
@login_required
def api_lista():
    tipo = request.args.get("tipo")  # insumo | material | todos
    q = Producto.query.filter(Producto.estado == "activo")
    if tipo in ("insumo", "material"):
        q = q.filter(Producto.tipo_producto == tipo)
    else:
        q = q.filter(Producto.tipo_producto.in_(["insumo", "material"]))

    salida = []
    for p in q.order_by(Producto.nombre).all():
        inv = Inventario.query.filter_by(id_producto=p.id_producto).first()
        d = p.to_dict()
        d["stock"] = float(inv.stock_actual) if inv else 0.0
        d["stock_minimo"] = float(inv.stock_minimo) if inv else 0.0
        d["bajo_minimo"] = d["stock"] <= d["stock_minimo"]
        d["usado_en_recetas"] = (
            db.session.query(RecetaIngrediente)
            .filter_by(id_producto=p.id_producto)
            .count()
        )
        salida.append(d)
    return jsonify(salida)


@insumo_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    bloqueo = _solo_escritura()
    if bloqueo:
        return bloqueo

    data = request.get_json(silent=True) or {}
    if not data.get("nombre"):
        return jsonify({"success": False, "message": "El nombre es obligatorio"}), 400

    try:
        producto = Producto(
            id_empresa=current_user.id_empresa,
            id_categoria=data.get("id_categoria") or None,
            id_unidad=data.get("id_unidad") or None,
            codigo=data.get("codigo"),
            nombre=data["nombre"],
            descripcion=data.get("descripcion"),
            precio_compra=data.get("precio_compra") or 0,
            precio_venta=data.get("precio_venta") or 0,
            tipo_producto=data.get("tipo_producto", "insumo"),
            es_ingrediente_receta=True,
            se_vende=bool(data.get("se_vende", True)),
            estado="activo",
            estado_sync="pendiente",
        )
        db.session.add(producto)
        db.session.flush()

        inv = Inventario(
            id_producto=producto.id_producto,
            id_sucursal=current_user.id_sucursal or 1,
            stock_actual=data.get("stock_inicial") or 0,
            stock_minimo=data.get("stock_minimo") or 0,
            stock_maximo=data.get("stock_maximo") or 0,
        )
        db.session.add(inv)
        db.session.flush()

        db.session.commit()
        registrar_auditoria("crear", "insumos", {"id_producto": producto.id_producto})
        return jsonify({"success": True, "message": "Insumo creado", "producto": producto.to_dict()})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@insumo_bp.route("/api/<int:id_producto>/actualizar", methods=["POST", "PUT"])
@login_required
def api_actualizar(id_producto):
    bloqueo = _solo_escritura()
    if bloqueo:
        return bloqueo

    data = request.get_json(silent=True) or {}
    producto = Producto.query.get_or_404(id_producto)
    try:
        for campo in ("nombre", "descripcion", "codigo"):
            if campo in data:
                setattr(producto, campo, data[campo])
        if "precio_compra" in data:
            producto.precio_compra = data["precio_compra"] or 0
        if "precio_venta" in data:
            producto.precio_venta = data["precio_venta"] or 0
        if "id_unidad" in data:
            producto.id_unidad = data["id_unidad"] or None
        if "id_categoria" in data:
            producto.id_categoria = data["id_categoria"] or None
        if "tipo_producto" in data:
            producto.tipo_producto = data["tipo_producto"]
        if "se_vende" in data:
            producto.se_vende = bool(data["se_vende"])
        if "estado" in data:
            producto.estado = data["estado"]
        producto.fecha_actualizacion = nicaragua_now()
        producto.estado_sync = "pendiente"

        inv = Inventario.query.filter_by(id_producto=id_producto).first()
        if inv:
            if "stock_minimo" in data:
                inv.stock_minimo = data["stock_minimo"] or 0
            if "stock_maximo" in data:
                inv.stock_maximo = data["stock_maximo"] or 0

        db.session.commit()

        # Recalcula el costo de las recetas que usan este insumo.
        _recalcular_recetas_de(id_producto)

        registrar_auditoria("actualizar", "insumos", {"id_producto": id_producto})
        return jsonify({"success": True, "message": "Insumo actualizado"})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@insumo_bp.route("/api/<int:id_producto>/ajustar-stock", methods=["POST"])
@login_required
def api_ajustar_stock(id_producto):
    bloqueo = _solo_escritura()
    if bloqueo:
        return bloqueo

    data = request.get_json(silent=True) or {}
    cantidad = data.get("cantidad")
    if cantidad is None:
        return jsonify({"success": False, "message": "cantidad requerida"}), 400
    try:
        mov = InventarioService.mover(
            id_producto,
            float(cantidad),
            data.get("tipo_movimiento", "ajuste"),
            current_user.id_usuario,
            referencia=data.get("referencia"),
            observacion=data.get("observacion", "Ajuste manual de insumo"),
            commit=True,
        )
        registrar_auditoria("actualizar", "inventario", {"id_producto": id_producto})
        return jsonify({"success": True, "message": "Stock ajustado", "movimiento": mov.to_dict()})
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@insumo_bp.route("/api/<int:id_producto>/recetas", methods=["GET"])
@login_required
def api_recetas_que_lo_usan(id_producto):
    filas = (
        db.session.query(RecetaIngrediente, Receta)
        .join(Receta, Receta.id_receta == RecetaIngrediente.id_receta)
        .filter(RecetaIngrediente.id_producto == id_producto)
        .all()
    )
    return jsonify(
        [
            {
                "id_receta": r.id_receta,
                "receta": r.nombre,
                "cantidad_necesaria": float(ing.cantidad_necesaria or 0),
            }
            for ing, r in filas
        ]
    )


# ---------------------------------------------------------------- helpers
def _recalcular_recetas_de(id_producto):
    from app.services.receta_service import RecetaService

    ids = {
        i.id_receta
        for i in RecetaIngrediente.query.filter_by(id_producto=id_producto).all()
    }
    for id_receta in ids:
        receta = Receta.query.get(id_receta)
        if receta:
            receta.costo_total = RecetaService.calcular_costo_receta(receta)
    if ids:
        db.session.commit()
