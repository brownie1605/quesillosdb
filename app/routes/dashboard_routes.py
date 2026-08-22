from flask import Blueprint, render_template
from flask_login import login_required
from app.extensions import db
from app.models import Venta, Producto, DetalleVenta, Inventario, Compra
from datetime import timedelta
from sqlalchemy import func, text
from app.utils.date_utils import nicaragua_now

from app.utils.decorators import require_roles

dashboard_bp = Blueprint("dashboard", __name__)

from flask import redirect, url_for
from flask_login import current_user

@dashboard_bp.before_request
def check_roles():
    if current_user.is_authenticated and current_user.rol:
        if current_user.rol.nombre == 'Cajero':
            return redirect(url_for('venta.historial'))
        elif current_user.rol.nombre == 'Inventario':
            return redirect(url_for('producto.lista'))
            
    return require_roles('Administrador')



@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    today = nicaragua_now().date()
    first_day_of_month = today.replace(day=1)
    
    # Ventas del día
    ventas_hoy = float(db.session.query(func.sum(Venta.total)).filter(
        Venta.id_empresa == current_user.id_empresa,
        func.date(Venta.fecha_venta) == today,
        Venta.estado == 'completada'
    ).scalar() or 0.0)

    # Ventas del mes
    ventas_mes = float(db.session.query(func.sum(Venta.total)).filter(
        Venta.id_empresa == current_user.id_empresa,
        func.date(Venta.fecha_venta) >= first_day_of_month,
        Venta.estado == 'completada'
    ).scalar() or 0.0)

    # Gastos del mes (compras)
    gastos_mes = float(db.session.query(func.sum(Compra.total)).filter(
        Compra.id_empresa == current_user.id_empresa,
        func.date(Compra.fecha_compra) >= first_day_of_month,
        Compra.estado == 'completada'
    ).scalar() or 0.0)

    # Total de productos activos
    total_productos = Producto.query.filter_by(estado='activo', id_empresa=current_user.id_empresa).count()
    
    # Productos con bajo stock
    bajo_stock = db.session.query(Producto, Inventario).join(Inventario).filter(
        Producto.id_empresa == current_user.id_empresa,
        Inventario.stock_actual <= Inventario.stock_minimo,
        Producto.estado == 'activo'
    ).limit(5).all()
    
    # Productos más vendidos (Top 4)
    mas_vendidos_query = db.session.query(
        Producto.nombre,
        func.sum(DetalleVenta.cantidad).label('total_vendido')
    ).join(DetalleVenta).join(Venta).filter(
        Venta.id_empresa == current_user.id_empresa,
        Venta.estado == 'completada'
    ).group_by(Producto.id_producto).order_by(db.desc('total_vendido')).limit(4).all()

    return render_template(
        "dashboard/dashboard.html",
        ventas_hoy=ventas_hoy,
        ventas_mes=ventas_mes,
        gastos_mes=gastos_mes,
        total_productos=total_productos,
        bajo_stock=bajo_stock,
        mas_vendidos=mas_vendidos_query
    )

@dashboard_bp.route("/api/dashboard_charts")
@login_required
def api_dashboard_charts():
    from flask import request
    from datetime import datetime
    
    inicio = request.args.get('inicio')
    fin = request.args.get('fin')
    
    hoy = nicaragua_now().date()
    
    params_7d = {"empresa": current_user.id_empresa}
    
    if inicio and fin:
        start_date = datetime.strptime(inicio, "%Y-%m-%d").date()
        end_date = datetime.strptime(fin, "%Y-%m-%d").date()
        
        # Limitar la diferencia a 31 días máximo para evitar gráficos enormes
        dias_diff = (end_date - start_date).days
        if dias_diff > 31:
            end_date = start_date + timedelta(days=31)
            dias_diff = 31
            
        rango_dias = [start_date + timedelta(days=i) for i in range(dias_diff + 1)]
        params_7d["start_date"] = start_date
        params_7d["end_date"] = end_date
        filtro_fecha_tendencia = "AND DATE(fecha_venta) >= :start_date AND DATE(fecha_venta) <= :end_date"
    else:
        start_date = hoy - timedelta(days=6)
        rango_dias = [hoy - timedelta(days=i) for i in range(6, -1, -1)]
        params_7d["start_date"] = start_date
        filtro_fecha_tendencia = "AND DATE(fecha_venta) >= :start_date"
    
    query_7d = text(f"""
        SELECT DATE(fecha_venta) as fecha, SUM(total) as total_ventas 
        FROM ventas 
        WHERE id_empresa = :empresa AND estado = 'completada' 
        {filtro_fecha_tendencia}
        GROUP BY DATE(fecha_venta)
        ORDER BY fecha ASC
    """)
    res_7d = db.session.execute(query_7d, params_7d).fetchall()
    
    # Mapear ventas reales por fecha
    ventas_dict = {str(row[0]): float(row[1] or 0) for row in res_7d}
    
    ventas_7d = []
    for dia in rango_dias:
        str_dia = str(dia)
        ventas_7d.append({
            "fecha": dia.strftime("%d/%m"),
            "total": ventas_dict.get(str_dia, 0.0)
        })
    
    # 2. Top 5 Productos (Donut Chart)
    filtro_fecha_prod = ""
    params_prod = {"empresa": current_user.id_empresa}
    if inicio and fin:
        filtro_fecha_prod = "AND DATE(v.fecha_venta) >= :inicio AND DATE(v.fecha_venta) <= :fin"
        params_prod["inicio"] = start_date
        params_prod["fin"] = end_date
        
    query_prod = text(f"""
        SELECT p.nombre, sum(dv.subtotal) as total
        FROM detalle_ventas dv
        JOIN productos p ON dv.id_producto = p.id_producto
        JOIN ventas v ON dv.id_venta = v.id_venta
        WHERE v.id_empresa = :empresa AND v.estado = 'completada'
        {filtro_fecha_prod}
        GROUP BY p.nombre
        ORDER BY total DESC
        LIMIT 5
    """)
    res_prod = db.session.execute(query_prod, params_prod).fetchall()
    
    top_productos = []
    for row in res_prod:
        top_productos.append({
            "producto": row[0],
            "total": float(row[1] or 0)
        })
        
    if not top_productos:
        top_productos.append({"producto": "Sin ventas", "total": 0})
        
    return {"ventas_7d": ventas_7d, "top_productos": top_productos}