document.addEventListener('DOMContentLoaded', () => {
    cargarAuditoria();

    const reiniciarYFiltrar = () => { pagAuditoria.reset(); filtrarTabla(); };
    document.getElementById('searchInput').addEventListener('input', reiniciarYFiltrar);
    document.getElementById('moduloFilter').addEventListener('change', reiniciarYFiltrar);
});

let auditoriasGlobal = [];
let auditoriasFiltradasGlobal = [];
const pagAuditoria = crearPaginador('paginacionAuditoria', 25);

async function cargarAuditoria() {
    try {
        const res = await fetch('/api/auditoria');
        if (!res.ok) throw new Error('Error al obtener datos');
        
        auditoriasGlobal = await res.json();
        renderTabla(auditoriasGlobal);
    } catch (e) {
        console.error(e);
        if (window.showCustomAlert) {
            window.showCustomAlert("Error al cargar auditoría", true);
        } else {
            alert("Error al cargar auditoría");
        }
    }
}

function renderTabla(datos) {
    auditoriasFiltradasGlobal = datos;
    const tbody = document.querySelector('#tablaAuditoria tbody');
    tbody.innerHTML = '';

    if (datos.length === 0) {
        document.getElementById('paginacionAuditoria').innerHTML = '';
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No se encontraron registros.</td></tr>';
        return;
    }

    const pagina = pagAuditoria.paginar(datos, () => renderTabla(auditoriasFiltradasGlobal));
    pagina.forEach(row => {
        const tr = document.createElement('tr');
        
        // Formatear detalles para vista previa
        let detallesBtn = '';
        if (row.detalles) {
            detallesBtn = `<button class="btn btn-sm btn-info" onclick='mostrarDetalles(${JSON.stringify(row.detalles).replace(/'/g, "&#39;")})'>Ver</button>`;
        } else {
            detallesBtn = '<span style="color: #999;">N/A</span>';
        }

        tr.innerHTML = `
            <td>${row.fecha}</td>
            <td><strong>${escapeHtml(row.nombre_usuario)}</strong></td>
            <td><span class="badge" style="background: #e0e0e0; color: #333; padding: 3px 8px; border-radius: 4px;">${escapeHtml(row.modulo)}</span></td>
            <td>${escapeHtml(row.accion)}</td>
            <td>${escapeHtml(row.ip_address) || 'N/A'}</td>
            <td>${detallesBtn}</td>
        `;
        tbody.appendChild(tr);
    });
}

function filtrarTabla() {
    const q = document.getElementById('searchInput').value.toLowerCase();
    const modulo = document.getElementById('moduloFilter').value;
    
    const filtrados = auditoriasGlobal.filter(row => {
        const matchQ = row.nombre_usuario.toLowerCase().includes(q) || row.accion.toLowerCase().includes(q);
        const matchM = modulo === "" || row.modulo === modulo;
        return matchQ && matchM;
    });
    
    renderTabla(filtrados);
}

window.mostrarDetalles = function(detallesStr) {
    const modal = document.getElementById('modalAuditoria');
    const content = document.getElementById('auditoriaDetallesContent');
    
    try {
        // Intentar parsear como JSON para formatear bonito
        const parsed = JSON.parse(detallesStr);
        let html = '<ul style="list-style: none; padding: 0; margin: 0; font-size: 14px;">';
        for (const [key, value] of Object.entries(parsed)) {
            html += `<li style="margin-bottom: 8px;"><strong style="text-transform: capitalize;">${key.replace('_', ' ')}:</strong> ${value}</li>`;
        }
        html += '</ul>';
        content.innerHTML = html;
    } catch(e) {
        // Si no es JSON, mostrar como texto normal
        content.innerHTML = detallesStr;
    }
    
    modal.style.display = 'flex';
}
