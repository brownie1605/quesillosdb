/* Inventario: secciones "Consumo" (cuanto se uso al vender, por dia o mes)
   y "Bajas" (merma, vencido, dañado...). La seccion "Existencias" es la
   tabla de siempre (inventario.js). */
(function () {
    'use strict';

    const hoyISO = () => {
        const d = new Date();
        return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    };
    const primeroDelMes = () => hoyISO().slice(0, 8) + '01';
    const hace30 = () => {
        const d = new Date(Date.now() - 29 * 86400000);
        return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    };
    const num = (n) => Number(n).toLocaleString('es-NI', { maximumFractionDigits: 2 });
    const tipoLabel = { insumo: 'Insumo', final: 'Producto final', material: 'Material' };
    let consumoActual = null;
    let cargadoConsumo = false, cargadoBajas = false;

    // ---------------------------------------------------------------- pestañas
    document.querySelectorAll('.btn-seccion-inv').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.btn-seccion-inv').forEach(b => b.classList.toggle('activo', b === btn));
            ['seccionExistencias', 'seccionConsumo', 'seccionBajas'].forEach(id => {
                document.getElementById(id).style.display = id === btn.dataset.seccion ? '' : 'none';
            });
            if (btn.dataset.seccion === 'seccionConsumo' && !cargadoConsumo) { cargadoConsumo = true; cargarConsumo(); }
            if (btn.dataset.seccion === 'seccionBajas' && !cargadoBajas) { cargadoBajas = true; iniciarBajas(); }
        });
    });

    // ---------------------------------------------------------------- consumo
    const cAgrupar = document.getElementById('consumoAgrupar');
    const cInicio = document.getElementById('consumoInicio');
    const cFin = document.getElementById('consumoFin');
    const cTipo = document.getElementById('consumoTipo');
    cInicio.value = hoyISO();
    cFin.value = hoyISO();

    cAgrupar.addEventListener('change', () => {
        // Por mes, por defecto se ve el mes en curso.
        if (cAgrupar.value === 'mes' && cInicio.value === cFin.value) cInicio.value = primeroDelMes();
        cargarConsumo();
    });
    [cInicio, cFin].forEach(el => el.addEventListener('change', cargarConsumo));
    cTipo.addEventListener('change', pintarConsumo);

    async function cargarConsumo() {
        const params = new URLSearchParams({ agrupar: cAgrupar.value, inicio: cInicio.value, fin: cFin.value });
        try {
            consumoActual = await fetch('/inventario/api/consumo?' + params).then(r => r.json());
        } catch (e) {
            showCustomAlert('No se pudo cargar el consumo');
            return;
        }
        pintarConsumo();
    }

    function pintarConsumo() {
        if (!consumoActual) return;
        const tipo = cTipo.value;
        const filtra = (r) => !tipo || r.tipo_producto === tipo;
        const resumen = consumoActual.resumen.filter(filtra);
        const detalle = consumoActual.detalle.filter(filtra);
        document.getElementById('consumoDetalleTitulo').textContent =
            consumoActual.agrupar === 'mes' ? 'Mes por mes' : 'Día por día';

        document.getElementById('consumoResumen').innerHTML = resumen.length
            ? resumen.map(r => `<tr><td>${escapeHtml(r.producto)}</td><td>${tipoLabel[r.tipo_producto] || ''}</td>
                <td style="text-align:right;font-weight:700;">${num(r.cantidad)} ${escapeHtml(r.unidad || '')}</td></tr>`).join('')
            : '<tr><td colspan="3" class="inv-vacio">No hubo consumo por ventas en este rango.</td></tr>';

        document.getElementById('consumoDetalle').innerHTML = detalle.length
            ? detalle.map(r => `<tr><td>${escapeHtml(r.periodo)}</td><td>${escapeHtml(r.producto)}</td>
                <td style="text-align:right;">${num(r.cantidad)} ${escapeHtml(r.unidad || '')}</td></tr>`).join('')
            : '<tr><td colspan="3" class="inv-vacio">Sin datos.</td></tr>';
    }

    document.getElementById('consumoExportar').addEventListener('click', () => {
        if (!consumoActual || typeof XLSX === 'undefined') return;
        const tipo = cTipo.value;
        const filas = consumoActual.detalle
            .filter(r => !tipo || r.tipo_producto === tipo)
            .map(r => ({ Periodo: r.periodo, Producto: r.producto, Tipo: tipoLabel[r.tipo_producto] || '', Usado: r.cantidad, Unidad: r.unidad || '' }));
        const libro = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(filas), 'Consumo');
        XLSX.writeFile(libro, `consumo_${consumoActual.inicio}_a_${consumoActual.fin}.xlsx`);
    });

    // ---------------------------------------------------------------- bajas
    const bInicio = document.getElementById('bajasInicio');
    const bFin = document.getElementById('bajasFin');
    bInicio.value = hace30();
    bFin.value = hoyISO();
    [bInicio, bFin].forEach(el => el.addEventListener('change', cargarBajas));

    async function iniciarBajas() {
        try {
            const productos = await fetch('/inventario/api/list').then(r => r.json());
            productos.sort((a, b) => a.nombre.localeCompare(b.nombre));
            document.getElementById('bajaProducto').innerHTML =
                '<option value="">Producto…</option>' +
                productos.map(p => `<option value="${p.id_producto}">${escapeHtml(p.nombre)} (hay ${num(p.stock_actual)})</option>`).join('');
        } catch (e) {
            showCustomAlert('No se pudieron cargar los productos');
        }
        await cargarBajas();
    }

    async function cargarBajas() {
        const params = new URLSearchParams({ inicio: bInicio.value, fin: bFin.value });
        let datos;
        try {
            datos = await fetch('/inventario/api/bajas?' + params).then(r => r.json());
        } catch (e) {
            showCustomAlert('No se pudieron cargar las bajas');
            return;
        }
        const selMotivo = document.getElementById('bajaMotivo');
        if (!selMotivo.options.length) {
            selMotivo.innerHTML = datos.motivos.map(m => `<option>${escapeHtml(m)}</option>`).join('');
        }
        document.getElementById('bajasTotal').textContent = 'C$ ' + Number(datos.total_costo).toFixed(2);
        document.getElementById('bajasLista').innerHTML = datos.bajas.length
            ? datos.bajas.map(b => `<tr><td>${escapeHtml(b.fecha)}</td><td>${escapeHtml(b.producto)}</td>
                <td style="text-align:right;">${num(b.cantidad)}</td><td>${escapeHtml(b.motivo)}</td>
                <td style="text-align:right;">C$ ${Number(b.costo).toFixed(2)}</td><td>${escapeHtml(b.usuario)}</td></tr>`).join('')
            : '<tr><td colspan="6" class="inv-vacio">No hay bajas en este rango.</td></tr>';
    }

    document.getElementById('bajaRegistrar').addEventListener('click', async () => {
        const datos = {
            id_producto: document.getElementById('bajaProducto').value,
            cantidad: parseFloat(document.getElementById('bajaCantidad').value) || 0,
            motivo: document.getElementById('bajaMotivo').value,
            detalle: document.getElementById('bajaDetalle').value,
        };
        if (!datos.id_producto) { showCustomAlert('Elige el producto'); return; }
        if (datos.cantidad <= 0) { showCustomAlert('Pon una cantidad mayor a cero'); return; }
        const btn = document.getElementById('bajaRegistrar');
        btn.disabled = true;
        try {
            const r = await fetch('/inventario/api/bajas', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos),
            }).then(x => x.json());
            if (!r.success) { showCustomAlert(r.message || 'No se pudo registrar la baja'); return; }
            showCustomAlert('Baja registrada', false);
            document.getElementById('bajaCantidad').value = '';
            document.getElementById('bajaDetalle').value = '';
            await iniciarBajas();
        } finally {
            btn.disabled = false;
        }
    });
})();
