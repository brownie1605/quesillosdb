document.addEventListener('DOMContentLoaded', () => {
    cargarReportes();
});

async function cargarReportes(inicio = '', fin = '') {
    try {
        let qs = '';
        if (inicio && fin) {
            qs = `?inicio=${inicio}&fin=${fin}`;
        }
        
        const [ventasRes, prodRes, stockRes] = await Promise.all([
            fetch('/reportes/api/resumen_ventas' + qs),
            fetch('/reportes/api/productos_top' + qs),
            fetch('/reportes/api/stock_bajo') // Stock no depende de fechas, es actual
        ]);
        
        const ventasData = await ventasRes.json();
        const prodData = await prodRes.json();
        const stockData = await stockRes.json();

        if (ventasData.success) {
            if (window.ventasChartInst) window.ventasChartInst.destroy();
            renderVentasChart(ventasData.data);
        }
        if (prodData.success) {
            if (window.productosChartInst) window.productosChartInst.destroy();
            renderProductosChart(prodData.data);
        }
        if (stockData.success) renderStockBajoTable(stockData.data);
        
    } catch (error) {
        console.error("Error al cargar reportes:", error);
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
