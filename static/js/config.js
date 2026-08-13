// static/js/config.js
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
            // Conexión MySQL
            if (cfg.mysql) {
                document.getElementById('cfgHost').value = cfg.mysql.host || 'localhost';
                document.getElementById('cfgPort').value = cfg.mysql.port || 3306;
                document.getElementById('cfgUser').value = cfg.mysql.user || 'root';
                document.getElementById('cfgPass').value = cfg.mysql.password || '';
            }
            if (cfg.refresh_interval) {
                document.getElementById('cfgInterval').value = cfg.refresh_interval;
            }
            
            // Consultas Lentas
            if (cfg.slow_query_threshold !== undefined) {
                document.getElementById('cfgSlowThreshold').value = cfg.slow_query_threshold;
            }
            if (cfg.slow_log_enabled !== undefined) {
                document.getElementById('cfgSlowEnabled').checked = cfg.slow_log_enabled;
            }
        })
        .catch(() => {
            // Si falla, dejar los valores por defecto
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
            // Si falla no es crítico
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

/* ═══════════════════════════════════════
   Configuración de Consultas Lentas
   (simplificada: solo umbral + switch)
   ═══════════════════════════════════════ */

async function saveSlowLogConfig() {
    let threshold = parseFloat(document.getElementById('cfgSlowThreshold').value);
    
    // ═══ VALIDACIÓN EN EL FRONTEND ═══
    if (isNaN(threshold) || threshold < 1) {
        showToast('❌ El umbral debe ser >= 1 segundo');
        document.getElementById('cfgSlowThreshold').value = 1;
        return;
    }
    if (threshold > 60) {
        showToast('❌ El umbral debe ser <= 60 segundos');
        document.getElementById('cfgSlowThreshold').value = 60;
        return;
    }
    
    const config = {
        threshold: threshold,
        enabled: document.getElementById('cfgSlowEnabled').checked,
        log_no_indexes: true,
    };
    
    try {
        const response = await fetch('/api/query-config/slow-log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast(`✅ Umbral actualizado a ${result.config.threshold}s`);
        } else {
            showToast(`❌ Error: ${result.error || 'Error desconocido'}`);
        }
    } catch (error) {
        showToast(`❌ Error de red: ${error.message}`);
    }
}



// Función auxiliar para mostrar toast (si no está disponible globalmente)
if (typeof showToast === 'undefined') {
    function showToast(message) {
        const toastBody = document.getElementById('toastBd');
        const toastEl = document.getElementById('toastEl');
        if (toastBody && toastEl) {
            toastBody.innerHTML = '<i class="bi bi-info-circle me-2"></i>' + message;
            const toast = new bootstrap.Toast(toastEl);
            toast.show();
        } else {
            alert(message);
        }
    }
}