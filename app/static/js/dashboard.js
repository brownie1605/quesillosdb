document.addEventListener('DOMContentLoaded', () => {
    cargarChartsDashboard();
    cargarResumenFinanciero();

    const aplicarFiltroDashboard = () => {
        const inicio = document.getElementById('filterDesde').value;
        const fin = document.getElementById('filterHasta').value;
        if (inicio && fin) {
            cargarChartsDashboard(inicio, fin);
            cargarResumenFinanciero(inicio, fin);
        }
    };

    const inputDesde = document.getElementById('filterDesde');
    const inputHasta = document.getElementById('filterHasta');
    if (inputDesde) inputDesde.addEventListener('change', aplicarFiltroDashboard);
    if (inputHasta) inputHasta.addEventListener('change', aplicarFiltroDashboard);
    const btnQuitarFiltro = document.getElementById('btnQuitarFiltroDashboard');
    if (btnQuitarFiltro) {
        btnQuitarFiltro.addEventListener('click', () => {
            document.getElementById('filterDesde').value = '';
            document.getElementById('filterHasta').value = '';
            cargarChartsDashboard(); // Carga por defecto (últimos 7 días)
            cargarResumenFinanciero();
        });
    }
});

function _moneyFmt(n) {
    return 'C$ ' + (n || 0).toLocaleString('es-NI', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function cargarResumenFinanciero(inicio = '', fin = '') {
    try {
        let url = '/reportes/api/resumen_financiero';
        if (inicio && fin) url += `?inicio=${inicio}&fin=${fin}`;
        const res = await fetch(url);
        const data = await res.json();
        if (!data.success) return;

        document.getElementById('fVentas').textContent = _moneyFmt(data.total_vendido);
        document.getElementById('fCantVentas').textContent = `${data.cantidad_ventas} venta${data.cantidad_ventas === 1 ? '' : 's'}`;
        document.getElementById('fTicket').textContent = _moneyFmt(data.ticket_promedio);
        document.getElementById('fCosto').textContent = _moneyFmt(data.costo_productos);
        document.getElementById('fBruta').textContent = _moneyFmt(data.ganancia_bruta);
        document.getElementById('fGastos').textContent = _moneyFmt(data.gastos_varios);
        document.getElementById('fNeta').textContent = _moneyFmt(data.ganancia_neta);
        document.getElementById('fMargen').textContent = `${(data.margen_pct || 0).toFixed(1)}% margen`;

        const rangoLabel = document.getElementById('rangoFinancieroLabel');
        if (rangoLabel && data.inicio && data.fin) {
            rangoLabel.textContent = `(${data.inicio} al ${data.fin})`;
        }
    } catch (error) {
        console.error("Error al cargar resumen financiero:", error);
    }

    // Propinas del mismo rango: efectivo vs tarjeta.
    try {
        let urlProp = '/reportes/api/propinas';
        if (inicio && fin) urlProp += `?inicio=${inicio}&fin=${fin}`;
        const resProp = await fetch(urlProp);
        const dataProp = await resProp.json();
        if (dataProp.success) {
            const fPropinas = document.getElementById('fPropinas');
            const fPropinasDetalle = document.getElementById('fPropinasDetalle');
            if (fPropinas) fPropinas.textContent = _moneyFmt(dataProp.total_propinas);
            if (fPropinasDetalle) {
                fPropinasDetalle.textContent = (dataProp.por_metodo || []).length
                    ? dataProp.por_metodo.map(m => `${m.metodo}: ${_moneyFmt(m.total)}`).join(' · ')
                    : 'No cuenta como ganancia';
            }
        }
    } catch (error) {
        console.error("Error al cargar propinas:", error);
    }

    // Top productos (cantidad + ingresos), mismo rango
    try {
        let urlTop = '/reportes/api/productos_top';
        if (inicio && fin) urlTop += `?inicio=${inicio}&fin=${fin}`;
        const resTop = await fetch(urlTop);
        const dataTop = await resTop.json();
        const tbody = document.getElementById('tbodyTopProductos');
        if (!tbody) return;
        if (!dataTop.success || !dataTop.data || !dataTop.data.length) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align: center;">Sin ventas aún</td></tr>';
            return;
        }
        tbody.innerHTML = dataTop.data.map((p, i) => `
            <tr>
                <td>${i + 1}. ${p.producto}</td>
                <td>${p.cantidad}</td>
                <td>${_moneyFmt(p.ingresos)}</td>
            </tr>`).join('');
    } catch (error) {
        console.error("Error al cargar top productos:", error);
    }
}

let ventasChartInstancia = null;
let productosDonutInstancia = null;

async function cargarChartsDashboard(inicio = '', fin = '') {
    try {
        let url = '/api/dashboard_charts';
        if (inicio && fin) {
            url += `?inicio=${inicio}&fin=${fin}`;
        }
        
        const res = await fetch(url);
        const data = await res.json();
        
        if (data.ventas_7d) renderVentasDashboardChart(data.ventas_7d);
        if (data.top_productos) renderProductosDonutChart(data.top_productos);
    } catch (error) {
        console.error("Error al cargar charts del dashboard:", error);
    }
}

function renderVentasDashboardChart(data) {
    const ctx = document.getElementById('ventasDashboardChart').getContext('2d');
    const labels = data.map(d => d.fecha);
    const totales = data.map(d => d.total);

    if (ventasChartInstancia) {
        ventasChartInstancia.destroy();
    }

    ventasChartInstancia = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Tendencia de Ventas (C$)',
                data: totales,
                backgroundColor: '#0b5cff',
                borderRadius: 4
            }]
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

function renderProductosDonutChart(data) {
    const ctx = document.getElementById('productosDonutChart').getContext('2d');
    const labels = data.map(d => d.producto);
    const totales = data.map(d => d.total);
    const coloresBase = ['#0b5cff', '#16b978', '#ffb703', '#ef476f', '#9b59b6'];

    if (productosDonutInstancia) {
        productosDonutInstancia.destroy();
    }

    productosDonutInstancia = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: totales,
                backgroundColor: coloresBase,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (event, elements, chart) => {
                if (elements.length > 0) {
                    const index = elements[0].index;
                    
                    // Resaltar seleccionado y volver los demas opacos
                    const nuevosColores = coloresBase.map((color, i) => {
                        return i === index ? color : color + '40'; // 40 es la opacidad en hex (~25%)
                    });
                    
                    chart.data.datasets[0].backgroundColor = nuevosColores;
                    chart.update();
                } else {
                    // Restaurar colores al dar clic fuera
                    chart.data.datasets[0].backgroundColor = coloresBase;
                    chart.update();
                }
            }
        }
    });
}
