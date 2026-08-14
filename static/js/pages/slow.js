//static/js/pages/slow.js
import { esc, formatNum } from '../helpers.js';

let _lastSlowRows = [];

export async function loadSlowQueries() {
    loadDropdowns();
    await fetchAndRender();
}

async function fetchAndRender() {
    const body = document.getElementById('slowBody');
    body.innerHTML = `<tr><td colspan="10" class="empty-state"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Cargando...</td></tr>`;

    const params = new URLSearchParams();
    
    const minTime = document.getElementById('slowMinTime').value;
    if (minTime) params.set('min_time', minTime);

    const db = document.getElementById('slowDb').value;
    if (db) params.set('db', db);

    const dateFrom = document.getElementById('slowDate').value;
    if (dateFrom) params.set('date_from', dateFrom);

    try {
        const r = await fetch('/api/slow-queries?' + params);
        const res = await r.json();
        
        // 🆕 VERIFICAR ERROR DE PERMISOS
        if (res.permission_error) {
            body.innerHTML = `
                <tr>
                    <td colspan="10" class="empty-state">
                        <div style="padding:20px;">
                            <i class="bi bi-shield-x" style="font-size:40px;color:var(--warning);display:block;margin-bottom:12px"></i>
                            <p style="font-size:14px;color:var(--warning);margin-bottom:8px;font-weight:600">
                                Sin acceso a consultas
                            </p>
                            <p style="font-size:12.5px;color:var(--text-secondary);max-width:500px;margin:0 auto;line-height:1.5">
                                ${esc(res.permission_error)}
                            </p>
                        </div>
                    </td>
                </tr>`;
            return;
        }
        
        renderTable(res.data || []);
    } catch (e) {
        console.error('Error cargando slow queries:', e);
        body.innerHTML = `<tr><td colspan="10" class="empty-state"><i class="bi bi-exclamation-triangle"></i><p>Error al cargar</p></td></tr>`;
    }
}

// 🆕 NUEVA FUNCIÓN: Formatea el tiempo con decimales inteligentes
function formatTime(seconds) {
    if (seconds === null || seconds === undefined) return { value: '—', unit: '', color: 'var(--text-primary)' };
    
    const s = parseFloat(seconds);
    
    // Colorear según duración
    const color = s >= 10 ? 'var(--danger)' : s >= 5 ? 'var(--warning)' : 'var(--text-primary)';
    
    // Mostrar en segundos con 3 decimales (siempre)
    return {
        value: s.toFixed(3),
        unit: 's',
        color: color
    };
}

function renderTable(rows) {
    _lastSlowRows = rows;
    const body = document.getElementById('slowBody');

    if (!rows.length) {
        body.innerHTML = `<tr><td colspan="10" class="empty-state"><i class="bi bi-hourglass-split"></i><p>Sin consultas lentas registradas (>= ${document.getElementById('slowMinTime').value}s)</p></td></tr>`;
        return;
    }

    body.innerHTML = rows.map((q, i) => {
        const idx = i + 1;
        
        // ✅ USAR CAMPOS DIRECTOS: username y client_ip
        const user = q.username || '—';
        const ip = q.client_ip || '—';
        
        // 🆕 USAR formatTime en lugar de toFixed(0)
        const timeInfo = formatTime(q.query_time);

        const ts = fmtTS(q.start_time);

        return `<tr>
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${idx}</td>
            <td><code class="sql-snippet">${esc(truncateSQL(q.sql_text))}</code></td>
            <td><span style="color:${timeInfo.color};font-weight:700;font-family:'Space Grotesk',monospace;font-size:13px">${timeInfo.value} ${timeInfo.unit}</span></td>
            <td style="font-size:12.5px">${esc(user)}</td>
            <td style="font-size:12px"><code>${esc(ip)}</code></td>
            <td class="fd" style="font-weight:600">${formatNum(q.rows_examined || 0)}</td>
            <td class="text-secondary">${formatNum(q.rows_sent || 0)}</td>
            <td><span class="bs bs-i">${esc(q.db || '—')}</span></td>
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${ts}</td>
            <td><button class="bsa" onclick="window.showSlowDetail(${i})"><i class="bi bi-eye"></i></button></td>
        </tr>`;
    }).join('');
}

/* ── DETAIL MODAL ── */
window.showSlowDetail = function (index) {
    const q = _lastSlowRows[index];
    if (!q) return;

    const idx = index + 1;
    
    // ✅ USAR CAMPOS DIRECTOS: username y client_ip
    const user = q.username || '—';
    const ip = q.client_ip || '—';
    
    // 🆕 USAR formatTime también en el modal
    const timeInfo = formatTime(q.query_time);
    const lockMs = q.lock_time ? (q.lock_time * 1000).toFixed(2) : '—';

    document.getElementById('mTitle').innerHTML = `<i class="bi bi-hourglass-split me-2" style="color:var(--warning)"></i>Consulta Lenta #${idx}`;
    document.getElementById('mBody').innerHTML = `
        <div class="row g-3 mb-3">
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Usuario</small><span class="fd" style="font-weight:700;font-size:18px">${esc(user)}</span></div>
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Tiempo Total</small><span style="font-size:20px;font-weight:800;color:${timeInfo.color};font-family:'Space Grotesk',monospace">${timeInfo.value} ${timeInfo.unit}</span></div>
        </div>
        <div class="row g-3 mb-3">
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Base de Datos</small><code style="font-size:15px;color:var(--accent)">${esc(q.db || '—')}</code></div>
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">IP Cliente</small><code style="font-size:13px">${esc(ip)}</code></div>
        </div>
        <div class="row g-3 mb-3">
            <div class="col-4"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Fecha y Hora</small><span style="font-size:13px">${q.start_time}</span></div>
            <div class="col-4"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Lock Time</small><span style="font-size:13px">${lockMs} ms</span></div>
            <div class="col-4"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Estado</small><span class="bs bs-w" style="font-size:12px;padding:5px 12px">Lenta</span></div>
        </div>
        <div>
            <label style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:6px">Análisis de Rendimiento</label>
            <div class="codeb" style="font-size:12px;color:var(--text-secondary)">Rows Examined: ${formatNum(q.rows_examined || 0)}
Rows Sent: ${formatNum(q.rows_sent || 0)}</div>
        </div>
        <div style="margin-top:14px">
            <label style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:6px">SQL Query</label>
            <pre style="background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-size:12.5px;color:#e2e8f0;max-height:350px;overflow:auto;margin:0;white-space:pre-wrap;word-break:break-all;font-family:'Fira Code',monospace;line-height:1.6">${esc(q.sql_text)}</pre>
        </div>`;

    const copyBtn = document.getElementById('copyBtn');
    copyBtn.onclick = () => {
        navigator.clipboard.writeText(q.sql_text);
        copyBtn.innerHTML = '<i class="bi bi-check me-1"></i>Copiado';
        setTimeout(() => { copyBtn.innerHTML = '<i class="bi bi-clipboard me-1"></i>Copiar SQL'; }, 2000);
    };

    new bootstrap.Modal(document.getElementById('detailModal')).show();
};

/* ── DROPDOWNS ── */
async function loadDropdowns() {
    try {
        const [dRes, uRes] = await Promise.all([
            fetch('/api/slow-queries/databases'),
            fetch('/api/slow-queries/users')
        ]);

        const dbs = await dRes.json();
        const users = await uRes.json();
        
        const dSel = document.getElementById('slowDb');
        const cd = dSel.value;
        dSel.innerHTML = '<option value="">Todas</option>' + dbs.map(d => `<option value="${esc(d)}"${d === cd ? ' selected' : ''}>${esc(d)}</option>`).join('');
    } catch (e) {
        console.error('Error cargando dropdowns:', e);
    }
}

/* ── CLEAR HISTORY ── */
export async function clearSlowHistory() {
    if (!confirm('¿Limpiar todo el historial de consultas lentas?')) return;
    try {
        const r = await fetch('/api/slow-queries', { method: 'DELETE' });
        if (r.ok) {
            document.getElementById('slowBody').innerHTML = `<tr><td colspan="10" class="empty-state"><i class="bi bi-hourglass-split"></i><p>Historial limpiado</p></td></tr>`;
            const { showToast } = await import('../helpers.js');
            showToast('Historial de consultas lentas limpiado');
        }
    } catch (e) {
        console.error(e);
    }
}

/* ── HELPERS ── */
function parseUserHost(uh) {
    // Legacy: mantener por compatibilidad pero ya no se usa
    if (!uh) return { user: '—', host: '—' };
    const um = uh.match(/^(\w+)/);
    const im = uh.match(/\[([^\]]+)\]/);
    const hm = uh.match(/@([^\[]+)/);
    return {
        user: um ? um[1] : '—',
        host: im ? im[1] : (hm ? hm[1].trim() : '—')
    };
}

function truncateSQL(sql) {
    if (!sql) return '—';
    const c = sql.replace(/\s+/g, ' ').trim();
    return c.length <= 90 ? c : c.substring(0, 90) + '...';
}

function fmtTS(ts) {
    if (!ts) return '—';
    try {
        const cleanTs = ts.substring(0, 19);
        const d = new Date(cleanTs + 'Z');
        if (isNaN(d.getTime())) return ts;
        return d.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return ts; }
}