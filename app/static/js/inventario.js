let inventarioList = [];
const pagInventario = crearPaginador('paginacionInventario', 20);

document.addEventListener('DOMContentLoaded', () => {
    cargarInventario();

    const reiniciarYRenderizar = () => { pagInventario.reset(); renderizarTabla(); };
    document.getElementById('searchInput').addEventListener('input', reiniciarYRenderizar);
    document.getElementById('stockFilter').addEventListener('change', reiniciarYRenderizar);
    document.getElementById('btnExportarExcel').addEventListener('click', exportarExcel);
});

async function cargarInventario() {
    try {
        const res = await fetch('/inventario/api/list');
        inventarioList = await res.json();
        renderizarTabla();
    } catch (error) {
        console.error("Error al cargar inventario", error);
    }
}

function renderizarTabla() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    const stockFilter = document.getElementById('stockFilter').value;
    const tbody = document.querySelector('#tablaInventario tbody');
    tbody.innerHTML = '';

    const filtrados = inventarioList.filter(p => {

        if (stockFilter === 'out' && p.stock_actual > 0) return false;
        if (stockFilter === 'low' && (p.stock_actual <= 0 || p.stock_actual > p.stock_minimo)) return false;
        if (stockFilter === 'normal' && p.stock_actual <= p.stock_minimo) return false;

        const q = query;
        return (p.nombre && p.nombre.toLowerCase().includes(q)) ||
               (p.codigo && p.codigo.toLowerCase().includes(q));
    });

    // El total del KPI y el filtro de stock deben reflejar TODO lo filtrado,
    // no solo la pagina visible -- por eso se calcula antes de paginar.
    let totalUnidades = 0;
    filtrados.forEach(p => { totalUnidades += parseFloat(p.stock_actual); });
    const kpi = document.getElementById('kpiTotalInventario');
    if (kpi) kpi.textContent = totalUnidades;

    pagInventario.paginar(filtrados, renderizarTabla).forEach(p => {
        let estado = 'Óptimo';
        let badgeClass = 'badge-active';

        if (p.stock_actual <= 0) {
            estado = 'Agotado';
            badgeClass = 'badge-inactive';
        } else if (p.stock_actual <= p.stock_minimo) {
            estado = 'Bajo';
            badgeClass = 'badge-warning';
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(p.codigo) || 'N/A'}</td>
            <td><strong>${escapeHtml(p.nombre)}</strong></td>
            <td>${p.stock_actual}</td>
            <td>${p.stock_minimo}</td>
            <td><span class="badge ${badgeClass}">${estado}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function exportarExcel() {
    const ws = XLSX.utils.json_to_sheet(inventarioList.map(p => ({
        "Código": p.codigo,
        "Producto": p.nombre,
        "Stock Actual": p.stock_actual,
        "Stock Mínimo": p.stock_minimo,
        "Estado": p.stock_actual <= 0 ? "Agotado" : (p.stock_actual <= p.stock_minimo ? "Bajo" : "Óptimo")
    })));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Inventario");
    XLSX.writeFile(wb, "Inventario.xlsx");
}

// El inventario ya no se ajusta manualmente desde aqui -- toda entrada de
// stock nuevo debe pasar por Compras, para que el costo quede ligado a lo
// que de verdad se pago. Las bajas por rotura/merma se seguiran viendo en
// el Historial de movimientos (kardex).
