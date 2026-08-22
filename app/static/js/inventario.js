let inventarioList = [];

document.addEventListener('DOMContentLoaded', () => {
    cargarInventario();

    document.getElementById('searchInput').addEventListener('input', renderizarTabla);
    document.getElementById('stockFilter').addEventListener('change', renderizarTabla);
    document.getElementById('btnExportarExcel').addEventListener('click', exportarExcel);

    document.getElementById('btnCerrarModalStock').addEventListener('click', () => {
        document.getElementById('modalStock').style.display = 'none';
    });

    document.getElementById('formStock').addEventListener('submit', guardarAjusteStock);
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

    let totalUnidades = 0;

    filtrados.forEach(p => {
        totalUnidades += parseFloat(p.stock_actual);
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
            <td>${p.codigo || 'N/A'}</td>
            <td><strong>${p.nombre}</strong></td>
            <td>${p.stock_actual}</td>
            <td>${p.stock_minimo}</td>
            <td><span class="badge ${badgeClass}">${estado}</span></td>
            <td>
                <button class="btn-icon" title="Entrada / Ajuste" onclick="abrirModalStock(${p.id_producto}, '${p.nombre}', ${p.stock_actual}, ${p.stock_minimo})">📦</button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    const kpi = document.getElementById('kpiTotalInventario');
    if (kpi) kpi.textContent = totalUnidades;
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

function abrirModalStock(id_prod, nombre, actual, minimo) {
    const p = inventarioList.find(x => x.id_producto === id_prod);
    if (!p) return;

    document.getElementById('inv_producto_id').value = p.id_producto;
    document.getElementById('inv_nombre_producto').value = p.nombre;
    document.getElementById('inv_stock_actual').value = p.stock_actual.toFixed(2);
    document.getElementById('inv_stock_minimo').value = p.stock_minimo.toFixed(2);
    
    document.getElementById('modalStock').style.display = 'flex';
}

async function guardarAjusteStock(e) {
    e.preventDefault();
    const id = document.getElementById('inv_producto_id').value;

    const payload = {
        stock_actual: document.getElementById('inv_stock_actual').value,
        stock_minimo: document.getElementById('inv_stock_minimo').value
    };

    try {
        const res = await fetch(`/inventario/api/editar_stock/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.success) {
            document.getElementById('modalStock').style.display = 'none';
            cargarInventario();
        } else {
            showCustomAlert('Error: ' + result.message);
        }
    } catch (error) {
        console.error(error);
        showCustomAlert('Error en el servidor');
    }
}
