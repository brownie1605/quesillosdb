from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Producto, Categoria, Inventario, Marca, UnidadMedida
from datetime import datetime
import os
import io
from werkzeug.utils import secure_filename
from flask import send_file

from app.utils.decorators import require_roles

producto_bp = Blueprint("producto", __name__, url_prefix="/productos")

@producto_bp.before_request
def check_roles():
    return require_roles('Administrador', 'Cajero', 'Inventario')


@producto_bp.route("/")
@login_required
def lista():
    return render_template("productos/lista.html")

@producto_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    productos = Producto.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    resultado = []
    for p in productos:
        cat = Categoria.query.get(p.id_categoria) if p.id_categoria else None
        inv = Inventario.query.filter_by(id_producto=p.id_producto).first()
        
        data = p.to_dict()
        data["categoria_nombre"] = cat.nombre if cat else "Sin Categoría"
        data["precio_compra"] = float(p.precio_compra) if p.precio_compra else 0.0
        data["stock"] = float(inv.stock_actual) if inv else 0.0
        data["stock_minimo"] = float(inv.stock_minimo) if inv and inv.stock_minimo else 0.0
        data["estado"] = p.estado
        data["id_marca"] = p.id_marca
        data["id_unidad"] = p.id_unidad
        data["codigo_barra"] = p.codigo_barra
        data["descripcion"] = p.descripcion
        data["aplica_impuesto"] = p.aplica_impuesto
        resultado.append(data)
    return jsonify(resultado)

@producto_bp.route("/api/categorias", methods=["GET"])
@login_required
def api_categorias():
    categorias = Categoria.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    return jsonify([c.to_dict() for c in categorias])

@producto_bp.route("/api/marcas", methods=["GET"])
@login_required
def api_marcas():
    marcas = Marca.query.filter_by(estado="activo", id_empresa=current_user.id_empresa).all()
    return jsonify([m.to_dict() for m in marcas])

@producto_bp.route("/api/marcas/crear", methods=["POST"])
@login_required
def api_marcas_crear():
    data = request.json
    try:
        nueva_marca = Marca(
            id_empresa=current_user.id_empresa,
            nombre=data.get("nombre", ""),
            estado="activo"
        )
        db.session.add(nueva_marca)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/unidades", methods=["GET"])
@login_required
def api_unidades():
    unidades = UnidadMedida.query.filter_by(estado="activo").all()
    return jsonify([u.to_dict() for u in unidades])

@producto_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads', 'productos')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    try:
        imagen_file = request.files.get('imagen')
        imagen_url = None
        imagen_datos = None
        imagen_mimetype = None
        
        if imagen_file and imagen_file.filename:
            imagen_datos = imagen_file.read()
            imagen_mimetype = imagen_file.mimetype

        nuevo_prod = Producto(
            id_empresa=current_user.id_empresa,
            id_categoria=request.form.get("id_categoria") or None,
            id_marca=request.form.get("id_marca") or None,
            id_unidad=request.form.get("id_unidad") or None,
            codigo=request.form.get("codigo", ""),
            codigo_barra=request.form.get("codigo_barra", ""),
            nombre=request.form.get("nombre"),
            descripcion=request.form.get("descripcion", ""),
            precio_compra=float(request.form.get("precio_compra", 0.0)),
            precio_venta=float(request.form.get("precio_venta", 0.0)),
            aplica_impuesto=request.form.get("aplica_impuesto") == 'true',
            imagen_url=imagen_url,
            imagen_datos=imagen_datos,
            imagen_mimetype=imagen_mimetype,
            estado="activo"
        )
        db.session.add(nuevo_prod)
        db.session.flush() # Get ID
        
        if imagen_datos:
            nuevo_prod.imagen_url = f"/productos/imagen/{nuevo_prod.id_producto}"
            
        # Generar código automáticamente si no se proporcionó
        if not nuevo_prod.codigo or nuevo_prod.codigo.strip() == "":
            nuevo_prod.codigo = f"P{nuevo_prod.id_producto:03d}"
            
        # Crear inventario en 0
        nuevo_inv = Inventario(
            id_sucursal=current_user.id_sucursal,
            id_producto=nuevo_prod.id_producto,
            stock_actual=0.0,
            stock_minimo=float(request.form.get("stock_minimo", 0.0))
        )
        db.session.add(nuevo_inv)
        db.session.commit()
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria("CREAR PRODUCTO", "Productos", f"Producto {nuevo_prod.nombre} creado (Código: {nuevo_prod.codigo})")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/editar/<int:id>", methods=["POST"])
@login_required
def api_editar(id):
    UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads', 'productos')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403

        imagen_file = request.files.get('imagen')
        if imagen_file and imagen_file.filename:
            prod.imagen_datos = imagen_file.read()
            prod.imagen_mimetype = imagen_file.mimetype
            prod.imagen_url = f"/productos/imagen/{prod.id_producto}"

        prod.codigo = request.form.get("codigo", prod.codigo)
        prod.codigo_barra = request.form.get("codigo_barra", prod.codigo_barra)
        prod.nombre = request.form.get("nombre", prod.nombre)
        prod.descripcion = request.form.get("descripcion", prod.descripcion)
        prod.id_categoria = request.form.get("id_categoria") or None
        prod.id_marca = request.form.get("id_marca") or None
        prod.id_unidad = request.form.get("id_unidad") or None
        prod.precio_compra = float(request.form.get("precio_compra", prod.precio_compra or 0.0))
        prod.precio_venta = float(request.form.get("precio_venta", prod.precio_venta))
        prod.aplica_impuesto = request.form.get("aplica_impuesto") == 'true'
        
        # Actualizar stock mínimo si existe el registro de inventario
        inv = Inventario.query.filter_by(id_producto=prod.id_producto).first()
        if inv:
            inv.stock_minimo = float(request.form.get("stock_minimo", inv.stock_minimo or 0.0))
        
        db.session.commit()
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria("EDITAR PRODUCTO", "Productos", f"Producto {prod.nombre} modificado")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/eliminar/<int:id>", methods=["DELETE"])
@login_required
def api_eliminar(id):
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        prod.estado = "inactivo"
        db.session.commit()
        from app.services.auditoria_service import registrar_auditoria
        registrar_auditoria("ELIMINAR PRODUCTO", "Productos", f"Producto {prod.nombre} marcado como inactivo")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/api/entrada/<int:id>", methods=["POST"])
@login_required
def api_entrada(id):
    data = request.json
    cantidad = float(data.get("cantidad", 0.0))
    if cantidad <= 0:
        return jsonify({"success": False, "message": "Cantidad debe ser mayor a 0"}), 400
        
    try:
        prod = Producto.query.get_or_404(id)
        if prod.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        inv = Inventario.query.filter_by(id_producto=id).first()
        if not inv:
            return jsonify({"success": False, "message": "Inventario no encontrado para este producto"}), 404
            
        inv.stock_actual = float(inv.stock_actual) + cantidad
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@producto_bp.route("/imagen/<int:id>", methods=["GET"])
def obtener_imagen(id):
    prod = Producto.query.get_or_404(id)
    if prod.imagen_datos and prod.imagen_mimetype:
        return send_file(
            io.BytesIO(prod.imagen_datos),
            mimetype=prod.imagen_mimetype,
            as_attachment=False
        )
    # Retornar una imagen por defecto o error 404
    return "", 404
