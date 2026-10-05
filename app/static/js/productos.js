// productos.js
let productosList = [];
let categoriasList = [];
let unidadesList = [];
let proveedoresList = [];
const pagProductos = crearPaginador('paginacionProductos', 20);

document.addEventListener('DOMContentLoaded', () => {
    cargarSelects();
    cargarProductos();

    // Filtros
    const reiniciarYRenderizar = () => { pagProductos.reset(); renderizarTabla(); };
    document.getElementById('searchInput').addEventListener('input', reiniciarYRenderizar);
    document.getElementById('tipoFilter').addEventListener('change', reiniciarYRenderizar);
    document.getElementById('catFilter').addEventListener('change', reiniciarYRenderizar);
    document.getElementById('estadoFilter').addEventListener('change', reiniciarYRenderizar);
    document.getElementById('impuestoFilter').addEventListener('change', reiniciarYRenderizar);

    // Botones de Modales
    document.getElementById('btnNuevoProducto').addEventListener('click', abrirModalCrear);
    document.getElementById('btnCerrarModalProducto').addEventListener('click', cerrarModalProducto);
    document.getElementById('btnNuevaCategoria').addEventListener('click', () => {
        document.getElementById('formNuevaCategoria').reset();
        document.getElementById('modalNuevaCategoria').style.display = 'flex';
    });
    document.getElementById('btnCerrarModalCategoria').addEventListener('click', () => {
        document.getElementById('modalNuevaCategoria').style.display = 'none';
    });
    document.getElementById('formNuevaCategoria').addEventListener('submit', guardarNuevaCategoria);

    // Precio + IVA dinámico
    document.getElementById('prod_precio_venta').addEventListener('input', calcularIvaEnModal);
    document.getElementById('prod_aplica_impuesto').addEventListener('change', calcularIvaEnModal);

    // Insumo/material: sin precio de venta, sin categoría, sin IVA
    document.getElementById('prod_tipo_producto').addEventListener('change', actualizarCamposPorTipo);

    // Formularios
    document.getElementById('formProducto').addEventListener('submit', guardarProducto);

    // Pestañas Datos / Receta del modal
    document.querySelectorAll('.prod-tab').forEach(btn => {
        btn.addEventListener('click', () => mostrarTabProducto(btn.dataset.tab));
    });
    document.getElementById('rec_agregar').addEventListener('click', () => agregarFilaReceta());

    // Preview de imagen al seleccionar archivo
    document.getElementById('prod_imagen').addEventListener('change', function() {
        const preview = document.getElementById('prod_imagen_preview');
        if (this.files && this.files[0]) {
            const reader = new FileReader();
            reader.onload = e => {
                preview.innerHTML = `<img src="${e.target.result}" style="max-width: 120px; max-height: 80px; object-fit: cover; border-radius: 8px; border: 1px solid #e1e7f0; margin-top: 4px;">`;
            };
            reader.readAsDataURL(this.files[0]);
        }
    });
});

async function cargarSelects() {
    try {
        const [catRes, uniRes, provRes] = await Promise.all([
            fetch('/productos/api/categorias'),
            fetch('/productos/api/unidades'),
            fetch('/productos/api/proveedores')
        ]);

        categoriasList = await catRes.json();
        unidadesList = await uniRes.json();
        proveedoresList = await provRes.json();

        const catFilter = document.getElementById('catFilter');
        const prodCategoria = document.getElementById('prod_categoria');
        catFilter.innerHTML = '<option value="">Categoría: Todas</option>';
        prodCategoria.innerHTML = '<option value="">Sin Categoría</option>';
        categoriasList.forEach(c => {
            catFilter.innerHTML += `<option value="${c.id_categoria}">${c.nombre}</option>`;
            prodCategoria.innerHTML += `<option value="${c.id_categoria}">${c.nombre}</option>`;
        });

        const prodProveedor = document.getElementById('prod_proveedor');
        prodProveedor.innerHTML = '<option value="">Sin Proveedor</option>';
        proveedoresList.forEach(p => {
            prodProveedor.innerHTML += `<option value="${p.id_proveedor}">${p.nombre}</option>`;
        });

        const prodUnidad = document.getElementById('prod_unidad');
        prodUnidad.innerHTML = '<option value="">Sin Unidad</option>';
        unidadesList.forEach(u => {
            prodUnidad.innerHTML += `<option value="${u.id_unidad}">${u.nombre} (${u.abreviatura})</option>`;
        });

    } catch (error) {
        console.error("Error cargando selects:", error);
    }
}

async function cargarProductos() {
    try {
        const response = await fetch('/productos/api/list');
        productosList = await response.json();
        renderizarTabla();
    } catch (error) {
        console.error("Error cargando productos:", error);
    }
}

function renderizarTabla() {
    const tbody = document.getElementById('productosTableBody');
    tbody.innerHTML = '';
    
    const search = document.getElementById('searchInput').value.toLowerCase();
    const tipo = document.getElementById('tipoFilter').value;
    const cat = document.getElementById('catFilter').value;
    const estado = document.getElementById('estadoFilter').value;
    const impuesto = document.getElementById('impuestoFilter').value;

    let filtrados = productosList.filter(p => {
        const matchSearch = p.nombre.toLowerCase().includes(search) || (p.codigo && p.codigo.toLowerCase().includes(search));
        const matchTipo = tipo === '' || p.tipo_producto === tipo;
        const matchCat = cat === '' || String(p.id_categoria) === cat;
        const matchEstado = estado === '' || p.estado === estado;
        const matchImpuesto = impuesto === '' || String(p.aplica_impuesto) === impuesto;
        return matchSearch && matchTipo && matchCat && matchEstado && matchImpuesto;
    });
    
    pagProductos.paginar(filtrados, renderizarTabla).forEach(p => {
        const tr = document.createElement('tr');
        
        let stockStyle = p.stock <= 0 ? 'color: red; font-weight: bold;' : '';
        let imgHtml = p.imagen_url
            ? `<img src="${p.imagen_url}" style="width: 44px; height: 44px; object-fit: cover; border-radius: 8px; border: 1px solid #e1e7f0;">`
            : `<span style="font-size: 26px;">📦</span>`;

        const tipoChip = {final: 'final', insumo: 'insumo', material: 'material'}[p.tipo_producto] || 'final';

        tr.innerHTML = `
            <td>${imgHtml}</td>
            <td>${p.codigo || '-'}</td>
            <td>${p.nombre}</td>
            <td><span class="q-chip ${tipoChip}" style="padding:2px 8px;font-size:11px;">${p.tipo_label || p.tipo_producto || 'final'}</span></td>
            <td>${p.categoria_nombre}</td>
            <td>C$ ${p.precio_compra.toFixed(2)}</td>
            <td>C$ ${p.precio_venta.toFixed(2)}</td>
            <td style="${stockStyle}">${p.stock}</td>
            <td>
                <select class="form-control estado-select ${p.estado === 'activo' ? 'badge-active' : 'badge-inactive'}" style="padding: 4px 6px; font-size: 12px; width: auto;" data-id="${p.id_producto}" data-anterior="${p.estado}" onchange="cambiarEstadoProducto(this)">
                    <option value="activo" ${p.estado === 'activo' ? 'selected' : ''}>Activo</option>
                    <option value="inactivo" ${p.estado === 'inactivo' ? 'selected' : ''}>Inactivo</option>
                </select>
            </td>
            <td>
                <button class="btn-icon" onclick="abrirModalEditar(${p.id_producto})" title="Editar">✏️</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// --- PESTAÑA RECETA (dentro del modal de producto) ---
// Dos sectores que guardan en el MISMO registro de receta:
//   - texto plano (modo_preparacion), solo referencia
//   - ingredientes + "descontar al vender" (lo que resta del inventario)

let insumosReceta = [];
let recetaEditable = false;   // true solo al editar un producto final

function mostrarTabProducto(tab) {
    document.getElementById('tab_datos').style.display = tab === 'tab_datos' ? '' : 'none';
    document.getElementById('tab_receta').style.display = tab === 'tab_receta' ? '' : 'none';
    document.querySelectorAll('.prod-tab').forEach(b => b.classList.toggle('activo', b.dataset.tab === tab));
}

async function cargarInsumosReceta() {
    if (insumosReceta.length) return;
    const res = await fetch('/recetas/api/insumos');
    const lista = await res.json();
    // Solo insumos/materiales como ingrediente (no otros platos del menu).
    insumosReceta = lista.filter(p => p.tipo_producto === 'insumo' || p.tipo_producto === 'material');
}

function agregarFilaReceta(idProducto = '', cantidad = 1) {
    const fila = document.createElement('div');
    fila.className = 'rec-fila';
    const opciones = insumosReceta.map(p =>
        `<option value="${p.id_producto}" ${p.id_producto === idProducto ? 'selected' : ''}>${escapeHtml(p.nombre)}</option>`
    ).join('');
    fila.innerHTML = `
        <select class="form-control rec-insumo"><option value="">Elegir insumo...</option>${opciones}</select>
        <input type="number" class="form-control rec-cantidad" min="0.01" step="0.01" value="${cantidad}">
        <button type="button" class="btn" style="background:#f3e5e5;color:#8B2E2E;padding:4px 10px;" title="Quitar">✕</button>`;
    fila.querySelector('button').addEventListener('click', () => fila.remove());
    document.getElementById('rec_filas').appendChild(fila);
}

function prepararTabReceta(producto) {
    recetaEditable = !!producto && producto.tipo_producto === 'final';
    document.getElementById('prod_tabs').style.display = recetaEditable ? 'flex' : 'none';
    document.getElementById('rec_texto').value = '';
    document.getElementById('rec_descontar').checked = false;
    document.getElementById('rec_filas').innerHTML = '';
    mostrarTabProducto('tab_datos');
    if (!recetaEditable) return;

    Promise.all([
        cargarInsumosReceta(),
        fetch(`/recetas/api/por-producto/${producto.id_producto}`).then(r => r.json()),
    ]).then(([, receta]) => {
        document.getElementById('rec_texto').value = receta.texto || '';
        document.getElementById('rec_descontar').checked = !!receta.descontar;
        (receta.ingredientes || []).forEach(i => agregarFilaReceta(i.id_producto, i.cantidad_necesaria));
    }).catch(err => console.error('No se pudo cargar la receta:', err));
}

async function guardarRecetaProducto(idProducto) {
    const ingredientes = [];
    document.querySelectorAll('#rec_filas .rec-fila').forEach(fila => {
        const id = fila.querySelector('.rec-insumo').value;
        const cant = parseFloat(fila.querySelector('.rec-cantidad').value);
        if (id && cant > 0) ingredientes.push({ id_producto: parseInt(id), cantidad_necesaria: cant });
    });
    const res = await fetch(`/recetas/api/por-producto/${idProducto}/guardar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            texto: document.getElementById('rec_texto').value,
            ingredientes: ingredientes,
            descontar: document.getElementById('rec_descontar').checked,
        }),
    });
    return res.json();
}

// --- MODAL PRODUCTO (CREAR / EDITAR) ---

function abrirModalCrear() {
    document.getElementById('modalProductoTitle').textContent = 'Nuevo Producto';
    document.getElementById('formProducto').reset();
    document.getElementById('prod_id').value = '';
    document.getElementById('prod_tipo_producto').value = 'final';
    document.getElementById('prod_imagen_preview').innerHTML = '';
    // La receta se arma despues de crear el producto (necesita su id).
    prepararTabReceta(null);
    document.getElementById('modalProducto').style.display = 'flex';
    actualizarCamposPorTipo();
    calcularIvaEnModal();
}

// Insumo/material: no se venden -> ocultamos Precio Venta, Categoría e IVA.
// Solo "final" se vende al cliente y usa esos campos.
function actualizarCamposPorTipo() {
    const tipo = document.getElementById('prod_tipo_producto').value;
    const esVendible = tipo === 'final';

    document.getElementById('campo_categoria').style.display = esVendible ? '' : 'none';
    document.getElementById('campo_precio_venta').style.display = esVendible ? '' : 'none';
    document.getElementById('campo_iva').style.display = esVendible ? '' : 'none';
    document.getElementById('prod_tipo_ayuda').style.display = esVendible ? 'none' : 'block';

    if (!esVendible) {
        document.getElementById('prod_categoria').value = '';
        document.getElementById('prod_precio_venta').value = '0.00';
        document.getElementById('prod_aplica_impuesto').checked = false;
    }
}

function calcularIvaEnModal() {
    let precioBase = parseFloat(document.getElementById('prod_precio_venta').value);
    if (isNaN(precioBase)) precioBase = 0;
    
    // Calcula Precio Venta * 1.15 (sumándole el 15% de IVA)
    let precioConIva = document.getElementById('prod_aplica_impuesto').checked ? (precioBase * 1.15) : precioBase;
    
    document.getElementById('prod_precio_iva').textContent = `C$ ${precioConIva.toFixed(2)}`;
}

function abrirModalEditar(id) {
    const p = productosList.find(x => x.id_producto === id);
    if (!p) return;
    
    document.getElementById('modalProductoTitle').textContent = 'Editar Producto';
    document.getElementById('prod_id').value = p.id_producto;
    document.getElementById('prod_codigo').value = p.codigo || '';
    document.getElementById('prod_codigo_barra').value = p.codigo_barra || '';
    document.getElementById('prod_nombre').value = p.nombre || '';
    document.getElementById('prod_descripcion').value = p.descripcion || '';
    document.getElementById('prod_tipo_producto').value = p.tipo_producto || 'final';
    document.getElementById('prod_categoria').value = p.id_categoria || '';
    document.getElementById('prod_proveedor').value = p.id_proveedor || '';
    document.getElementById('prod_impresora').value = p.impresora || '';
    document.getElementById('prod_unidad').value = p.id_unidad || '';
    document.getElementById('prod_precio_compra').value = p.precio_compra.toFixed(2);
    document.getElementById('prod_precio_venta').value = p.precio_venta.toFixed(2);
    document.getElementById('prod_stock_minimo').value = p.stock_minimo || 0;
    document.getElementById('prod_aplica_impuesto').checked = p.aplica_impuesto || false;
    
    // Mostrar imagen actual si existe
    const preview = document.getElementById('prod_imagen_preview');
    if (p.imagen_url) {
        preview.innerHTML = `<img src="${p.imagen_url}" style="max-width: 120px; max-height: 80px; object-fit: cover; border-radius: 8px; border: 1px solid #e1e7f0; margin-top: 4px;">`;
    } else {
        preview.innerHTML = '';
    }
    document.getElementById('prod_imagen').value = '';

    prepararTabReceta(p);
    document.getElementById('modalProducto').style.display = 'flex';
    actualizarCamposPorTipo();
    calcularIvaEnModal();
}

function cerrarModalProducto() {
    document.getElementById('modalProducto').style.display = 'none';
    document.getElementById('prod_imagen_preview').innerHTML = '';
    document.getElementById('prod_imagen').value = '';
}

async function guardarProducto(e) {
    e.preventDefault();
    
    const id = document.getElementById('prod_id').value;
    const fileInput = document.getElementById('prod_imagen');
    
    const formData = new FormData();
    formData.append('codigo', document.getElementById('prod_codigo').value);
    formData.append('codigo_barra', document.getElementById('prod_codigo_barra').value);
    formData.append('nombre', document.getElementById('prod_nombre').value);
    formData.append('descripcion', document.getElementById('prod_descripcion').value);
    formData.append('tipo_producto', document.getElementById('prod_tipo_producto').value);
    formData.append('id_categoria', document.getElementById('prod_categoria').value);
    formData.append('id_proveedor', document.getElementById('prod_proveedor').value);
    formData.append('impresora', document.getElementById('prod_impresora').value);
    formData.append('id_unidad', document.getElementById('prod_unidad').value);
    formData.append('precio_compra', document.getElementById('prod_precio_compra').value);
    formData.append('precio_venta', document.getElementById('prod_precio_venta').value);
    formData.append('stock_minimo', document.getElementById('prod_stock_minimo').value);
    formData.append('aplica_impuesto', document.getElementById('prod_aplica_impuesto').checked);
    
    if (fileInput.files.length > 0) {
        formData.append('imagen', fileInput.files[0]);
    }
    
    const isEdit = id !== '';
    const url = isEdit ? `/productos/api/editar/${id}` : '/productos/api/crear';
    
    try {
        const response = await fetch(url, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();
        if (result.success) {
            // Receta: solo al editar un producto que sigue siendo "final".
            if (isEdit && recetaEditable && document.getElementById('prod_tipo_producto').value === 'final') {
                const rec = await guardarRecetaProducto(id);
                if (!rec.success) {
                    mostrarTabProducto('tab_receta');
                    showCustomAlert('El producto se guardó, pero la receta no: ' + rec.message);
                    cargarProductos();
                    return;
                }
            }
            cerrarModalProducto();
            cargarProductos();
        } else {
            showCustomAlert('Error al guardar: ' + result.message);
        }
    } catch (error) {
        console.error("Error al guardar producto:", error);
        showCustomAlert('Ocurrió un error en el servidor');
    }
}

async function guardarNuevaCategoria(e) {
    e.preventDefault();

    const nombre = document.getElementById('nueva_categoria_nombre').value;

    try {
        const response = await fetch(`/productos/api/categorias/crear`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({nombre: nombre})
        });
        const result = await response.json();
        if (result.success) {
            document.getElementById('modalNuevaCategoria').style.display = 'none';
            cargarSelects();
        } else {
            showCustomAlert('Error al crear categoría: ' + result.message);
        }
    } catch (error) {
        console.error("Error al crear categoría:", error);
        showCustomAlert('Ocurrió un error en el servidor');
    }
}

// --- ESTADO (activo/inactivo) ---

function cambiarEstadoProducto(select) {
    const id = select.dataset.id;
    const anterior = select.dataset.anterior;
    const nuevo = select.value;
    if (nuevo === anterior) return;

    // showCustomConfirm no tiene callback de "cancelar": el select se
    // regresa al valor anterior de inmediato y solo se aplica el cambio
    // (visual + API) si el usuario confirma.
    select.value = anterior;

    const accion = nuevo === 'activo' ? 'activar' : 'desactivar';
    showCustomConfirm(`¿Está seguro de ${accion} este producto?`, async () => {
        try {
            const response = await fetch(`/productos/api/estado/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({estado: nuevo})
            });
            const result = await response.json();
            if (result.success) {
                select.value = nuevo;
                select.dataset.anterior = nuevo;
                select.classList.toggle('badge-active', nuevo === 'activo');
                select.classList.toggle('badge-inactive', nuevo === 'inactivo');
                const idx = productosList.findIndex(p => p.id_producto == id);
                if (idx !== -1) productosList[idx].estado = nuevo;
            } else {
                showCustomAlert('Error al cambiar estado: ' + result.message);
            }
        } catch (error) {
            console.error("Error al cambiar estado:", error);
            showCustomAlert('Ocurrió un error en el servidor');
        }
    });
}

