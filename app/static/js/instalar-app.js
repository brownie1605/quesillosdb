/* Boton "Instalar app" (PWA).
   - Si el navegador permite instalar con un toque (Chrome/Edge mandan el
     evento beforeinstallprompt), el boton abre esa instalacion.
   - Si no (iPhone, Samsung Internet, Firefox, o Chrome cuando no manda el
     evento porque antes se descarto o ya se instalo), el boton muestra los
     pasos para ese navegador.
   - En el telefono el boton se ve siempre; en computadora solo cuando el
     navegador permite instalar con un toque.
   - Si ya esta abierta como app instalada, no aparece.
   Los botones son cualquier elemento con la clase .btn-instalar-app
   (ocultos por defecto). */
(function () {
    'use strict';

    const ua = navigator.userAgent;
    const yaInstalada = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    const esIOS = /iphone|ipad|ipod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const esTelefono = esIOS || /android|mobile/i.test(ua);
    let aviso = null;

    const botones = () => document.querySelectorAll('.btn-instalar-app');
    const mostrar = (si) => botones().forEach(b => { b.style.display = si ? '' : 'none'; });

    function pasos() {
        if (esIOS) {
            return [
                'Abre esta página en <strong>Safari</strong>.',
                'Toca <strong>Compartir</strong> ⬆️ (abajo, en el centro).',
                'Elige <strong>"Agregar a inicio"</strong> y toca <strong>Agregar</strong>.',
            ];
        }
        if (/samsungbrowser/i.test(ua)) {
            return [
                'Toca el menú <strong>≡</strong> (abajo a la derecha).',
                'Elige <strong>"Agregar página a"</strong> → <strong>"Pantalla de inicio"</strong>.',
            ];
        }
        if (/firefox/i.test(ua)) {
            return [
                'Toca el menú <strong>⋮</strong>.',
                'Elige <strong>"Instalar"</strong> o <strong>"Agregar a pantalla de inicio"</strong>.',
            ];
        }
        return [
            'Toca el menú <strong>⋮</strong> de Chrome (arriba a la derecha).',
            'Elige <strong>"Instalar app"</strong> o <strong>"Agregar a la pantalla principal"</strong>.',
            'Confirma con <strong>Instalar</strong>.',
        ];
    }

    function mostrarPasos() {
        const capa = document.createElement('div');
        capa.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:3000;display:flex;align-items:flex-end;justify-content:center;';
        capa.innerHTML = `
            <div style="background:#fff;color:#3e2723;border-radius:16px 16px 0 0;padding:22px 20px 28px;max-width:420px;width:100%;font-family:inherit;">
                <div style="font-weight:800;font-size:17px;margin-bottom:10px;">Instalar Quesillos POS</div>
                <ol style="margin:0 0 12px;padding-left:20px;line-height:1.7;font-size:15px;">
                    ${pasos().map(p => `<li>${p}</li>`).join('')}
                </ol>
                <p style="margin:0 0 16px;font-size:13px;color:#8d6e63;">Queda un ícono como cualquier app y se abre sin la barra del navegador.</p>
                <button type="button" style="width:100%;padding:12px;border:none;border-radius:10px;background:#8B2E2E;color:#fff;font-weight:700;font-size:15px;">Entendido</button>
            </div>`;
        capa.addEventListener('click', (e) => { if (e.target === capa || e.target.tagName === 'BUTTON') capa.remove(); });
        document.body.appendChild(capa);
    }

    async function instalar() {
        if (aviso) {
            const evento = aviso;
            aviso = null;
            evento.prompt();
            const r = await evento.userChoice;
            if (r.outcome === 'accepted') mostrar(false);
        } else {
            mostrarPasos();
        }
    }

    if (yaInstalada) return;

    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();          // se muestra con nuestro boton
        aviso = e;
        mostrar(true);
    });
    window.addEventListener('appinstalled', () => mostrar(false));

    function iniciar() {
        botones().forEach(b => b.addEventListener('click', instalar));
        if (esTelefono || aviso) mostrar(true);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
})();
