from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Compra, DetalleCompra, Producto, Proveedor, Inventario
from datetime import datetime
from app.utils.date_utils import nicaragua_now

from app.utils.decorators import require_roles

compra_bp = Blueprint("compra", __name__, url_prefix="/compras")

@compra_bp.before_request
def check_roles():
    return require_roles('Administrador', 'Cajero', 'Inventario')


@compra_bp.route("/")
@login_required
def lista():
    return render_template("compras/lista.html")

@compra_bp.route("/api/list", methods=["GET"])
@login_required
def api_list():
    compras = Compra.query.filter_by(id_empresa=current_user.id_empresa).order_by(Compra.fecha_compra.desc()).all()
    res = []
    for c in compras:
        prov = Proveedor.query.get(c.id_proveedor) if c.id_proveedor else None
        d = c.to_dict()
        if c.tipo_compra == 'varios':
            d["proveedor_nombre"] = "Gasto Vario"
            if c.descripcion_gasto:
                d["proveedor_nombre"] += f" ({c.descripcion_gasto})"
        else:
            d["proveedor_nombre"] = prov.nombre if prov else "Desconocido"
        d["id_proveedor"] = c.id_proveedor
        res.append(d)
    return jsonify(res)

@compra_bp.route("/api/crear", methods=["POST"])
@login_required
def api_crear():
    data = request.json
    id_proveedor = data.get("id_proveedor")
    items = data.get("items", [])
    
    if id_proveedor == "varios":
        descripcion = data.get("descripcion")
        monto = data.get("monto")
        if not descripcion or not monto:
            return jsonify({"success": False, "message": "Descripción y monto son obligatorios para gastos"}), 400
        
        try:
            prov_varios = Proveedor.query.filter(Proveedor.nombre.ilike('%varios%')).first()
            id_prov_varios = prov_varios.id_proveedor if prov_varios else None

            num_compra = f"GV-{nicaragua_now().strftime('%Y%m%d%H%M%S')}"
            nueva_compra = Compra(
                id_empresa=current_user.id_empresa,
                id_sucursal=current_user.id_sucursal,
                id_usuario=current_user.id_usuario,
                id_proveedor=id_prov_varios,
                numero_compra=num_compra,
                subtotal=float(monto),
                impuesto=0.0,
                total=float(monto),
                estado="completada",
                tipo_compra="varios",
                descripcion_gasto=descripcion
            )
            db.session.add(nueva_compra)
            db.session.commit()
            return jsonify({"success": True, "message": "Gasto vario registrado exitosamente"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": str(e)}), 500
            
    if not items:
        return jsonify({"success": False, "message": "No hay productos en la compra"}), 400
        
    try:
        subtotal_compra = 0.0
        num_compra = f"C-{nicaragua_now().strftime('%Y%m%d%H%M%S')}"
        
        nueva_compra = Compra(
            id_empresa=current_user.id_empresa,
            id_sucursal=current_user.id_sucursal,
            id_usuario=current_user.id_usuario,
            id_proveedor=id_proveedor,
            numero_compra=num_compra,
            subtotal=0.0,
            impuesto=0.0,
            total=0.0,
            estado="completada"
        )
        db.session.add(nueva_compra)
        db.session.flush()
        
        for item in items:
            producto_id = item.get("id_producto")
            cantidad = float(item.get("cantidad", 0))
            costo_unitario = float(item.get("costo_unitario", 0))
            subtotal_item = cantidad * costo_unitario
            subtotal_compra += subtotal_item
            
            detalle = DetalleCompra(
                id_compra=nueva_compra.id_compra,
                id_producto=producto_id,
                cantidad=cantidad,
                precio_unitario=costo_unitario,
                subtotal=subtotal_item
            )
            db.session.add(detalle)
            
            # Sumar al inventario
            inv = Inventario.query.filter_by(id_producto=producto_id).first()
            if inv:
                inv.stock_actual = float(inv.stock_actual) + cantidad
            else:
                inv = Inventario(
                    id_sucursal=current_user.id_sucursal,
                    id_producto=producto_id,
                    stock_actual=cantidad,
                    stock_minimo=0
                )
                db.session.add(inv)
                
        nueva_compra.subtotal = subtotal_compra
        nueva_compra.total = subtotal_compra # Asumimos 0 impuesto por ahora
        
        db.session.commit()
        return jsonify({"success": True, "message": "Compra registrada exitosamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@compra_bp.route("/api/detalle/<int:id>", methods=["GET"])
@login_required
def api_detalle(id):
    try:
        compra = Compra.query.get_or_404(id)
        if compra.id_empresa != current_user.id_empresa:
            return jsonify({"success": False, "message": "Acceso denegado"}), 403
            
        detalles = DetalleCompra.query.filter_by(id_compra=id).all()
        res_detalles = []
        if compra.tipo_compra == 'varios':
            res_detalles.append({
                "producto_nombre": "Gasto Vario: " + (compra.descripcion_gasto or ""),
                "cantidad": 1,
                "precio_unitario": float(compra.total),
                "subtotal": float(compra.total)
            })
        else:
            for d in detalles:
                prod = Producto.query.get(d.id_producto)
                dt = d.to_dict()
                dt["producto_nombre"] = prod.nombre if prod else "Desconocido"
                res_detalles.append(dt)
            
        return jsonify({"success": True, "detalles": res_detalles})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@compra_bp.route("/api/editar/<int:id>", methods=["PUT"])
@login_required
def api_editar(id):
    compra = Compra.query.get_or_404(id)
    if compra.id_empresa != current_user.id_empresa:
        return jsonify({"success": False, "message": "Acceso denegado"}), 403
        
    data = request.json
    id_proveedor = data.get("id_proveedor")
    items = data.get("items", [])
    
    if id_proveedor == "varios":
        descripcion = data.get("descripcion")
        monto = data.get("monto")
        if not descripcion or not monto:
            return jsonify({"success": False, "message": "Descripción y monto son obligatorios para gastos"}), 400
        try:
            prov_varios = Proveedor.query.filter(Proveedor.nombre.ilike('%varios%')).first()
            id_prov_varios = prov_varios.id_proveedor if prov_varios else None

            compra.id_proveedor = id_prov_varios
            compra.tipo_compra = "varios"
            compra.descripcion_gasto = descripcion
            compra.subtotal = float(monto)
            compra.total = float(monto)
            db.session.commit()
            return jsonify({"success": True, "message": "Gasto actualizado exitosamente"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "message": str(e)}), 500

    if not items:
        return jsonify({"success": False, "message": "No hay productos en la compra"}), 400
        
    try:
        # 1. Revertir inventario de la compra anterior
        detalles_previos = DetalleCompra.query.filter_by(id_compra=id).all()
        for dp in detalles_previos:
            inv = Inventario.query.filter_by(id_producto=dp.id_producto).first()
            if inv:
                inv.stock_actual = float(inv.stock_actual) - float(dp.cantidad)
                
        # 2. Eliminar detalles de compra anteriores
        DetalleCompra.query.filter_by(id_compra=id).delete()
        
        # 3. Guardar nuevos datos de compra y calcular total
        compra.id_proveedor = id_proveedor
        subtotal_compra = 0.0
        
        for item in items:
            producto_id = item.get("id_producto")
            cantidad = float(item.get("cantidad", 0))
            costo_unitario = float(item.get("costo_unitario", 0))
            subtotal_item = cantidad * costo_unitario
            subtotal_compra += subtotal_item
            
            detalle = DetalleCompra(
                id_compra=compra.id_compra,
                id_producto=producto_id,
                cantidad=cantidad,
                precio_unitario=costo_unitario,
                subtotal=subtotal_item
            )
            db.session.add(detalle)
            
            # Sumar al inventario
            inv = Inventario.query.filter_by(id_producto=producto_id).first()
            if inv:
                inv.stock_actual = float(inv.stock_actual) + cantidad
            else:
                inv = Inventario(
                    id_sucursal=current_user.id_sucursal,
                    id_producto=producto_id,
                    stock_actual=cantidad,
                    stock_minimo=0
                )
                db.session.add(inv)
                
        compra.subtotal = subtotal_compra
        compra.total = subtotal_compra
        
        db.session.commit()
        return jsonify({"success": True, "message": "Compra actualizada exitosamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
