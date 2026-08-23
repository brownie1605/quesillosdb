from flask import Blueprint, render_template, jsonify, send_file, request
from flask_login import login_required, current_user
from sqlalchemy import text
from app.extensions import db
from datetime import timedelta, datetime
from app.utils.date_utils import nicaragua_now
import csv
import io

from app.utils.decorators import require_roles

reporte_bp = Blueprint("reporte", __name__, url_prefix="/reportes")

@reporte_bp.before_request
def check_roles():
    return require_roles('Administrador')


@reporte_bp.route("/")
@login_required
def index():
    return render_template("reportes/index.html")

@reporte_bp.route("/api/resumen_ventas", methods=["GET"])
@login_required
def api_resumen_ventas():
    try:
        inicio = request.args.get('inicio')
        fin = request.args.get('fin')
        
        if inicio and fin:
            start_date = datetime.strptime(inicio, '%Y-%m-%d').date()
            end_date = datetime.strptime(fin, '%Y-%m-%d').date()
            dias_diff = (end_date - start_date).days
            limit_clause = "" # If date range is given, don't limit by 7
        else:
            hoy = nicaragua_now().date()
            start_date = hoy - timedelta(days=6)
            end_date = hoy
            limit_clause = "LIMIT 7"
            
        query = text(f"""
            SELECT DATE(fecha_venta) as fecha, SUM(total) as total_ventas
            FROM ventas
            WHERE id_empresa = :empresa AND estado = 'completada'
            AND DATE(fecha_venta) >= :start_date AND DATE(fecha_venta) <= :end_date
            GROUP BY DATE(fecha_venta)
            ORDER BY fecha DESC
            {limit_clause}
        """)
        result = db.session.execute(query, {"empresa": current_user.id_empresa, "start_date": start_date, "end_date": end_date}).fetchall()
        
        # Gastos
        query_gastos = text("""
            SELECT DATE(fecha_compra), SUM(total)
            FROM compras
            WHERE id_empresa = :empresa AND estado = 'completada'
            AND DATE(fecha_compra) >= :start_date AND DATE(fecha_compra) <= :end_date
            GROUP BY DATE(fecha_compra)
        """)
        gastos_res = db.session.execute(query_gastos, {"empresa": current_user.id_empresa, "start_date": start_date, "end_date": end_date}).fetchall()
        gastos_dict = {str(row[0]): float(row[1] or 0) for row in gastos_res}

        datos = []
        for row in result:
            fecha_str = str(row[0])
            total_ventas = float(row[1] or 0)
            gastos = gastos_dict.get(fecha_str, 0.0)
            datos.append({
                "fecha": fecha_str,
                "total": total_ventas,
                "ganancia": total_ventas - gastos,
                "gastos": gastos
            })
            
        return jsonify({"success": True, "data": datos[::-1]}) # Reverse to show chronologically
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@reporte_bp.route("/api/resumen_financiero", methods=["GET"])
@login_required
def api_resumen_financiero():
    """Resumen financiero de un rango (o de los ultimos 7 dias por defecto).
    Usa la misma logica que el CSV de exportar_ventas: ganancia bruta =
    ventas - costo de productos vendidos; ganancia neta = bruta - gastos
    varios (compras tipo_compra='varios')."""
    try:
        inicio = request.args.get('inicio')
        fin = request.args.get('fin')
        if inicio and fin:
            fecha_inicio, fecha_fin = inicio, fin
        else:
            hoy = nicaragua_now().date()
            fecha_inicio = str(hoy - timedelta(days=6))
            fecha_fin = str(hoy)

        query_ventas = text("""
            SELECT COALESCE(SUM(v.total), 0) as total_vendido,
                   COALESCE(SUM((SELECT SUM(dv.cantidad * p.precio_compra) FROM detalle_ventas dv JOIN productos p ON dv.id_producto = p.id_producto WHERE dv.id_venta = v.id_venta)), 0) as costo_total,
                   COUNT(*) as cantidad_ventas
            FROM ventas v
            WHERE v.id_empresa = :empresa AND v.estado = 'completada'
            AND DATE(v.fecha_venta) >= :inicio AND DATE(v.fecha_venta) <= :fin
        """)
        fila = db.session.execute(query_ventas, {"empresa": current_user.id_empresa, "inicio": fecha_inicio, "fin": fecha_fin}).fetchone()
        total_vendido = float(fila.total_vendido or 0)
        costo_total = float(fila.costo_total or 0)
        cantidad_ventas = int(fila.cantidad_ventas or 0)

        query_gastos = text("""
            SELECT COALESCE(SUM(total), 0) FROM compras
            WHERE id_empresa = :empresa AND estado = 'completada' AND tipo_compra = 'varios'
            AND DATE(fecha_compra) >= :inicio AND DATE(fecha_compra) <= :fin
        """)
        total_gastos = float(db.session.execute(query_gastos, {"empresa": current_user.id_empresa, "inicio": fecha_inicio, "fin": fecha_fin}).scalar() or 0)

        ganancia_bruta = total_vendido - costo_total
        ganancia_neta = ganancia_bruta - total_gastos

        return jsonify({
            "success": True,
            "inicio": fecha_inicio,
            "fin": fecha_fin,
            "total_vendido": total_vendido,
            "cantidad_ventas": cantidad_ventas,
            "ticket_promedio": (total_vendido / cantidad_ventas) if cantidad_ventas else 0.0,
            "costo_productos": costo_total,
            "ganancia_bruta": ganancia_bruta,
            "gastos_varios": total_gastos,
            "ganancia_neta": ganancia_neta,
            "margen_pct": (ganancia_neta / total_vendido * 100) if total_vendido else 0.0
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@reporte_bp.route("/api/productos_top", methods=["GET"])
@login_required
def api_productos_top():
    try:
        inicio = request.args.get('inicio')
        fin = request.args.get('fin')

        if not inicio or not fin:
            hoy = nicaragua_now().date()
            inicio = str(hoy - timedelta(days=6))
            fin = str(hoy)

        date_filter = "AND DATE(v.fecha_venta) >= :inicio AND DATE(v.fecha_venta) <= :fin"
        params = {"empresa": current_user.id_empresa, "inicio": inicio, "fin": fin}

        # Consultar productos más vendidos
        query = text(f"""
            SELECT p.nombre, SUM(dv.cantidad) as cantidad, SUM(dv.subtotal) as ingresos
            FROM detalle_ventas dv
            JOIN productos p ON dv.id_producto = p.id_producto
            JOIN ventas v ON dv.id_venta = v.id_venta
            WHERE v.id_empresa = :empresa AND v.estado = 'completada'
            {date_filter}
            GROUP BY p.id_producto
            ORDER BY cantidad DESC
            LIMIT 5
        """)
        result = db.session.execute(query, params).fetchall()
        
        datos = []
        for row in result:
            datos.append({
                "producto": row[0],
                "cantidad": float(row[1] or 0),
                "ingresos": float(row[2] or 0)
            })
            
        return jsonify({"success": True, "data": datos})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@reporte_bp.route("/api/stock_bajo", methods=["GET"])
@login_required
def api_stock_bajo():
    try:
        query = text("""
            SELECT p.nombre, i.stock_actual, i.stock_minimo
            FROM inventario i
            JOIN productos p ON i.id_producto = p.id_producto
            WHERE p.id_empresa = :empresa AND p.estado = 'activo'
            AND i.stock_actual <= i.stock_minimo
            ORDER BY i.stock_actual ASC
        """)
        result = db.session.execute(query, {"empresa": current_user.id_empresa}).fetchall()
        
        datos = []
        for row in result:
            datos.append({
                "producto": row[0],
                "stock_actual": float(row[1] or 0),
                "stock_minimo": float(row[2] or 0)
            })
            
        return jsonify({"success": True, "data": datos})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@reporte_bp.route("/api/exportar/ventas", methods=["GET"])
@login_required
def exportar_ventas():
    fecha_inicio = request.args.get('inicio', '')
    fecha_fin = request.args.get('fin', '')
    
    if not fecha_inicio or not fecha_fin:
        return jsonify({"success": False, "message": "Fechas son requeridas"}), 400
        
    try:
        query_ventas = text("""
            SELECT v.numero_venta, v.fecha_venta, v.total, 
                   COALESCE((SELECT SUM(dv.cantidad * p.precio_compra) FROM detalle_ventas dv JOIN productos p ON dv.id_producto = p.id_producto WHERE dv.id_venta = v.id_venta), 0) as costo_total
            FROM ventas v
            WHERE v.id_empresa = :empresa AND v.estado = 'completada'
            AND DATE(v.fecha_venta) >= :inicio AND DATE(v.fecha_venta) <= :fin
            ORDER BY v.fecha_venta DESC
        """)
        ventas = db.session.execute(query_ventas, {"empresa": current_user.id_empresa, "inicio": fecha_inicio, "fin": fecha_fin}).fetchall()
        
        query_gastos = text("""
            SELECT numero_compra, fecha_compra, total, descripcion_gasto
            FROM compras
            WHERE id_empresa = :empresa AND estado = 'completada' AND tipo_compra = 'varios'
            AND DATE(fecha_compra) >= :inicio AND DATE(fecha_compra) <= :fin
            ORDER BY fecha_compra DESC
        """)
        gastos = db.session.execute(query_gastos, {"empresa": current_user.id_empresa, "inicio": fecha_inicio, "fin": fecha_fin}).fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # VENTAS
        writer.writerow(["--- REPORTE DE VENTAS ---"])
        writer.writerow(["No. Venta", "Fecha", "Total Vendido (C$)", "Costo de Productos (C$)", "Ganancia Bruta (C$)"])
        total_vendido = 0
        total_costo = 0
        for v in ventas:
            ganancia = float(v.total) - float(v.costo_total)
            writer.writerow([v.numero_venta, v.fecha_venta.strftime("%Y-%m-%d %H:%M:%S"), float(v.total), float(v.costo_total), ganancia])
            total_vendido += float(v.total)
            total_costo += float(v.costo_total)
            
        writer.writerow([])
        writer.writerow(["TOTALES VENTAS", "", total_vendido, total_costo, total_vendido - total_costo])
        writer.writerow([])
        writer.writerow([])
        
        # GASTOS
        writer.writerow(["--- GASTOS VARIOS ---"])
        writer.writerow(["No. Gasto", "Fecha", "Descripcion", "Monto (C$)"])
        total_gastos = 0
        for g in gastos:
            writer.writerow([g.numero_compra, g.fecha_compra.strftime("%Y-%m-%d %H:%M:%S"), g.descripcion_gasto, float(g.total)])
            total_gastos += float(g.total)
            
        writer.writerow([])
        writer.writerow(["TOTAL GASTOS", "", "", total_gastos])
        writer.writerow([])
        writer.writerow([])
        
        # RESUMEN FINAL
        ganancia_neta = (total_vendido - total_costo) - total_gastos
        writer.writerow(["--- RESUMEN FINAL ---"])
        writer.writerow(["Ganancia Bruta (Ventas - Costos)", total_vendido - total_costo])
        writer.writerow(["Total Gastos Varios", total_gastos])
        writer.writerow(["GANANCIA NETA", ganancia_neta])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'Reporte_Ventas_{fecha_inicio}_al_{fecha_fin}.csv'
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@reporte_bp.route("/api/exportar/inventario", methods=["GET"])
@login_required
def exportar_inventario():
    try:
        query = text("""
            SELECT p.codigo, p.nombre, p.precio_compra, p.precio_venta, i.stock_actual, i.stock_minimo
            FROM productos p
            JOIN inventario i ON p.id_producto = i.id_producto
            WHERE p.id_empresa = :empresa AND p.estado = 'activo'
            ORDER BY p.nombre ASC
        """)
        productos = db.session.execute(query, {"empresa": current_user.id_empresa}).fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        writer.writerow(["Codigo", "Producto", "Costo U. (C$)", "Precio U. (C$)", "Stock Actual", "Stock Minimo", "Valor Total Costo (C$)"])
        total_valor_inventario = 0
        for p in productos:
            valor_total = float(p.precio_compra or 0) * float(p.stock_actual or 0)
            writer.writerow([p.codigo, p.nombre, float(p.precio_compra or 0), float(p.precio_venta or 0), float(p.stock_actual or 0), float(p.stock_minimo or 0), valor_total])
            total_valor_inventario += valor_total
            
        writer.writerow([])
        writer.writerow(["TOTAL VALOR EN INVENTARIO", "", "", "", "", "", total_valor_inventario])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'Reporte_Inventario_{nicaragua_now().strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
