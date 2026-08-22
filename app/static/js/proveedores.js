let proveedoresList = [];

document.addEventListener('DOMContentLoaded', () => {
    cargarProveedores();

    document.getElementById('searchInput').addEventListener('input', renderizarTabla);

    document.getElementById('btnNuevoProveedor').addEventListener('click', () => {
        document.getElementById('modalProveedorTitle').textContent = 'Nuevo Proveedor';
        document.getElementById('formProveedor').reset();
        document.getElementById('prov_id').value = '';
        document.getElementById('modalProveedor').style.display = 'flex';
    });

    document.getElementById('btnCerrarModalProveedor').addEventListener('click', () => {
        document.getElementById('modalProveedor').style.display = 'none';
    });

    document.getElementById('formProveedor').addEventListener('submit', guardarProveedor);
});

async function cargarProveedores() {
    try {
        const res = await fetch('/proveedores/api/list');
        proveedoresList = await res.json();
        renderizarTabla();
    } catch (error) {
        console.error("Error al cargar proveedores", error);
    }
}

function renderizarTabla() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    const tbody = document.querySelector('#tablaProveedores tbody');
    tbody.innerHTML = '';

    const filtrados = proveedoresList.filter(p => {
        if (p.estado !== 'activo') return false;
        const q = query;
        return (p.nombre && p.nombre.toLowerCase().includes(q)) ||
               (p.ruc && p.ruc.toLowerCase().includes(q)) ||
               (p.telefono && p.telefono.toLowerCase().includes(q));
    });

    filtrados.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${p.nombre}</td>
            <td>${p.ruc || '-'}</td>
            <td>${p.telefono || '-'}</td>
            <td>${p.correo || '-'}</td>
            <td>${p.direccion || '-'}</td>
            <td><span class="badge badge-active">Activo</span></td>
            <td>
                <button class="btn-icon" onclick="editarProveedor(${p.id_proveedor})">✏️</button>
                <button class="btn-icon delete" onclick="eliminarProveedor(${p.id_proveedor})">🗑️</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function editarProveedor(id) {
    const p = proveedoresList.find(x => x.id_proveedor === id);
    if (!p) return;

    document.getElementById('modalProveedorTitle').textContent = 'Editar Proveedor';
    document.getElementById('prov_id').value = p.id_proveedor;
    document.getElementById('prov_nombre').value = p.nombre || '';
    document.getElementById('prov_ruc').value = p.ruc || '';
    document.getElementById('prov_telefono').value = p.telefono || '';
    document.getElementById('prov_correo').value = p.correo || '';
    document.getElementById('prov_direccion').value = p.direccion || '';

    document.getElementById('modalProveedor').style.display = 'flex';
}

async function guardarProveedor(e) {
    e.preventDefault();
    const id = document.getElementById('prov_id').value;
    const isEdit = id !== '';
    const url = isEdit ? `/proveedores/api/editar/${id}` : '/proveedores/api/crear';
    const method = isEdit ? 'PUT' : 'POST';

    const payload = {
        nombre: document.getElementById('prov_nombre').value,
        ruc: document.getElementById('prov_ruc').value,
        telefono: document.getElementById('prov_telefono').value,
        correo: document.getElementById('prov_correo').value,
        direccion: document.getElementById('prov_direccion').value
    };

    try {
        const res = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.success) {
            document.getElementById('modalProveedor').style.display = 'none';
            cargarProveedores();
        } else {
            showCustomAlert('Error: ' + result.message);
        }
    } catch (error) {
        console.error(error);
        showCustomAlert('Error en el servidor');
    }
}

async function eliminarProveedor(id) {
    showCustomConfirm('¿Está seguro de eliminar este proveedor?', async () => {
        try {
            const res = await fetch(`/proveedores/api/eliminar/${id}`, { method: 'DELETE' });
            const result = await res.json();
            if (result.success) {
                cargarProveedores();
            } else {
                showCustomAlert('Error: ' + result.message);
            }
        } catch (error) {
            console.error(error);
            showCustomAlert('Error en el servidor');
        }
    });
}
