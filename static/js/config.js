/* ═══════════════════════════════════════
   config.js — Modal de configuración
   Script NORMAL (no module) para que
   onclick del HTML pueda ver las funciones
   ═══════════════════════════════════════ */

let configModalInstance = null;

function showConfigModal() {
    // Cargar valores actuales desde la API
    fetch('/api/config')
        .then(r => r.json())
        .then(cfg => {
            if (cfg.mysql) {
                document.getElementById('cfgHost').value = cfg.mysql.host || 'localhost';
                document.getElementById('cfgPort').value = cfg.mysql.port || 3306;
                document.getElementById('cfgUser').value = cfg.mysql.user || 'root';
                document.getElementById('cfgPass').value = cfg.mysql.password || '';
            }
            if (cfg.refresh_interval) {
                document.getElementById('cfgInterval').value = cfg.refresh_interval;
            }
        })
        .catch(() => {
            // Si falla, dejar los valores por defecto que ya tienen los inputs
        });

    // Ocultar mensajes anteriores
    document.getElementById('cfgError').classList.remove('show');
    document.getElementById('cfgOk').style.display = 'none';
    document.getElementById('cfgSaveText').style.display = '';
    document.getElementById('cfgSaveSpinner').style.display = 'none';

    // Abrir modal
    if (!configModalInstance) {
        configModalInstance = new bootstrap.Modal(document.getElementById('configModal'));
    }
    configModalInstance.show();
}

function closeConfigModal() {
    if (configModalInstance) {
        configModalInstance.hide();
    }
}




async function saveConfig() {
    const errEl = document.getElementById('cfgError');
    const okEl = document.getElementById('cfgOk');
    const txtEl = document.getElementById('cfgSaveText');
    const spnEl = document.getElementById('cfgSaveSpinner');

    errEl.classList.remove('show');
    okEl.style.display = 'none';
    txtEl.style.display = 'none';
    spnEl.style.display = '';

    const payload = {
        mysql: {
            host: document.getElementById('cfgHost').value.trim() || 'localhost',
            port: parseInt(document.getElementById('cfgPort').value) || 3306,
            user: document.getElementById('cfgUser').value.trim() || 'root',
            password: document.getElementById('cfgPass').value,
        },
        refresh_interval: parseFloat(document.getElementById('cfgInterval').value) || 2,
    };

    try {
        const r = await fetch('/api/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!r.ok) {
            const err = await r.json();
            throw new Error(err.detail || 'Error desconocido');
        }

        okEl.style.display = '';
        spnEl.style.display = 'none';
        txtEl.style.display = '';

        // Reiniciar el binlog con la nueva config
        try {
            await fetch('/api/binlog/restart', { method: 'POST' });
        } catch (e) {
            // Si falla no es crítico, el resto funciona
        }

        setTimeout(() => {
            closeConfigModal();
            location.reload();
        }, 1500);

    } catch (e) {
        errEl.textContent = e.message;
        errEl.classList.add('show');
        spnEl.style.display = 'none';
        txtEl.style.display = '';
    }
}


