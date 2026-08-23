// productos.js
let productosList = [];
let categoriasList = [];
let marcasList = [];
let unidadesList = [];
let proveedoresList = [];

document.addEventListener('DOMContentLoaded', () => {
    cargarSelects();
    cargarProductos();

    // Filtros
    document.getElementById('searchInput').addEventListener('input', renderizarTabla);
    document.getElementById('tipoFilter').addEventListener('change', renderizarTabla);
    document.getElementById('catFilter').addEventListener('change', renderizarTabla);
    document.getElementById('estadoFilter').addEventListener('change', renderizarTabla);
    document.getElementById('impuestoFilter').addEventListener('change', renderizarTabla);

    // Botones de Modales
    document.getElementById('btnNuevoProducto').addEventListener('click', abrirModalCrear);
    document.getElementById('btnCerrarModalProducto').addEventListener('click', cerrarModalProducto);
    document.getElementById('btnCerrarModalEntrada').addEventListener('click', cerrarModalEntrada);
    document.getElementById('btnNuevaMarca').addEventListener('click', () => {
        document.getElementById('formNuevaMarca').reset();
        document.getElementById('modalNuevaMarca').style.display = 'flex';
    });
    document.getElementById('btnCerrarModalMarca').addEventListener('click', () => {
        document.getElementById('modalNuevaMarca').style.display = 'none';
    });
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
    document.getElementById('formEntrada').addEventListener('submit', guardarEntrada);
    document.getElementById('formNuevaMarca').addEventListener('submit', guardarNuevaMarca);

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
        const [catRes, marRes, uniRes, provRes] = await Promise.all([
            fetch('/productos/api/categorias'),
            fetch('/productos/api/marcas'),
            fetch('/productos/api/unidades'),
            fetch('/proveedores/api/list')
        ]);

        categoriasList = await catRes.json();
        marcasList = await marRes.json();
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

        // Marca va ligada a un Proveedor: mostramos "Marca — Proveedor" para
        // que quede claro a quien comprarle cuando se repone stock.
        const prodMarca = document.getElementById('prod_marca');
        prodMarca.innerHTML = '<option value="">Sin Marca</option>';
        marcasList.forEach(m => {
            const etiqueta = m.proveedor_nombre ? `${m.nombre} — ${m.proveedor_nombre}` : m.nombre;
            prodMarca.innerHTML += `<option value="${m.id_marca}">${etiqueta}</option>`;
        });

        const prodUnidad = document.getElementById('prod_unidad');
        prodUnidad.innerHTML = '<option value="">Sin Unidad</option>';
        unidadesList.forEach(u => {
            prodUnidad.innerHTML += `<option value="${u.id_unidad}">${u.nombre} (${u.abreviatura})</option>`;
        });

        const nuevaMarcaProveedor = document.getElementById('nueva_marca_proveedor');
        if (nuevaMarcaProveedor) {
            nuevaMarcaProveedor.innerHTML = '<option value="">Sin proveedor</option>';
            proveedoresList.forEach(p => {
                nuevaMarcaProveedor.innerHTML += `<option value="${p.id_proveedor}">${p.nombre}</option>`;
            });
        }

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
    
    filtrados.forEach(p => {
        const tr = document.createElement('tr');
        
        let badgeClass = p.estado === 'activo' ? 'badge-active' : 'badge-inactive';
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
            <td><span class="badge ${badgeClass}">${p.estado}</span></td>
            <td>
                <button class="btn-icon" onclick="abrirModalEditar(${p.id_producto})" title="Editar">✏️</button>
                <button class="btn-icon" style="color: #28a745;" onclick="abrirModalEntrada(${p.id_producto}, '${p.nombre.replace(/'/g, "\\'")}')" title="Ingresar Stock">➕</button>
                <button class="btn-icon delete" onclick="eliminarProducto(${p.id_producto})" title="Eliminar">🗑️</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// --- MODAL PRODUCTO (CREAR / EDITAR) ---

function abrirModalCrear() {
    document.getElementById('modalProductoTitle').textContent = 'Nuevo Producto';
    document.getElementById('formProducto').reset();
    document.getElementById('prod_id').value = '';
    document.getElementById('prod_tipo_producto').value = 'final';
    document.getElementById('prod_imagen_preview').innerHTML = '';
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
    document.getElementById('prod_marca').value = p.id_marca || '';
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
    formData.append('id_marca', document.getElementById('prod_marca').value);
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

// --- MODAL ENTRADA STOCK ---

function abrirModalEntrada(id, nombre) {
    document.getElementById('entrada_prod_id').value = id;
    document.getElementById('entradaProductName').textContent = "Ingresando stock a: " + nombre;
    document.getElementById('entrada_cantidad').value = '';
    document.getElementById('modalEntrada').style.display = 'flex';
}

function cerrarModalEntrada() {
    document.getElementById('modalEntrada').style.display = 'none';
}

async function guardarEntrada(e) {
    e.preventDefault();
    
    const id = document.getElementById('entrada_prod_id').value;
    const cantidad = document.getElementById('entrada_cantidad').value;
    
    try {
        const response = await fetch(`/productos/api/entrada/${id}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({cantidad: cantidad})
        });
        const result = await response.json();
        if (result.success) {
            cerrarModalEntrada();
            cargarProductos(); // Refrescar para ver el nuevo stock
        } else {
            showCustomAlert('Error al ingresar stock: ' + result.message);
        }
    } catch (error) {
        console.error("Error en entrada de stock:", error);
        showCustomAlert('Ocurrió un error en el servidor');
    }
}

async function guardarNuevaMarca(e) {
    e.preventDefault();

    const nombre = document.getElementById('nueva_marca_nombre').value;
    const id_proveedor = document.getElementById('nueva_marca_proveedor').value || null;

    try {
        const response = await fetch(`/productos/api/marcas/crear`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({nombre: nombre, id_proveedor: id_proveedor})
        });
        const result = await response.json();
        if (result.success) {
            document.getElementById('modalNuevaMarca').style.display = 'none';
            cargarSelects(); // Reload selects to show the new brand
        } else {
            showCustomAlert('Error al crear marca: ' + result.message);
        }
    } catch (error) {
        console.error("Error al crear marca:", error);
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

// --- ELIMINAR ---

async function eliminarProducto(id) {
    showCustomConfirm('¿Está seguro de eliminar (desactivar) este producto?', async () => {
        try {
            const response = await fetch(`/productos/api/eliminar/${id}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            if (result.success) {
                cargarProductos();
            } else {
                showCustomAlert('Error al eliminar: ' + result.message);
            }
        } catch (error) {
            console.error("Error al eliminar:", error);
            showCustomAlert('Ocurrió un error en el servidor');
        }
    });
}
