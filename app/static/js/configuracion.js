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
});
