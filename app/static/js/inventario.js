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

    // --- Subir inventario masivo ---
    document.getElementById('btnSubirInventario').addEventListener('click', abrirModalImportar);
    document.getElementById('btnCerrarModalImportar').addEventListener('click', () => {
        document.getElementById('modalImportar').style.display = 'none';
    });
    document.getElementById('btnDescargarPlantilla').addEventListener('click', descargarPlantillaInventario);
    document.getElementById('importarArchivo').addEventListener('change', leerArchivoImportar);
    document.getElementById('btnConfirmarImportar').addEventListener('click', confirmarImportar);
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

// --- SUBIR INVENTARIO MASIVO (Excel) ---

let importarFilasParseadas = [];

function abrirModalImportar() {
    document.getElementById('importarArchivo').value = '';
    document.getElementById('importarResumen').innerHTML = '';
    document.getElementById('importarResultado').innerHTML = '';
    document.getElementById('btnConfirmarImportar').disabled = true;
    importarFilasParseadas = [];
    document.getElementById('modalImportar').style.display = 'flex';
}

function descargarPlantillaInventario() {
    const datos = [
        { "Código": "", "Nombre": "Quesillo Lo Nuestro", "Tipo": "final", "Categoría": "Quesillos", "Marca": "", "Unidad": "Unidad", "Precio Compra": 25, "Precio Venta": 40, "Stock Actual": 50, "Stock Mínimo": 5, "Aplica IVA": "No" },
        { "Código": "", "Nombre": "Tortilla", "Tipo": "insumo", "Categoría": "", "Marca": "", "Unidad": "Unidad", "Precio Compra": 3, "Precio Venta": "", "Stock Actual": 200, "Stock Mínimo": 20, "Aplica IVA": "" },
    ];
    const wsDatos = XLSX.utils.json_to_sheet(datos);
    wsDatos['!cols'] = [{ wch: 12 }, { wch: 26 }, { wch: 10 }, { wch: 16 }, { wch: 14 }, { wch: 10 }, { wch: 13 }, { wch: 13 }, { wch: 12 }, { wch: 13 }, { wch: 10 }];

    const instrucciones = [
        ["Cómo llenar esta plantilla"],
        ["- Código: opcional. Si lo dejas vacío se genera solo. Si coincide con un producto que ya existe, se actualiza ese producto en vez de crear uno nuevo."],
        ["- Nombre: obligatorio. Si no hay código y el nombre coincide con uno existente (sin importar mayúsculas), también se actualiza ese producto."],
        ["- Tipo: final, insumo o material. Solo 'final' se vende al cliente."],
        ["- Categoría, Precio Venta y Aplica IVA solo aplican si Tipo = final. Para insumo/material déjalos vacíos."],
        ["- Categoría y Marca: si escribes un nombre que no existe todavía, se crea automáticamente."],
        ["- Unidad: debe coincidir con una unidad ya existente en el sistema (nombre o abreviatura); si no coincide, se deja sin unidad."],
        ["- Stock Actual y Stock Mínimo: el valor que pongas REEMPLAZA el stock actual del sistema (no se suma)."],
        ["- Aplica IVA: escribe Sí o No."],
        ["- No cambies los nombres de las columnas de la hoja 'Plantilla'."],
    ];
    const wsInstrucciones = XLSX.utils.aoa_to_sheet(instrucciones);
    wsInstrucciones['!cols'] = [{ wch: 110 }];

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, wsDatos, "Plantilla");
    XLSX.utils.book_append_sheet(wb, wsInstrucciones, "Instrucciones");
    XLSX.writeFile(wb, "Plantilla_Inventario.xlsx");
}

async function leerArchivoImportar(e) {
    const file = e.target.files[0];
    const resumen = document.getElementById('importarResumen');
    const btn = document.getElementById('btnConfirmarImportar');
    document.getElementById('importarResultado').innerHTML = '';
    if (!file) { resumen.innerHTML = ''; btn.disabled = true; return; }

    try {
        const buf = await file.arrayBuffer();
        const wb = XLSX.read(buf, { type: 'array' });
        const hoja = wb.Sheets[wb.SheetNames[0]];
        const filas = XLSX.utils.sheet_to_json(hoja, { defval: '' });

        importarFilasParseadas = filas.map(f => ({
            codigo: String(f['Código'] ?? '').trim(),
            nombre: String(f['Nombre'] ?? '').trim(),
            tipo: String(f['Tipo'] ?? 'final').trim().toLowerCase(),
            categoria: String(f['Categoría'] ?? '').trim(),
            marca: String(f['Marca'] ?? '').trim(),
            unidad: String(f['Unidad'] ?? '').trim(),
            precio_compra: f['Precio Compra'],
            precio_venta: f['Precio Venta'],
            stock_actual: f['Stock Actual'],
            stock_minimo: f['Stock Mínimo'],
            aplica_impuesto: f['Aplica IVA'],
        })).filter(f => f.nombre);

        if (!importarFilasParseadas.length) {
            resumen.innerHTML = '<p style="color:#c0392b;">No se encontraron filas válidas. Revisa que la hoja tenga la columna "Nombre" llena.</p>';
            btn.disabled = true;
        } else {
            resumen.innerHTML = `<p style="color:#1f6b45;">Se leyeron <strong>${importarFilasParseadas.length}</strong> productos del archivo. Dale "Subir" para importarlos.</p>`;
            btn.disabled = false;
        }
    } catch (error) {
        console.error(error);
        resumen.innerHTML = '<p style="color:#c0392b;">No se pudo leer el archivo. ¿Es un Excel (.xlsx) válido?</p>';
        importarFilasParseadas = [];
        btn.disabled = true;
    }
}

async function confirmarImportar() {
    if (!importarFilasParseadas.length) return;
    const btn = document.getElementById('btnConfirmarImportar');
    const textoOriginal = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Subiendo…';
    try {
        const res = await fetch('/productos/api/importar_masivo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filas: importarFilasParseadas })
        });
        const r = await res.json();
        const resultado = document.getElementById('importarResultado');
        if (r.success) {
            resultado.innerHTML = `
                <div style="background:#e6f4ec;color:#1f6b45;padding:10px 12px;border-radius:8px;margin-top:10px;font-size:13px;">
                    ✅ ${r.creados} producto(s) creados, ${r.actualizados} actualizados.
                </div>
                ${r.errores.length ? `<div style="background:#fbe7e7;color:#a72020;padding:10px 12px;border-radius:8px;margin-top:8px;max-height:150px;overflow:auto;font-size:12.5px;">⚠️ ${r.errores.length} fila(s) con error:<br>${r.errores.map(e => `• ${e}`).join('<br>')}</div>` : ''}
            `;
            importarFilasParseadas = [];
            document.getElementById('importarArchivo').value = '';
            document.getElementById('importarResumen').innerHTML = '';
            cargarInventario();
        } else {
            resultado.innerHTML = `<div style="background:#fbe7e7;color:#a72020;padding:10px 12px;border-radius:8px;margin-top:10px;font-size:13px;">Error: ${r.message}</div>`;
        }
    } catch (error) {
        console.error(error);
        showCustomAlert('Error en el servidor al importar');
    } finally {
        btn.disabled = importarFilasParseadas.length === 0;
        btn.textContent = textoOriginal;
    }
}
