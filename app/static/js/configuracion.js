document.addEventListener('DOMContentLoaded', () => {
    // Theme logic
    const themeToggle = document.getElementById('themeToggle');
    
    // Check saved theme
    if (localStorage.getItem('theme') === 'dark') {
        document.body.classList.add('dark-theme');
        document.documentElement.classList.add('dark-theme');
        themeToggle.checked = true;
    }

    themeToggle.addEventListener('change', (e) => {
        let newTheme = 'light';
        if (e.target.checked) {
            document.body.classList.add('dark-theme');
            document.documentElement.classList.add('dark-theme');
            newTheme = 'dark';
        } else {
            document.body.classList.remove('dark-theme');
            document.documentElement.classList.remove('dark-theme');
        }
        localStorage.setItem('theme', newTheme);
        
        fetch('/configuracion/api/guardar_preferencias', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tema_preferido: newTheme })
        }).catch(err => console.error('Error saving theme', err));
    });

    // --- Color Picker Logic ---
    const btnColorPicker = document.getElementById('btnColorPicker');
    const colorPickerModal = document.getElementById('colorPickerModal');
    const closeColorPicker = document.getElementById('closeColorPicker');
    const colorSwatches = document.querySelectorAll('.color-swatch');
    const customColorPicker = document.getElementById('customColorPicker');

    // Open/Close Modal
    if (btnColorPicker && colorPickerModal) {
        btnColorPicker.addEventListener('click', () => {
            colorPickerModal.style.display = 'flex';
        });
        closeColorPicker.addEventListener('click', () => {
            colorPickerModal.style.display = 'none';
        });
        colorPickerModal.addEventListener('click', (e) => {
            if (e.target === colorPickerModal) {
                colorPickerModal.style.display = 'none';
            }
        });
    }

    // Apply color function
    function applyColor(color) {
        document.documentElement.style.setProperty('--primary-color', color);
        localStorage.setItem('primary-color', color);
        
        fetch('/configuracion/api/guardar_preferencias', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ color_primario: color })
        }).catch(err => console.error('Error saving color', err));
    }

    // Swatches click
    colorSwatches.forEach(swatch => {
        swatch.addEventListener('click', () => {
            const color = swatch.getAttribute('data-color');
            applyColor(color);
        });
    });

    // Custom color picker change
    if (customColorPicker) {
        customColorPicker.addEventListener('input', (e) => {
            applyColor(e.target.value);
        });
    }
    // --------------------------

    // Password Form
    document.getElementById('formPassword').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const actual = document.getElementById('pass_actual').value;
        const nueva = document.getElementById('pass_nueva').value;
        const confirmar = document.getElementById('pass_confirmar').value;

        if (nueva !== confirmar) {
            showCustomAlert('Las contraseñas nuevas no coinciden');
            return;
        }

        try {
            const res = await fetch('/configuracion/api/cambiar_password', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    password_actual: actual,
                    password_nueva: nueva
                })
            });
            const result = await res.json();
            if (result.success) {
                showCustomAlert(result.message, false);
                document.getElementById('formPassword').reset();
            } else {
                showCustomAlert('Error: ' + result.message);
            }
        } catch (error) {
            console.error(error);
            showCustomAlert('Error en el servidor');
        }
    });

    // ---------------------------------------------------------- 2FA
    async function cargarEstado2FA() {
        const r = await fetch('/configuracion/api/2fa/estado').then(r => r.json());
        document.getElementById('twofaOff').style.display = r.habilitado ? 'none' : 'block';
        document.getElementById('twofaOn').style.display = r.habilitado ? 'block' : 'none';
        document.getElementById('twofaSetup').style.display = 'none';
    }

    const btn2faIniciar = document.getElementById('btn2faIniciar');
    if (btn2faIniciar) {
        btn2faIniciar.addEventListener('click', async () => {
            const r = await fetch('/configuracion/api/2fa/iniciar', { method: 'POST' }).then(r => r.json());
            if (!r.success) { showCustomAlert(r.message); return; }
            document.getElementById('twofaQr').src = r.qr;
            document.getElementById('twofaSecreto').textContent = r.secreto;
            document.getElementById('twofa_codigo').value = '';
            document.getElementById('twofaSetup').style.display = 'block';
        });
    }

    const btn2faCancelar = document.getElementById('btn2faCancelar');
    if (btn2faCancelar) {
        btn2faCancelar.addEventListener('click', () => {
            document.getElementById('twofaSetup').style.display = 'none';
        });
    }

    const btn2faConfirmar = document.getElementById('btn2faConfirmar');
    if (btn2faConfirmar) {
        btn2faConfirmar.addEventListener('click', async () => {
            const codigo = document.getElementById('twofa_codigo').value.trim();
            if (codigo.length !== 6) { showCustomAlert('Ingresa el código de 6 dígitos'); return; }
            const r = await fetch('/configuracion/api/2fa/confirmar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ codigo }),
            }).then(r => r.json());
            if (!r.success) { showCustomAlert(r.message); return; }
            document.getElementById('twofaSetup').style.display = 'none';
            document.getElementById('twofaRecoveryLista').innerHTML = r.codigos_recuperacion.map(c => `<div>${c}</div>`).join('');
            document.getElementById('twofaRecovery').style.display = 'block';
        });
    }

    const btn2faRecoveryListo = document.getElementById('btn2faRecoveryListo');
    if (btn2faRecoveryListo) {
        btn2faRecoveryListo.addEventListener('click', () => {
            document.getElementById('twofaRecovery').style.display = 'none';
            cargarEstado2FA();
        });
    }

    const btn2faDesactivar = document.getElementById('btn2faDesactivar');
    if (btn2faDesactivar) {
        btn2faDesactivar.addEventListener('click', () => {
            const password = document.getElementById('twofa_pass_desactivar').value;
            if (!password) { showCustomAlert('Ingresa tu contraseña para desactivar el 2FA'); return; }
            showCustomConfirm('¿Desactivar la verificación en dos pasos?', async () => {
                const r = await fetch('/configuracion/api/2fa/desactivar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password }),
                }).then(r => r.json());
                if (!r.success) { showCustomAlert(r.message); return; }
                document.getElementById('twofa_pass_desactivar').value = '';
                cargarEstado2FA();
            });
        });
    }

    if (document.getElementById('twofaOff')) cargarEstado2FA();
});
