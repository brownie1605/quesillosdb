/* Boton "Instalar app" (PWA).
   - Chrome/Edge (Android y computadora): abre la ventana de instalacion del
     navegador (evento beforeinstallprompt).
   - iPhone/iPad: Safari no permite instalar con un boton; se muestran los
     pasos (Compartir -> Agregar a inicio).
   - Si ya esta abierta como app instalada, el boton no aparece.
   Los botones son cualquier elemento con la clase .btn-instalar-app
   (ocultos por defecto). */
(function () {
    'use strict';

    const yaInstalada = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    const esIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    let aviso = null;

    const botones = () => document.querySelectorAll('.btn-instalar-app');
    const mostrar = (si) => botones().forEach(b => { b.style.display = si ? '' : 'none'; });

    function pasosIOS() {
        const capa = document.createElement('div');
        capa.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:3000;display:flex;align-items:flex-end;justify-content:center;';
        capa.innerHTML = `
            <div style="background:#fff;color:#3e2723;border-radius:16px 16px 0 0;padding:22px 20px 28px;max-width:420px;width:100%;font-family:inherit;">
                <div style="font-weight:800;font-size:17px;margin-bottom:10px;">Instalar Quesillos POS</div>
                <ol style="margin:0 0 16px;padding-left:20px;line-height:1.7;font-size:15px;">
                    <li>Toca el botón <strong>Compartir</strong> <span style="font-size:18px;">⬆️</span> de Safari.</li>
                    <li>Elige <strong>"Agregar a inicio"</strong>.</li>
                    <li>Toca <strong>Agregar</strong>. Queda un ícono como cualquier app.</li>
                </ol>
                <button type="button" style="width:100%;padding:12px;border:none;border-radius:10px;background:#8B2E2E;color:#fff;font-weight:700;font-size:15px;">Entendido</button>
            </div>`;
        capa.addEventListener('click', (e) => { if (e.target === capa || e.target.tagName === 'BUTTON') capa.remove(); });
        document.body.appendChild(capa);
    }

    async function instalar() {
        if (aviso) {
            aviso.prompt();
            const r = await aviso.userChoice;
            if (r.outcome === 'accepted') mostrar(false);
            aviso = null;
        } else if (esIOS) {
            pasosIOS();
        }
    }

    if (yaInstalada) return;

    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();          // se muestra con nuestro boton
        aviso = e;
        mostrar(true);
    });
    window.addEventListener('appinstalled', () => mostrar(false));

    document.addEventListener('DOMContentLoaded', () => {
        botones().forEach(b => b.addEventListener('click', instalar));
        if (esIOS && window.isSecureContext) mostrar(true);
    });
})();
