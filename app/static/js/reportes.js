document.addEventListener('DOMContentLoaded', () => {
    cargarReportes();
});

function _moneyFmt(valor) {
    return 'C$ ' + (parseFloat(valor) || 0).toLocaleString('es-NI', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function cargarReportes(inicio = '', fin = '') {
    try {
        let qs = '';
        if (inicio && fin) {
            qs = `?inicio=${inicio}&fin=${fin}`;
        }

        const [ventasRes, prodRes, stockRes, finRes, propRes] = await Promise.all([
            fetch('/reportes/api/resumen_ventas' + qs),
            fetch('/reportes/api/productos_top' + qs),
            fetch('/reportes/api/stock_bajo'), // Stock no depende de fechas, es actual
            fetch('/reportes/api/resumen_financiero' + qs),
            fetch('/reportes/api/propinas' + qs),
        ]);

        const ventasData = await ventasRes.json();
        const prodData = await prodRes.json();
        const stockData = await stockRes.json();
        const finData = await finRes.json();
        const propData = await propRes.json();

        if (ventasData.success) {
            if (window.ventasChartInst) window.ventasChartInst.destroy();
            renderVentasChart(ventasData.data);
        }
        if (prodData.success) {
            if (window.productosChartInst) window.productosChartInst.destroy();
            renderProductosChart(prodData.data);
        }
        if (stockData.success) renderStockBajoTable(stockData.data);
        if (finData.success) renderKpisFinancieros(finData);
        if (propData.success) {
            if (window.propinasChartInst) window.propinasChartInst.destroy();
            renderPropinas(propData);
        }

    } catch (error) {
        console.error("Error al cargar reportes:", error);
    }
}

function renderKpisFinancieros(data) {
    document.getElementById('rangoKpiLabel').textContent = `Del ${data.inicio} al ${data.fin}`;

    document.getElementById('kpiVentas').textContent = _moneyFmt(data.total_vendido);
    document.getElementById('kpiCantVentas').textContent = `${data.cantidad_ventas} venta${data.cantidad_ventas === 1 ? '' : 's'}`;

    document.getElementById('kpiGanancia').textContent = _moneyFmt(data.ganancia_neta);
    document.getElementById('kpiMargen').textContent = `${(data.margen_pct || 0).toFixed(1)}% margen`;

    document.getElementById('kpiProductos').textContent = (data.total_productos_vendidos || 0).toLocaleString('es-NI');
    document.getElementById('kpiTicket').textContent = `Ticket prom. ${_moneyFmt(data.ticket_promedio)}`;

    document.getElementById('kpiBruta').textContent = _moneyFmt(data.ganancia_bruta);
    document.getElementById('kpiCosto').textContent = _moneyFmt(data.costo_productos);
    document.getElementById('kpiGastos').textContent = _moneyFmt(data.gastos_varios);
    document.getElementById('kpiPropinas').textContent = _moneyFmt(data.total_propinas);

    if (data.mesa_top) {
        document.getElementById('kpiMesa').textContent = data.mesa_top.nombre;
        document.getElementById('kpiMesaDetalle').textContent = `${_moneyFmt(data.mesa_top.total)} · ${data.mesa_top.ventas} venta${data.mesa_top.ventas === 1 ? '' : 's'}`;
    } else {
        document.getElementById('kpiMesa').textContent = '—';
        document.getElementById('kpiMesaDetalle').textContent = 'Sin ventas por mesa en el rango';
    }

    if (data.producto_top) {
        document.getElementById('kpiProductoPopular').textContent = data.producto_top.nombre;
        document.getElementById('kpiProductoPopularDetalle').textContent = `${data.producto_top.cantidad} unidades · ${_moneyFmt(data.producto_top.ingresos)}`;
    } else {
        document.getElementById('kpiProductoPopular').textContent = '—';
        document.getElementById('kpiProductoPopularDetalle').textContent = 'Sin ventas en el rango';
    }
}

window.aplicarFiltroReportes = function() {
    const inicio = document.getElementById('exportFechaInicio').value;
    const fin = document.getElementById('exportFechaFin').value;
    if(!inicio || !fin) {
        if(typeof showCustomAlert !== 'undefined') showCustomAlert("Seleccione ambas fechas");
        else alert("Seleccione ambas fechas");
        return;
    }
    cargarReportes(inicio, fin);
};

window.quitarFiltroReportes = function() {
    const hoy = new Date();
    const inicioDate = new Date();
    inicioDate.setDate(hoy.getDate() - 6);
    
    const formatoFecha = (fecha) => {
        const yyyy = fecha.getFullYear();
        const mm = String(fecha.getMonth() + 1).padStart(2, '0');
        const dd = String(fecha.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    };
    
    document.getElementById('exportFechaInicio').value = formatoFecha(inicioDate);
    document.getElementById('exportFechaFin').value = formatoFecha(hoy);
    
    cargarReportes(); // Sin parámetros carga default (últimos 7 días / histórico)
};

function renderVentasChart(data) {
    const ctx = document.getElementById('ventasChart').getContext('2d');
    
    const labels = data.map(d => d.fecha);
    const totales = data.map(d => d.total);
    const ganancias = data.map(d => d.ganancia);
    const gastos = data.map(d => d.gastos || 0);

    window.ventasChartInst = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Total Ventas (C$)',
                    data: totales,
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'Ganancia Estimada (C$)',
                    data: ganancias,
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3
                },
                {
                    label: 'Gastos (Compras C$)',
                    data: gastos,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

function renderProductosChart(data) {
    const ctx = document.getElementById('productosChart').getContext('2d');
    
    const labels = data.map(d => d.producto);
    const cantidades = data.map(d => d.cantidad);

    window.productosChartInst = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: cantidades,
                backgroundColor: [
                    '#3498db', '#e74c3c', '#f1c40f', '#2ecc71', '#9b59b6'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
}

function renderPropinas(data) {
    const colorPorMetodo = { 'Efectivo': '#2ecc71', 'Tarjeta': '#3498db', 'Otro': '#95a5a6' };
    const porMetodo = data.por_metodo || [];

    document.getElementById('kpiPropinasDetalle').textContent = porMetodo.length
        ? porMetodo.map(m => `${m.metodo}: ${_moneyFmt(m.total)}`).join(' · ')
        : 'No cuenta como ganancia del negocio';

    const ctx = document.getElementById('propinasChart').getContext('2d');
    window.propinasChartInst = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: porMetodo.length ? porMetodo.map(m => m.metodo) : ['Sin propinas'],
            datasets: [{
                data: porMetodo.length ? porMetodo.map(m => m.total) : [1],
                backgroundColor: porMetodo.length ? porMetodo.map(m => colorPorMetodo[m.metodo] || '#95a5a6') : ['#e1e7f0'],
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { tooltip: { callbacks: { label: (c) => ` ${c.label}: ${_moneyFmt(c.raw)}` } } }
        }
    });

    const tbody = document.getElementById('tbodyPropinas');
    const lista = data.lista || [];
    if (!lista.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 14px; opacity:.6;">Sin propinas en el rango.</td></tr>';
        return;
    }
    tbody.innerHTML = lista.map(v => `
        <tr>
            <td style="padding: 6px 8px; border-bottom: 1px solid #f4f4f4;">#${escapeHtml(v.numero_venta)}</td>
            <td style="padding: 6px 8px; border-bottom: 1px solid #f4f4f4;">${escapeHtml(v.fecha)}</td>
            <td style="padding: 6px 8px; border-bottom: 1px solid #f4f4f4;">${escapeHtml(v.mesero) || '-'}</td>
            <td style="padding: 6px 8px; border-bottom: 1px solid #f4f4f4;">${escapeHtml(v.mesa) || '-'}</td>
            <td style="padding: 6px 8px; border-bottom: 1px solid #f4f4f4;">${escapeHtml(v.metodo_pago)}</td>
            <td style="padding: 6px 8px; border-bottom: 1px solid #f4f4f4; text-align:right;">${_moneyFmt(v.propina)}</td>
        </tr>`).join('');
}

function renderStockBajoTable(data) {
    const tbody = document.querySelector('#tablaStockBajo tbody');
    if(!tbody) return;
    tbody.innerHTML = '';
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 15px;">Todos los productos tienen un stock adecuado.</td></tr>';
        return;
    }
    
    data.forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.producto}</td>
            <td style="text-align: center; padding: 8px; border-bottom: 1px solid #eee; color: #e74c3c; font-weight: bold;">${item.stock_actual}</td>
            <td style="text-align: center; padding: 8px; border-bottom: 1px solid #eee; color: #7f8c8d;">${item.stock_minimo}</td>
        `;
        tbody.appendChild(tr);
    });
}
