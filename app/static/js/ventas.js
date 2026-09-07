// ventas.js
let productos = [];
let cart = [];
let descuentoPct = 0.0;       // % que el cajero eligio (0-100)
let descuentoAplicado = 0.0;  // monto en C$ derivado de descuentoPct * subtotal
let propinaAplicada = 0.0;
let propinaManual = null; // Si el usuario edita manualmente
let categoriaActiva = '';
let textoBusqueda = '';

// Producto en espera de que el cajero/mesero termine el modal de personalización.
let pzProductoActual = null;
let pzDatosActuales = null;

document.addEventListener('DOMContentLoaded', () => {
    cargarProductos();
    cargarClientes();

    document.getElementById('searchInput').addEventListener('input', (e) => {
        textoBusqueda = e.target.value.toLowerCase();
        aplicarFiltros();
    });

    // Método de pago: selector de bancos si es Tarjeta, efectivo/cambio si es Efectivo
    document.getElementById('paymentMethod').addEventListener('change', (e) => {
        document.getElementById('bankSelection').style.display = e.target.value === 'Tarjeta' ? 'flex' : 'none';
        actualizarCambio();
    });

    // Antiguo botón cobrar, ahora abre el modal
    document.getElementById('chargeBtn').addEventListener('click', abrirModalCheckout);
    document.getElementById('cancelSaleBtn').addEventListener('click', cancelarVenta);

    // Eventos del Modal de Checkout
    document.getElementById('closeCheckoutModalBtn').addEventListener('click', cerrarModalCheckout);
    document.getElementById('propinaSwitch').addEventListener('change', recalcularTotalesModal);
    document.getElementById('confirmCheckoutBtn').addEventListener('click', confirmarCobro);
    document.getElementById('modalEfectivoRecibido').addEventListener('input', actualizarCambio);

    // Eventos del Modal de Descuento
    document.getElementById('openDiscountModalBtn').addEventListener('click', abrirModalDescuento);
    document.getElementById('closeDiscountModalBtn').addEventListener('click', cerrarModalDescuento);
    document.getElementById('applyDiscountBtn').addEventListener('click', aplicarDescuento);

    // Eventos del Modal de Propina
    document.getElementById('openPropinaModalBtn').addEventListener('click', abrirModalPropina);
    document.getElementById('closePropinaModalBtn').addEventListener('click', cerrarModalPropina);
    document.getElementById('applyPropinaBtn').addEventListener('click', aplicarPropina);

    // Eventos del Modal de Personalización
    document.getElementById('pzCancelBtn').addEventListener('click', cerrarModalPersonalizacion);
    document.getElementById('pzAgregarBtn').addEventListener('click', confirmarPersonalizacion);

    // Eventos del Modal de Éxito
    document.getElementById('successCloseBtn').addEventListener('click', () => {
        document.getElementById('successModal').style.display = 'none';
    });
    document.getElementById('successPrintBtn').addEventListener('click', () => {
        const ventaId = document.getElementById('successPrintBtn').dataset.ventaId;
        if (ventaId) window.open(`/ventas/factura/${ventaId}`, '_blank');
        document.getElementById('successModal').style.display = 'none';
    });
});

async function cargarProductos() {
    try {
        const response = await fetch('/ventas/api/productos');
        productos = await response.json();
        renderizarTabsCategorias();
        aplicarFiltros();
    } catch (error) {
        console.error('Error cargando productos:', error);
    }
}

async function cargarClientes() {
    try {
        const response = await fetch('/ventas/api/clientes');
        const clientes = await response.json();
        const select = document.getElementById('clientSelect');
        clientes.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id_cliente;
            opt.textContent = `${c.nombre} - ${c.cedula || ''}`;
            select.appendChild(opt);
        });

        if (window.Choices) {
            new Choices(select, {
                searchEnabled: true,
                itemSelectText: '',
                noResultsText: 'No se encontraron clientes',
                noChoicesText: 'No hay opciones',
                placeholderValue: 'Seleccione un cliente...'
            });
        }
    } catch (error) {
        console.error('Error cargando clientes:', error);
    }
}

// ---- CATEGORÍAS ----

function renderizarTabsCategorias() {
    const nombres = [...new Set(productos.map(p => p.categoria_nombre || 'Sin categoría'))].sort();
    const tabs = document.getElementById('catTabs');
    if (nombres.length <= 1) { tabs.innerHTML = ''; return; }

    const todas = [{ label: 'Todos', value: '' }, ...nombres.map(n => ({ label: n, value: n }))];
    tabs.innerHTML = todas.map(t => `
        <button type="button" class="cat-tab ${categoriaActiva === t.value ? 'active' : ''}" data-cat="${t.value}">${t.label}</button>
    `).join('');

    tabs.querySelectorAll('.cat-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            categoriaActiva = btn.dataset.cat;
            tabs.querySelectorAll('.cat-tab').forEach(b => b.classList.toggle('active', b === btn));
            aplicarFiltros();
        });
    });
}

function aplicarFiltros() {
    let lista = productos;
    if (categoriaActiva) {
        lista = lista.filter(p => (p.categoria_nombre || 'Sin categoría') === categoriaActiva);
    }
    if (textoBusqueda) {
        lista = lista.filter(p =>
            p.nombre.toLowerCase().includes(textoBusqueda) ||
            (p.codigo && p.codigo.toLowerCase().includes(textoBusqueda))
        );
    }
    renderizarProductos(lista);
}

function renderizarProductos(lista) {
    const grid = document.getElementById('productsGrid');
    grid.innerHTML = '';

    lista.forEach(p => {
        const card = document.createElement('div');
        card.className = 'product-card';
        if (p.stock <= 0) {
            card.style.opacity = '0.5';
            card.style.pointerEvents = 'none';
        }

        const emojis = ['🍎','🥩','🥤','🥦','🍞','🧀','🍺','🍫','🥫','🧼','🥛','🥕'];
        const emoji = emojis[p.id_producto % emojis.length];
        const imgDisplay = p.imagen_url ? `<img src="${p.imagen_url}" alt="${p.nombre}" style="max-width: 40px; max-height: 40px; display: block; margin: 0 auto 10px auto;">` : `<span class="product-img">${emoji}</span>`;
        const badgePersonalizable = p.tiene_personalizacion ? '<div style="font-size:10px;color:#0b5cff;font-weight:600;">✎ Personalizable</div>' : '';

        card.innerHTML = `
            ${imgDisplay}
            <div class="product-title">${p.nombre}</div>
            <div class="product-price">C$ ${p.precio_venta.toFixed(2)}</div>
            ${p.stock <= 0 ? '<div style="color:red; font-size: 10px; text-align:center; font-weight:bold;">Agotado</div>' : `<div style="font-size: 10px; color: #6a768d; text-align:center;">Stock: ${p.stock}</div>`}
            ${badgePersonalizable}
        `;

        if (p.stock > 0) {
            card.addEventListener('click', () => onProductoClick(p));
        }

        grid.appendChild(card);
    });
}

// ---- CARRITO ----

function onProductoClick(producto) {
    if (producto.tiene_personalizacion) {
        abrirModalPersonalizacion(producto);
    } else {
        agregarAlCarrito(producto, [], [], null);
    }
}

function claveCarrito(id_producto, comentario) {
    return id_producto + '|' + (comentario || '');
}

function agregarAlCarrito(producto, excluidos, opciones, comentario) {
    const key = claveCarrito(producto.id_producto, comentario);
    const existente = cart.find(item => item.key === key);
    if (existente) {
        if (existente.cantidad < producto.stock) {
            existente.cantidad += 1;
        } else {
            showCustomAlert('Stock insuficiente');
            return;
        }
    } else {
        cart.push({
            key: key,
            id_producto: producto.id_producto,
            nombre: producto.nombre,
            precio: producto.precio_venta,
            cantidad: 1,
            stock: producto.stock,
            excluidos: excluidos || [],
            opciones: opciones || [],
            comentario: comentario || null,
        });
    }
    renderizarCarrito();
}

function modificarCantidad(key, delta) {
    const item = cart.find(i => i.key === key);
    if (item) {
        item.cantidad += delta;
        if (item.cantidad <= 0) {
            cart = cart.filter(i => i.key !== key);
        } else if (item.cantidad > item.stock) {
            item.cantidad = item.stock;
            showCustomAlert('Stock insuficiente');
        }
        renderizarCarrito();
    }
}

function eliminarDelCarrito(key) {
    cart = cart.filter(i => i.key !== key);
    renderizarCarrito();
}

function getSubtotal() {
    let subtotal = 0;
    cart.forEach(item => subtotal += item.precio * item.cantidad);
    return subtotal;
}

function renderizarCarrito() {
    const cartItemsDiv = document.getElementById('cartItems');
    cartItemsDiv.innerHTML = '';

    let subtotal = getSubtotal();

    cart.forEach(item => {
        const itemTotal = item.precio * item.cantidad;
        const div = document.createElement('div');
        div.className = 'cart-item';
        const notaHtml = item.comentario
            ? `<div class="cart-item-note">✎ ${escapeHtml(item.comentario)}</div>` : '';
        // La key se pasa por data-key (atributo, escapado por escapeHtml) y
        // no metida cruda dentro del string de JS del onclick: un
        // nombre/comentario de producto con una comilla ya no rompe fuera
        // del atributo.
        div.innerHTML = `
            <div>
                <strong>${escapeHtml(item.nombre)}</strong><br>
                <span style="color:#6a768d;">C$ ${item.precio.toFixed(2)}</span>
            </div>
            <div class="qty-control">
                <button class="qty-btn" data-key="${escapeHtml(item.key)}" onclick="modificarCantidad(this.dataset.key, -1)">-</button>
                <span>${item.cantidad}</span>
                <button class="qty-btn" data-key="${escapeHtml(item.key)}" onclick="modificarCantidad(this.dataset.key, 1)">+</button>
            </div>
            <div style="text-align: right; font-weight: bold;">C$ ${itemTotal.toFixed(2)}</div>
            <div style="text-align: right;">
                <button class="btn-icon delete" data-key="${escapeHtml(item.key)}" onclick="eliminarDelCarrito(this.dataset.key)">🗑️</button>
            </div>
            ${notaHtml}
        `;
        cartItemsDiv.appendChild(div);
    });

    descuentoAplicado = subtotal * (descuentoPct / 100);

    document.getElementById('subtotalDisplay').textContent = `C$ ${subtotal.toFixed(2)}`;
    const discountDisplay = document.getElementById('discountDisplay');
    if (discountDisplay) {
        discountDisplay.textContent = descuentoPct > 0
            ? `${descuentoPct}% (− C$ ${descuentoAplicado.toFixed(2)})`
            : 'C$ 0.00';
    }

    let total = subtotal - descuentoAplicado;
    if (total < 0) total = 0;
    document.getElementById('totalDisplay').textContent = `C$ ${total.toFixed(2)}`;
    document.getElementById('chargeBtn').textContent = `Cobrar C$ ${total.toFixed(2)}`;
}

function cancelarVenta() {
    if (cart.length === 0) return;
    showCustomConfirm('¿Está seguro de cancelar la venta?', () => {
        cart = [];
        descuentoPct = 0;
        descuentoAplicado = 0;
        propinaManual = null;
        renderizarCarrito();
    });
}

// ---- LOGICA DEL MODAL DE PERSONALIZACIÓN ----

async function abrirModalPersonalizacion(producto) {
    pzProductoActual = producto;
    document.getElementById('pzTitulo').textContent = 'Personalizar: ' + producto.nombre;
    document.getElementById('pzGrupos').innerHTML = '<p style="font-size:13px;color:#6a768d;">Cargando…</p>';
    document.getElementById('pzExcluibles').innerHTML = '';
    document.getElementById('personalizacionModal').style.display = 'flex';

    try {
        const datos = await fetch(`/ventas/api/personalizacion/${producto.id_producto}`).then(r => r.json());
        pzDatosActuales = datos;
        renderizarModalPersonalizacion(datos);
    } catch (error) {
        console.error('Error cargando personalización:', error);
        cerrarModalPersonalizacion();
        agregarAlCarrito(producto, [], [], null);
    }
}

function renderizarModalPersonalizacion(datos) {
    const gruposDiv = document.getElementById('pzGrupos');
    gruposDiv.innerHTML = (datos.grupos || []).map(g => `
        <div class="pz-group" data-grupo="${g.id_grupo}">
            <h4>${g.nombre}${g.obligatorio ? ' <span style="color:#e74c3c;">*</span>' : ' <span style="opacity:.5;font-weight:400;">(opcional)</span>'}</h4>
            ${g.items.map((it, idx) => `
                <label class="pz-option ${!it.disponible ? 'disabled' : ''}">
                    <input type="radio" name="pz-grupo-${g.id_grupo}" value="${it.id_item}"
                        ${(it.es_default || (idx === 0 && !g.items.some(i => i.es_default))) && it.disponible ? 'checked' : ''}
                        ${!it.disponible ? 'disabled' : ''}>
                    ${it.nombre}${!it.disponible ? ' — sin stock' : ''}
                </label>
            `).join('')}
        </div>
    `).join('');

    const excDiv = document.getElementById('pzExcluibles');
    const excluibles = datos.ingredientes_excluibles || [];
    excDiv.innerHTML = excluibles.length ? `
        <div class="pz-group">
            <h4>Ingredientes</h4>
            ${excluibles.map(ing => `
                <label class="pz-option">
                    <input type="checkbox" class="pz-exc" value="${ing.id_producto}" checked>
                    ${ing.nombre}
                </label>
            `).join('')}
        </div>
    ` : '';
}

function cerrarModalPersonalizacion() {
    document.getElementById('personalizacionModal').style.display = 'none';
    pzProductoActual = null;
    pzDatosActuales = null;
}

function confirmarPersonalizacion() {
    if (!pzProductoActual) return;

    // Validar que cada grupo obligatorio tenga una opción elegida.
    for (const g of (pzDatosActuales.grupos || [])) {
        if (!g.obligatorio) continue;
        const marcado = document.querySelector(`input[name="pz-grupo-${g.id_grupo}"]:checked`);
        if (!marcado) {
            showCustomAlert(`Elige una opción de "${g.nombre}"`);
            return;
        }
    }

    const opciones = [];
    const nombresOpciones = [];
    (pzDatosActuales.grupos || []).forEach(g => {
        const marcado = document.querySelector(`input[name="pz-grupo-${g.id_grupo}"]:checked`);
        if (marcado) {
            opciones.push(parseInt(marcado.value));
            const item = g.items.find(i => i.id_item === parseInt(marcado.value));
            if (item) nombresOpciones.push(item.nombre);
        }
    });

    const excluidos = [];
    const nombresExcluidos = [];
    document.querySelectorAll('.pz-exc').forEach(chk => {
        if (!chk.checked) {
            excluidos.push(parseInt(chk.value));
            const ing = (pzDatosActuales.ingredientes_excluibles || []).find(i => i.id_producto === parseInt(chk.value));
            if (ing) nombresExcluidos.push(ing.nombre);
        }
    });

    let comentario = '';
    if (nombresExcluidos.length) comentario += 'Sin ' + nombresExcluidos.join(', ');
    if (nombresOpciones.length) comentario += (comentario ? ' · ' : '') + nombresOpciones.join(' · ');

    const producto = pzProductoActual;
    cerrarModalPersonalizacion();
    agregarAlCarrito(producto, excluidos, opciones, comentario || null);
}

// ---- LOGICA DEL MODAL DE CHECKOUT ----

function abrirModalCheckout() {
    if (cart.length === 0) {
        showCustomAlert('El carrito está vacío');
        return;
    }

    // Fecha y Hora
    const now = new Date();
    document.getElementById('modalDate').textContent = now.toLocaleString();

    // Llenar Items
    const modalItems = document.getElementById('modalItems');
    modalItems.innerHTML = '';
    cart.forEach(item => {
        const div = document.createElement('div');
        div.style.marginBottom = '4px';
        const nota = item.comentario ? `<div style="font-size:11px;color:#e67e22;">✎ ${escapeHtml(item.comentario)}</div>` : '';
        div.innerHTML = `<div style="display:flex;justify-content:space-between;"><span>${item.cantidad}x ${escapeHtml(item.nombre)}</span> <span>C$ ${(item.precio * item.cantidad).toFixed(2)}</span></div>${nota}`;
        modalItems.appendChild(div);
    });

    // Reset Propina manual si el carrito cambió (opcional), aquí lo mantenemos
    document.getElementById('propinaSwitch').checked = true; // Por defecto activo como pidió el usuario
    document.getElementById('modalEfectivoRecibido').value = '0';
    document.getElementById('modalNotas').value = '';

    recalcularTotalesModal();

    document.getElementById('checkoutModal').style.display = 'flex';
}

// Muestra el bloque de efectivo/cambio solo si el metodo de pago actual es
// Efectivo, y recalcula la diferencia contra el total del modal.
function actualizarCambio() {
    const metodo = document.getElementById('paymentMethod').value;
    const seccion = document.getElementById('efectivoSection');
    const btnConfirmar = document.getElementById('confirmCheckoutBtn');
    if (metodo !== 'Efectivo') {
        seccion.style.display = 'none';
        if (btnConfirmar) btnConfirmar.disabled = false;
        return;
    }
    seccion.style.display = 'block';

    const total = parseFloat(document.getElementById('modalTotal').textContent.replace('C$', '').trim()) || 0;
    const recibido = parseFloat(document.getElementById('modalEfectivoRecibido').value) || 0;
    const diferencia = recibido - total;

    document.getElementById('modalCambioLabel').textContent = diferencia < 0 ? 'Falta:' : 'Cambio a entregar:';
    document.getElementById('modalCambio').textContent = 'C$ ' + Math.abs(diferencia).toFixed(2);
    document.getElementById('modalCambio').style.color = diferencia < 0 ? '#c0392b' : '#1abc9c';

    if (btnConfirmar) btnConfirmar.disabled = diferencia < 0;
}

function cerrarModalCheckout() {
    document.getElementById('checkoutModal').style.display = 'none';
}

function recalcularTotalesModal() {
    let subtotal = getSubtotal();
    descuentoAplicado = subtotal * (descuentoPct / 100);
    let baseTotal = subtotal - descuentoAplicado;
    if (baseTotal < 0) baseTotal = 0;

    const applyPropina = document.getElementById('propinaSwitch').checked;

    if (applyPropina) {
        if (propinaManual !== null) {
            propinaAplicada = propinaManual;
        } else {
            propinaAplicada = baseTotal * 0.10; // 10% por defecto
        }
    } else {
        propinaAplicada = 0.0;
    }

    let finalTotal = baseTotal + propinaAplicada;

    document.getElementById('modalSubtotal').textContent = `C$ ${subtotal.toFixed(2)}`;
    document.getElementById('modalDiscount').textContent = descuentoPct > 0
        ? `${descuentoPct}% (- C$ ${descuentoAplicado.toFixed(2)})`
        : '- C$ 0.00';
    document.getElementById('modalPropina').textContent = `+ C$ ${propinaAplicada.toFixed(2)}`;
    document.getElementById('modalTotal').textContent = `C$ ${finalTotal.toFixed(2)}`;
    actualizarCambio();
}

// ---- LOGICA DEL MODAL DE DESCUENTO ----

function abrirModalDescuento() {
    document.getElementById('modalDiscountInput').value = descuentoPct;
    document.getElementById('discountModal').style.display = 'flex';
}

function cerrarModalDescuento() {
    document.getElementById('discountModal').style.display = 'none';
}

function aplicarDescuento() {
    let val = parseFloat(document.getElementById('modalDiscountInput').value);
    if (isNaN(val) || val < 0) val = 0;
    if (val > 100) {
        showCustomAlert("El descuento no puede ser mayor al 100%.");
        val = 100;
    }

    descuentoPct = val;
    cerrarModalDescuento();
    recalcularTotalesModal();
    renderizarCarrito(); // Para actualizar la vista principal de atrás
}

// ---- LOGICA DEL MODAL DE PROPINA ----

function abrirModalPropina() {
    document.getElementById('modalPropinaInput').value = propinaAplicada.toFixed(2);
    document.getElementById('propinaModal').style.display = 'flex';
}

function cerrarModalPropina() {
    document.getElementById('propinaModal').style.display = 'none';
}

function aplicarPropina() {
    let val = parseFloat(document.getElementById('modalPropinaInput').value);
    if (isNaN(val) || val < 0) val = 0;

    propinaManual = val;
    document.getElementById('propinaSwitch').checked = true; // Activar switch si editó la propina
    cerrarModalPropina();
    recalcularTotalesModal();
}

// ---- CONFIRMAR COBRO ----

async function confirmarCobro() {
    let methodValue = document.getElementById('paymentMethod').value;
    let montoRecibido = 0;
    if (methodValue === 'Tarjeta') {
        const selectedBank = document.querySelector('input[name="bankSelect"]:checked').value;
        methodValue = `Tarjeta ${selectedBank}`;
    } else if (methodValue === 'Efectivo') {
        const total = parseFloat(document.getElementById('modalTotal').textContent.replace('C$', '').trim()) || 0;
        montoRecibido = parseFloat(document.getElementById('modalEfectivoRecibido').value) || 0;
        if (montoRecibido < total) {
            showCustomAlert('El efectivo recibido es menor al total a pagar.');
            return;
        }
    }

    const payload = {
        cart: cart.map(item => ({
            id_producto: item.id_producto,
            cantidad: item.cantidad,
            precio: item.precio,
            excluidos: item.excluidos,
            opciones: item.opciones,
            comentario: item.comentario,
        })),
        descuento: descuentoAplicado,
        propina: propinaAplicada,
        metodo_pago: methodValue,
        monto_recibido: montoRecibido,
        id_cliente: document.getElementById('clientSelect').value || null,
        notas: document.getElementById('modalNotas').value,
    };

    const btn = document.getElementById('confirmCheckoutBtn');
    btn.disabled = true;
    btn.textContent = 'Procesando...';

    try {
        const response = await fetch('/ventas/api/cobrar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.success) {
            cerrarModalCheckout();

            // Mostrar modal de éxito con los datos de la venta
            const totalPagado = document.getElementById('modalTotal').textContent;
            showSuccessModal(result.venta_id, totalPagado, result.cambio || 0);

            // Limpiar carrito
            cart = [];
            descuentoPct = 0;
            descuentoAplicado = 0;
            propinaAplicada = 0;
            propinaManual = null;
            renderizarCarrito();
            cargarProductos();
        } else {
            showCustomAlert('Error al cobrar: ' + result.message);
        }
    } catch (error) {
        console.error('Error en cobro:', error);
        showCustomAlert('Ocurrió un error al procesar la venta');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Registrar Venta';
    }
}

function showSuccessModal(ventaId, totalDisplay, cambio) {
    // Rellenar info de la venta
    document.getElementById('successVentaNum').textContent = `#${ventaId}`;
    document.getElementById('successTotal').textContent = totalDisplay;
    // Guardar el id en el botón de imprimir
    document.getElementById('successPrintBtn').dataset.ventaId = ventaId;

    const filaCambio = document.getElementById('successCambioRow');
    if (cambio && cambio > 0) {
        document.getElementById('successCambio').textContent = 'C$ ' + cambio.toFixed(2);
        filaCambio.style.display = 'flex';
    } else {
        filaCambio.style.display = 'none';
    }

    // Mostrar el modal
    const modal = document.getElementById('successModal');
    modal.style.display = 'flex';
}
