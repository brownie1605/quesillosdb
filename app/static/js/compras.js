let comprasList = [];
let proveedoresList = [];
let productosList = [];
let itemsNuevaCompra = [];
let choiceProveedor = null;
let choiceProducto = null;
const pagCompras = crearPaginador('paginacionCompras', 20);

document.addEventListener('DOMContentLoaded', () => {
    cargarDatosIniciales();

    document.getElementById('searchInput').addEventListener('input', () => { pagCompras.reset(); renderizarTablaCompras(); });
    
    // Modal Nueva Compra
    document.getElementById('btnNuevaCompra').addEventListener('click', abrirModalCompra);
    document.getElementById('btnCerrarModalCompra').addEventListener('click', cerrarModalCompra);
    document.getElementById('btnAgregarItem').addEventListener('click', agregarItem);
    document.getElementById('btnGuardarCompra').addEventListener('click', registrarCompra);
    
    // Modal Detalles
    document.getElementById('btnCerrarDetalles').addEventListener('click', () => {
        document.getElementById('modalDetalles').style.display = 'none';
    });

    // Modal Cargar compra masiva (Excel)
    document.getElementById('btnImportarCompra').addEventListener('click', abrirModalImportarCompra);
    document.getElementById('btnCerrarModalImportarCompra').addEventListener('click', () => {
        document.getElementById('modalImportarCompra').style.display = 'none';
    });
    document.getElementById('btnDescargarPlantillaCompra').addEventListener('click', descargarPlantillaCompra);
    document.getElementById('importarCompraArchivo').addEventListener('change', leerArchivoImportarCompra);
    document.getElementById('btnConfirmarImportarCompra').addEventListener('click', confirmarImportarCompra);
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
        
        
        // Una receta (plato preparado) no se compra a un proveedor, se
        // prepara con sus insumos -> no debe aparecer aqui como comprable.
        const selectProd = document.getElementById('compra_producto');
        productosList.filter(p => !p.es_receta).forEach(p => {
            selectProd.innerHTML += `<option value="${p.id_producto}" data-costo="${p.precio_compra || 0}">${p.nombre}</option>`;
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

    pagCompras.paginar(filtrados, renderizarTablaCompras).forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${escapeHtml(c.numero_compra)}</strong></td>
            <td>${c.fecha_compra}</td>
            <td>${escapeHtml(c.proveedor_nombre)}</td>
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

// --- CARGAR COMPRA MASIVA (Excel) ---
// El stock solo se mueve comprando: cada fila del Excel es una linea de
// compra real (producto + cantidad + costo + proveedor), no un ajuste
// directo de inventario.

let importarCompraFilasParseadas = [];

function abrirModalImportarCompra() {
    document.getElementById('importarCompraArchivo').value = '';
    document.getElementById('importarCompraResumen').innerHTML = '';
    document.getElementById('importarCompraResultado').innerHTML = '';
    document.getElementById('btnConfirmarImportarCompra').disabled = true;
    importarCompraFilasParseadas = [];
    document.getElementById('modalImportarCompra').style.display = 'flex';
}

function descargarPlantillaCompra() {
    const datos = [
        { "Código": "", "Nombre": "Quesillo Lo Nuestro", "Tipo": "final", "Categoría": "Quesillos", "Proveedor": "Distribuidora El Sol", "Unidad": "Unidad", "Precio Venta": 40, "Costo Unitario": 25, "Cantidad": 20, "Stock Mínimo": 5, "Aplica IVA": "No" },
        { "Código": "", "Nombre": "Tortilla", "Tipo": "insumo", "Categoría": "", "Proveedor": "Tortillería Doña Chepa", "Unidad": "Unidad", "Precio Venta": "", "Costo Unitario": 3, "Cantidad": 200, "Stock Mínimo": 20, "Aplica IVA": "" },
    ];
    const wsDatos = XLSX.utils.json_to_sheet(datos);
    wsDatos['!cols'] = [{ wch: 12 }, { wch: 26 }, { wch: 10 }, { wch: 16 }, { wch: 22 }, { wch: 10 }, { wch: 13 }, { wch: 13 }, { wch: 10 }, { wch: 13 }, { wch: 10 }];

    const instrucciones = [
        ["Cómo llenar esta plantilla"],
        ["- Cada fila es una línea de compra: cuánto compraste de qué producto, a qué proveedor y a qué costo."],
        ["- Proveedor: OBLIGATORIO por fila (a quién se le compró). Si no existe todavía, se crea automáticamente."],
        ["- Cantidad y Costo Unitario: obligatorios. La Cantidad es lo que se SUMA al stock actual del producto (no lo reemplaza)."],
        ["- Código: opcional. Si coincide con un producto que ya existe, se actualiza ese producto en vez de crear uno nuevo."],
        ["- Nombre: obligatorio. Si no hay código y el nombre coincide con uno existente (sin importar mayúsculas), también se actualiza ese producto."],
        ["- Tipo: final, insumo o material. Solo 'final' se vende al cliente."],
        ["- Categoría, Precio Venta y Aplica IVA solo aplican si Tipo = final."],
        ["- Categoría: si escribes un nombre que no existe todavía, se crea automáticamente."],
        ["- Unidad: debe coincidir con una unidad ya existente en el sistema (nombre o abreviatura); si no coincide, se deja sin unidad."],
        ["- Stock Mínimo: opcional, solo se actualiza si lo llenas."],
        ["- Aplica IVA: escribe Sí o No."],
        ["- Se genera una Compra por cada Proveedor distinto que aparezca en el archivo (con todas sus líneas adentro)."],
        ["- No cambies los nombres de las columnas de la hoja 'Plantilla'."],
    ];
    const wsInstrucciones = XLSX.utils.aoa_to_sheet(instrucciones);
    wsInstrucciones['!cols'] = [{ wch: 115 }];

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, wsDatos, "Plantilla");
    XLSX.utils.book_append_sheet(wb, wsInstrucciones, "Instrucciones");
    XLSX.writeFile(wb, "Plantilla_Compra_Masiva.xlsx");
}

async function leerArchivoImportarCompra(e) {
    const file = e.target.files[0];
    const resumen = document.getElementById('importarCompraResumen');
    const btn = document.getElementById('btnConfirmarImportarCompra');
    document.getElementById('importarCompraResultado').innerHTML = '';
    if (!file) { resumen.innerHTML = ''; btn.disabled = true; return; }

    try {
        const buf = await file.arrayBuffer();
        const wb = XLSX.read(buf, { type: 'array' });
        const hoja = wb.Sheets[wb.SheetNames[0]];
        const filas = XLSX.utils.sheet_to_json(hoja, { defval: '' });

        importarCompraFilasParseadas = filas.map(f => ({
            codigo: String(f['Código'] ?? '').trim(),
            nombre: String(f['Nombre'] ?? '').trim(),
            tipo: String(f['Tipo'] ?? 'final').trim().toLowerCase(),
            categoria: String(f['Categoría'] ?? '').trim(),
            proveedor: String(f['Proveedor'] ?? '').trim(),
            unidad: String(f['Unidad'] ?? '').trim(),
            precio_venta: f['Precio Venta'],
            costo_unitario: f['Costo Unitario'],
            cantidad: f['Cantidad'],
            stock_minimo: f['Stock Mínimo'],
            aplica_impuesto: f['Aplica IVA'],
        })).filter(f => f.nombre);

        if (!importarCompraFilasParseadas.length) {
            resumen.innerHTML = '<p style="color:#c0392b;">No se encontraron filas válidas. Revisa que la hoja tenga la columna "Nombre" llena.</p>';
            btn.disabled = true;
        } else {
            resumen.innerHTML = `<p style="color:#1f6b45;">Se leyeron <strong>${importarCompraFilasParseadas.length}</strong> líneas de compra. Dale "Subir" para registrarlas.</p>`;
            btn.disabled = false;
        }
    } catch (error) {
        console.error(error);
        resumen.innerHTML = '<p style="color:#c0392b;">No se pudo leer el archivo. ¿Es un Excel (.xlsx) válido?</p>';
        importarCompraFilasParseadas = [];
        btn.disabled = true;
    }
}

async function confirmarImportarCompra() {
    if (!importarCompraFilasParseadas.length) return;
    const btn = document.getElementById('btnConfirmarImportarCompra');
    const textoOriginal = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Subiendo…';
    try {
        const res = await fetch('/compras/api/importar_masivo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filas: importarCompraFilasParseadas })
        });
        const r = await res.json();
        const resultado = document.getElementById('importarCompraResultado');
        if (r.success) {
            const listaCompras = (r.compras || []).map(c => `• ${c.proveedor}: ${c.lineas} línea(s), C$ ${c.total.toFixed(2)} (${c.numero_compra})`).join('<br>');
            resultado.innerHTML = `
                <div style="background:#e6f4ec;color:#1f6b45;padding:10px 12px;border-radius:8px;margin-top:10px;font-size:13px;">
                    ✅ ${r.compras.length} compra(s) generadas · ${r.productos_creados} producto(s) nuevos, ${r.productos_actualizados} actualizados.
                    ${listaCompras ? `<br><br>${listaCompras}` : ''}
                </div>
                ${r.errores.length ? `<div style="background:#fbe7e7;color:#a72020;padding:10px 12px;border-radius:8px;margin-top:8px;max-height:150px;overflow:auto;font-size:12.5px;">⚠️ ${r.errores.length} fila(s) con error:<br>${r.errores.map(e => `• ${e}`).join('<br>')}</div>` : ''}
            `;
            importarCompraFilasParseadas = [];
            document.getElementById('importarCompraArchivo').value = '';
            document.getElementById('importarCompraResumen').innerHTML = '';
            cargarDatosIniciales();
        } else {
            resultado.innerHTML = `<div style="background:#fbe7e7;color:#a72020;padding:10px 12px;border-radius:8px;margin-top:10px;font-size:13px;">Error: ${r.message}${(r.errores||[]).length ? '<br>' + r.errores.map(e=>`• ${e}`).join('<br>') : ''}</div>`;
        }
    } catch (error) {
        console.error(error);
        showCustomAlert('Error en el servidor al importar');
    } finally {
        btn.disabled = importarCompraFilasParseadas.length === 0;
        btn.textContent = textoOriginal;
    }
}
