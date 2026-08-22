document.addEventListener('DOMContentLoaded', () => {
    cargarChartsDashboard();

    const aplicarFiltroDashboard = () => {
        const inicio = document.getElementById('filterDesde').value;
        const fin = document.getElementById('filterHasta').value;
        if (inicio && fin) {
            cargarChartsDashboard(inicio, fin);
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
        });
    }
});

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
