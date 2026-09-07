/* ==========================================================================
   pagination.js — paginador generico para las tablas/listas del sistema.
   Uso tipico dentro de una funcion renderizarTabla():

       const pag = crearPaginador('paginacionVentas', 20);
       ...
       const filtrados = lista.filter(...);
       const pagina = pag.paginar(filtrados, renderizarTabla);
       pagina.forEach(item => { ... construir fila ... });

   `crearPaginador` guarda su estado (pagina actual) en el propio objeto,
   asi que sobrevive entre llamadas a renderizarTabla mientras no se llame
   a `.reset()` (usar reset() cuando cambian los filtros/busqueda, para
   volver siempre a la pagina 1 con el nuevo resultado).
   ========================================================================== */
function crearPaginador(contenedorId, porPagina) {
    porPagina = porPagina || 20;
    let pagina = 1;

    function pintar(totalItems, onCambiar) {
        const el = document.getElementById(contenedorId);
        if (!el) return;
        const totalPaginas = Math.max(1, Math.ceil(totalItems / porPagina));
        if (pagina > totalPaginas) pagina = totalPaginas;
        if (pagina < 1) pagina = 1;

        if (totalItems <= porPagina) {
            // No hace falta paginar -- no se satura la vista con controles inutiles.
            el.innerHTML = '';
            return;
        }

        el.innerHTML = `
            <button type="button" class="page-btn" ${pagina <= 1 ? 'disabled' : ''}>‹ Anterior</button>
            <span class="page-info">Página ${pagina} de ${totalPaginas} · ${totalItems} registro${totalItems === 1 ? '' : 's'}</span>
            <button type="button" class="page-btn" ${pagina >= totalPaginas ? 'disabled' : ''}>Siguiente ›</button>
        `;
        const [btnPrev, , btnNext] = el.children;
        btnPrev.addEventListener('click', () => { if (pagina > 1) { pagina--; onCambiar(); } });
        btnNext.addEventListener('click', () => { if (pagina < totalPaginas) { pagina++; onCambiar(); } });
    }

    return {
        get pagina() { return pagina; },
        reset() { pagina = 1; },
        /** Recorta `items` a la pagina actual y pinta los controles debajo. */
        paginar(items, onCambiar) {
            pintar(items.length, onCambiar);
            const inicio = (pagina - 1) * porPagina;
            return items.slice(inicio, inicio + porPagina);
        },
    };
}
