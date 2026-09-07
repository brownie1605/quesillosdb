let movimientosList = [];

const TIPO_LABEL = {
    entrada: 'Entrada manual',
    compra: 'Compra',
    ajuste: 'Ajuste',
    venta: 'Venta',
    receta: 'Consumo de receta',
    devolucion: 'Devolución',
    salida: 'Salida',
};

const TIPO_CLASE = {
    entrada: 'badge-active',
    compra: 'badge-active',
    ajuste: 'badge-warning',
    venta: 'badge-inactive',
    receta: 'badge-inactive',
    devolucion: 'badge-warning',
    salida: 'badge-inactive',
};

const pagMovimientos = crearPaginador('paginacionMovimientos', 25);

document.addEventListener('DOMContentLoaded', () => {
    cargarMovimientos();
    document.getElementById('searchInput').addEventListener('input', () => { pagMovimientos.reset(); renderizarTabla(); });
    document.getElementById('tipoFilter').addEventListener('change', () => { pagMovimientos.reset(); cargarMovimientos(); });
});

async function cargarMovimientos() {
    const tbody = document.querySelector('#tablaMovimientos tbody');
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Cargando…</td></tr>';
    try {
        const tipo = document.getElementById('tipoFilter').value;
        const params = tipo ? `?tipo=${encodeURIComponent(tipo)}` : '';
        const res = await fetch(`/inventario/api/movimientos${params}`);
        movimientosList = await res.json();
        renderizarTabla();
    } catch (error) {
        console.error('Error al cargar movimientos', error);
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">No se pudo cargar el historial.</td></tr>';
    }
}

function renderizarTabla() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    const tbody = document.querySelector('#tablaMovimientos tbody');

    const filtrados = movimientosList.filter(m =>
        !query || (m.producto && m.producto.toLowerCase().includes(query))
    );

    if (!filtrados.length) {
        document.getElementById('paginacionMovimientos').innerHTML = '';
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Sin movimientos registrados.</td></tr>';
        return;
    }

    tbody.innerHTML = pagMovimientos.paginar(filtrados, renderizarTabla).map(m => {
        const signo = m.stock_nuevo >= m.stock_anterior ? '+' : '−';
        const tipoLabel = TIPO_LABEL[m.tipo_movimiento] || m.tipo_movimiento;
        const tipoClase = TIPO_CLASE[m.tipo_movimiento] || 'badge-active';
        return `
            <tr>
                <td>${m.fecha_movimiento || '—'}</td>
                <td><strong>${escapeHtml(m.producto) || 'Producto eliminado'}</strong></td>
                <td><span class="badge ${tipoClase}">${tipoLabel}</span></td>
                <td>${signo}${m.cantidad}</td>
                <td>${m.stock_anterior} → ${m.stock_nuevo}</td>
                <td style="font-size:12.5px;">${escapeHtml(m.observacion) || ''}${m.referencia ? `<br><small style="opacity:.7">${escapeHtml(m.referencia)}</small>` : ''}</td>
                <td>${escapeHtml(m.usuario) || '—'}</td>
            </tr>`;
    }).join('');
}
