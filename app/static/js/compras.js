let comprasList = [];
let proveedoresList = [];
let productosList = [];
let itemsNuevaCompra = [];
let choiceProveedor = null;
let choiceProducto = null;

document.addEventListener('DOMContentLoaded', () => {
    cargarDatosIniciales();
    
    document.getElementById('searchInput').addEventListener('input', renderizarTablaCompras);
    
    // Modal Nueva Compra
    document.getElementById('btnNuevaCompra').addEventListener('click', abrirModalCompra);
    document.getElementById('btnCerrarModalCompra').addEventListener('click', cerrarModalCompra);
    document.getElementById('btnAgregarItem').addEventListener('click', agregarItem);
    document.getElementById('btnGuardarCompra').addEventListener('click', registrarCompra);
    
    // Modal Detalles
    document.getElementById('btnCerrarDetalles').addEventListener('click', () => {
        document.getElementById('modalDetalles').style.display = 'none';
    });
});

async function cargarDatosIniciales() {
    try {
        const [compRes, provRes, prodRes] = await Promise.all([
            fetch('/compras/api/list'),
            fetch('/proveedores/api/list'),
            fetch('/productos/api/list')
        ]);
        comprasList = await compRes.json();
        proveedoresList = await provRes.json();
        productosList = await prodRes.json();
        
        // Llenar selects
        const selectProv = document.getElementById('compra_proveedor');
        proveedoresList.forEach(p => {
            selectProv.innerHTML += `<option value="${p.id_proveedor}">${p.nombre}</option>`;
        });
        
        selectProv.addEventListener('change', (e) => {
            const selectedText = e.target.options[e.target.selectedIndex]?.text.toLowerCase() || '';
            if (selectedText.includes('varios')) {
                document.getElementById('seccion-productos').style.display = 'none';
                document.getElementById('seccion-gasto-vario').style.display = 'block';
                document.getElementById('compra_total').textContent = parseFloat(document.getElementById('gasto_monto').value || 0).toFixed(2);
            } else {
                document.getElementById('seccion-productos').style.display = 'block';
                document.getElementById('seccion-gasto-vario').style.display = 'none';
                renderizarItemsNuevaCompra();
            }
        });
        
        document.getElementById('gasto_monto').addEventListener('input', (e) => {
            const selProv = document.getElementById('compra_proveedor');
            const txt = selProv.options[selProv.selectedIndex]?.text.toLowerCase() || '';
            if (txt.includes('varios')) {
                document.getElementById('compra_total').textContent = parseFloat(e.target.value || 0).toFixed(2);
            }
        });
        
        if (window.Choices) {
            choiceProveedor = new Choices(selectProv, {
                searchEnabled: true,
                itemSelectText: '',
                noResultsText: 'No se encontraron proveedores',
                noChoicesText: 'No hay opciones',
                placeholderValue: 'Seleccione un Proveedor...'
            });
        }
        
        
        const selectProd = document.getElementById('compra_producto');
        productosList.forEach(p => {
            selectProd.innerHTML += `<option value="${p.id_producto}" data-costo="${p.costo || 0}">${p.nombre}</option>`;
        });
        
        // Autocompletar costo al elegir producto
        selectProd.addEventListener('change', (e) => {
            const opt = e.target.options[e.target.selectedIndex];
            if (opt && opt.value) {
                document.getElementById('compra_costo').value = parseFloat(opt.dataset.costo || 0).toFixed(2);
            }
        });
        
        if (window.Choices) {
            choiceProducto = new Choices(selectProd, {
                searchEnabled: true,
                itemSelectText: '',
                noResultsText: 'No se encontraron productos',
                noChoicesText: 'No hay opciones',
                placeholderValue: 'Seleccione un Producto...'
            });
        }
        
        renderizarTablaCompras();
    } catch (e) {
        console.error("Error al cargar datos", e);
    }
}

function renderizarTablaCompras() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    const tbody = document.querySelector('#tablaCompras tbody');
    tbody.innerHTML = '';

    const filtrados = comprasList.filter(c => 
        (c.numero_compra && c.numero_compra.toLowerCase().includes(query)) ||
        (c.proveedor_nombre && c.proveedor_nombre.toLowerCase().includes(query))
    );

    filtrados.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${c.numero_compra}</strong></td>
            <td>${c.fecha_compra}</td>
            <td>${c.proveedor_nombre}</td>
            <td><strong>C$ ${c.total.toFixed(2)}</strong></td>
            <td><span class="badge badge-active">${c.estado}</span></td>
            <td>
                <button class="btn-icon" title="Ver Detalles" onclick="verDetalles(${c.id_compra})">👁️</button>
                <button class="btn-icon" title="Editar Compra" onclick="abrirModalEditar(${c.id_compra})">✏️</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function abrirModalCompra() {
    itemsNuevaCompra = [];
    document.getElementById('compra_id').value = '';
    document.getElementById('tituloModalCompra').textContent = 'Registrar Nueva Compra';
    document.getElementById('btnGuardarCompra').textContent = 'Registrar Compra';
    
    if (choiceProveedor) choiceProveedor.setChoiceByValue('');
    else document.getElementById('compra_proveedor').value = '';
    
    if (choiceProducto) choiceProducto.setChoiceByValue('');
    else document.getElementById('compra_producto').value = '';
    
    document.getElementById('compra_cantidad').value = '1';
    document.getElementById('compra_costo').value = '0';
    document.getElementById('gasto_descripcion').value = '';
    document.getElementById('gasto_monto').value = '0';
    
    document.getElementById('seccion-productos').style.display = 'block';
    document.getElementById('seccion-gasto-vario').style.display = 'none';
    
    renderizarItemsNuevaCompra();
    document.getElementById('modalNuevaCompra').style.display = 'flex';
}

async function abrirModalEditar(id) {
    itemsNuevaCompra = [];
    document.getElementById('compra_id').value = id;
    document.getElementById('tituloModalCompra').textContent = 'Editar Compra';
    document.getElementById('btnGuardarCompra').textContent = 'Guardar Cambios';

    try {
        const res = await fetch(`/compras/api/detalle/${id}`);
        const r = await res.json();

        if (r.success) {
            const compraObj = comprasList.find(c => c.id_compra === id);
            if (compraObj) {
                if (compraObj.tipo_compra === 'varios') {
                    const provVarios = proveedoresList.find(p => p.nombre.toLowerCase().includes('varios'));
                    if (choiceProveedor) choiceProveedor.setChoiceByValue(provVarios ? provVarios.id_proveedor.toString() : '');
                    else document.getElementById('compra_proveedor').value = provVarios ? provVarios.id_proveedor : '';
                    
                    document.getElementById('gasto_descripcion').value = compraObj.descripcion_gasto || '';
                    document.getElementById('gasto_monto').value = compraObj.total || 0;
                    document.getElementById('seccion-productos').style.display = 'none';
                    document.getElementById('seccion-gasto-vario').style.display = 'block';
                    document.getElementById('compra_total').textContent = parseFloat(compraObj.total || 0).toFixed(2);
                } else {
                    if (choiceProveedor) choiceProveedor.setChoiceByValue(compraObj.id_proveedor ? compraObj.id_proveedor.toString() : '');
                    else document.getElementById('compra_proveedor').value = compraObj.id_proveedor || '';
                    
                    document.getElementById('seccion-productos').style.display = 'block';
                    document.getElementById('seccion-gasto-vario').style.display = 'none';
                }
            }

            itemsNuevaCompra = r.detalles.map(d => ({
                id_producto: d.id_producto,
                nombre: d.producto_nombre,
                cantidad: d.cantidad,
                costo_unitario: d.precio_unitario
            }));

            renderizarItemsNuevaCompra();
            document.getElementById('modalNuevaCompra').style.display = 'flex';
        } else {
            showCustomAlert('Error al cargar la compra: ' + r.message);
        }
    } catch(e) {
        console.error('Error al abrir edición de compra:', e);
        showCustomAlert('Error de servidor');
    }
}

function cerrarModalCompra() {
    document.getElementById('modalNuevaCompra').style.display = 'none';
}

function agregarItem() {
    const id_prod = document.getElementById('compra_producto').value;
    const select = document.getElementById('compra_producto');
    const nombre = select.options[select.selectedIndex].text;
    const cant = parseFloat(document.getElementById('compra_cantidad').value);
    const costo = parseFloat(document.getElementById('compra_costo').value);
    
    if (!id_prod || isNaN(cant) || cant <= 0 || isNaN(costo) || costo < 0) {
        showCustomAlert("Campos de producto inválidos");
        return;
    }
    
    // Check if exists
    const ex = itemsNuevaCompra.find(i => i.id_producto == id_prod);
    if (ex) {
        ex.cantidad += cant;
        // update costo? maybe average, but let's just keep latest
        ex.costo_unitario = costo; 
    } else {
        itemsNuevaCompra.push({
            id_producto: id_prod,
            nombre: nombre,
            cantidad: cant,
            costo_unitario: costo
        });
    }
    
    if (choiceProducto) choiceProducto.setChoiceByValue('');
    else document.getElementById('compra_producto').value = '';
    
    document.getElementById('compra_cantidad').value = '1';
    document.getElementById('compra_costo').value = '0';
    renderizarItemsNuevaCompra();
}

function eliminarItem(idx) {
    itemsNuevaCompra.splice(idx, 1);
    renderizarItemsNuevaCompra();
}

function renderizarItemsNuevaCompra() {
    const tbody = document.querySelector('#tablaItemsCompra tbody');
    tbody.innerHTML = '';
    let total = 0;
    
    itemsNuevaCompra.forEach((it, idx) => {
        const sub = it.cantidad * it.costo_unitario;
        total += sub;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${it.nombre}</td>
            <td>${it.cantidad}</td>
            <td>C$ ${it.costo_unitario.toFixed(2)}</td>
            <td>C$ ${sub.toFixed(2)}</td>
            <td><button class="btn-icon delete" onclick="eliminarItem(${idx})">🗑️</button></td>
        `;
        tbody.appendChild(tr);
    });
    
    document.getElementById('compra_total').textContent = total.toFixed(2);
}

async function registrarCompra() {
    const id_prov = document.getElementById('compra_proveedor').value;
    const selectProv = document.getElementById('compra_proveedor');
    const selectedText = selectProv.options[selectProv.selectedIndex]?.text.toLowerCase() || '';
    const compraId = document.getElementById('compra_id').value;

    if (!id_prov) {
        showCustomAlert("Seleccione un proveedor o Gasto Vario");
        return;
    }
    
    let payload = {};
    if (selectedText.includes('varios')) {
        const desc = document.getElementById('gasto_descripcion').value;
        const monto = parseFloat(document.getElementById('gasto_monto').value);
        if (!desc || isNaN(monto) || monto <= 0) {
            showCustomAlert("Ingrese una descripción y un monto mayor a 0");
            return;
        }
        payload = {
            id_proveedor: 'varios',
            descripcion: desc,
            monto: monto
        };
    } else {
        if (itemsNuevaCompra.length === 0) {
            showCustomAlert("Agregue al menos un producto");
            return;
        }
        payload = {
            id_proveedor: id_prov,
            items: itemsNuevaCompra
        };
    }
    
    const isEdit = compraId !== '';
    const url = isEdit ? `/compras/api/editar/${compraId}` : '/compras/api/crear';
    const method = isEdit ? 'PUT' : 'POST';

    const btn = document.getElementById('btnGuardarCompra');
    btn.disabled = true;
    
    try {
        const res = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const r = await res.json();
        if (r.success) {
            showCustomAlert(r.message, false);
            cerrarModalCompra();
            // Reload list
            const compRes = await fetch('/compras/api/list');
            comprasList = await compRes.json();
            renderizarTablaCompras();
        } else {
            showCustomAlert("Error: " + r.message);
        }
    } catch(e) {
        console.error(e);
        showCustomAlert("Error de servidor");
    } finally {
        btn.disabled = false;
    }
}

async function verDetalles(id) {
    try {
        const res = await fetch(`/compras/api/detalle/${id}`);
        const r = await res.json();
        
        if (r.success) {
            const tbody = document.querySelector('#tablaDetallesView tbody');
            tbody.innerHTML = '';
            r.detalles.forEach(d => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${d.producto_nombre}</td>
                    <td>${d.cantidad}</td>
                    <td>C$ ${d.precio_unitario.toFixed(2)}</td>
                    <td>C$ ${d.subtotal.toFixed(2)}</td>
                `;
                tbody.appendChild(tr);
            });
            document.getElementById('modalDetalles').style.display = 'flex';
        } else {
            showCustomAlert("Error: " + r.message);
        }
    } catch(e) {
        console.error(e);
    }
}
