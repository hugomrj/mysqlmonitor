//static/js/pages/recent.js
import { setText, esc, formatNum } from '../helpers.js';

let _lastRecentRows = [];
let _slowThreshold = 3.0; // Umbral por defecto en segundos



export async function loadRecentQueries() {


    const minTimeEl = document.getElementById('recentMinTime');
    const dbEl = document.getElementById('recentDb');
    const userEl = document.getElementById('recentUser');
    
    const minTime = minTimeEl ? parseFloat(minTimeEl.value) || 0 : 0;
    const database = dbEl ? dbEl.value.trim() : '';
    const username = userEl ? userEl.value.trim() : '';
    
    let url = `/api/queries/recent?limit=100`;
    if (minTime > 0) url += `&min_time_ms=${minTime}`;
    if (database) url += `&database=${encodeURIComponent(database)}`;
    if (username) url += `&username=${encodeURIComponent(username)}`;
    
    try {
        const [queriesRes, statsRes] = await Promise.all([
            fetch(url),
            fetch('/api/queries/recent/stats')
        ]);
        
        const queriesData = await queriesRes.json();
        const statsData = await statsRes.json();
        
        const tbody = document.getElementById('recentBody');
        if (!tbody) return;
        
        // 🆕 VERIFICAR ERROR DE PERMISOS
        if (queriesData.permission_error) {
            setText('recentTotal', '0');
            setText('recentAvg', '0');
            setText('recentMax', '0');
            setText('recentMin', '0');
            
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="empty-state">
                        <div style="padding:20px;">
                            <i class="bi bi-shield-x" style="font-size:40px;color:var(--warning);display:block;margin-bottom:12px"></i>
                            <p style="font-size:14px;color:var(--warning);margin-bottom:8px;font-weight:600">
                                Sin acceso a consultas
                            </p>
                            <p style="font-size:12.5px;color:var(--text-secondary);max-width:500px;margin:0 auto;line-height:1.5">
                                ${esc(queriesData.permission_error)}
                            </p>
                        </div>
                    </td>
                </tr>`;
            return;
        }
        
        // Actualizar estadísticas
        setText('recentTotal', statsData.total || 0);
        
        // 🆕 Convertir de ms a segundos con 2 decimales
        const avgSeconds = (statsData.avg_time_ms || 0) / 1000;
        const maxSeconds = (statsData.max_time_ms || 0) / 1000;

        setText('recentAvg', avgSeconds.toFixed(4));
        setText('recentMax', maxSeconds.toFixed(4));

        setText('recentMin', (statsData.min_time_ms || 0).toFixed(2));
        


        if (!queriesData.data || queriesData.data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="empty-state">
                <i class="bi bi-inbox"></i>
                <p>No hay consultas recientes</p>
            </td></tr>`;
            return;
        }
        
        _lastRecentRows = queriesData.data;
        
        tbody.innerHTML = queriesData.data.map((q, i) => {
            const sqlPreview = esc(q.sql_text || '').substring(0, 80);
            const sqlFull = esc(q.sql_text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            
            const ms = parseFloat(q.query_time_ms) || 0;
            const timeInfo = formatTimeWithThreshold(ms, _slowThreshold);
            
            return `
                <tr>
                    <td>${i + 1}</td>
                        <td>
                            <code class="sql-snippet" title="${sqlFull}">${sqlPreview}${sqlPreview.length >= 80 ? '...' : ''}</code>
                        </td>
                    <td><span style="color:${timeInfo.color};font-weight:700;font-family:'Space Grotesk',monospace;font-size:12px">${timeInfo.display}</span></td>
                    <td><small>${esc(q.client_ip || 'unknown')}</small></td>
                    <td>${esc(q.username || '—')}</td>
                    <td>${esc(q.database || '—')}</td>
                    <td>${formatNum(q.rows_examined || 0)}</td>
                    <td>${formatNum(q.rows_sent || 0)}</td>
                    <td><button class="bsa" onclick="window.showRecentDetail(${i})"><i class="bi bi-eye"></i></button></td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Error cargando consultas recientes:', error);
        const tbody = document.getElementById('recentBody');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="9" class="empty-state"><i class="bi bi-exclamation-triangle"></i><p>Error al cargar</p></td></tr>`;
        }
    }
}

// 🆕 NUEVA FUNCIÓN: Formatea tiempo basado en umbral dinámico
function formatTimeWithThreshold(ms, thresholdSeconds) {
    const thresholdMs = thresholdSeconds * 1000;
    const warningMs = (thresholdSeconds - 1) * 1000; // 1 segundo antes del umbral
    
    let display, color;
    
    if (ms >= thresholdMs) {
        // 🔴 Rojo: supera o iguala el umbral
        display = ms.toFixed(2) + ' ms';
        color = 'var(--danger)';
    } else if (ms >= warningMs) {
        // 🟡 Amarillo: entre (umbral-1) y umbral
        display = ms.toFixed(2) + ' ms';
        color = 'var(--warning)';
    } else {
        // 🟢 Verde: por debajo de (umbral-1)
        display = ms < 10 ? ms.toFixed(3) + ' ms' : ms.toFixed(2) + ' ms';
        color = 'var(--success)';
    }
    
    return { display, color };
}

/* ── DETAIL MODAL ── */
window.showRecentDetail = function (index) {
    const q = _lastRecentRows[index];
    if (!q) return;

    const idx = index + 1;
    const ms = parseFloat(q.query_time_ms) || 0;
    const timeInfo = formatTimeWithThreshold(ms, _slowThreshold);

    document.getElementById('mTitle').innerHTML = `<i class="bi bi-clock-history me-2" style="color:var(--info)"></i>Consulta Reciente #${idx}`;
    document.getElementById('mBody').innerHTML = `
        <div class="row g-3 mb-3">
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Usuario</small><span class="fd" style="font-weight:700;font-size:18px">${esc(q.username || '—')}</span></div>
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Tiempo</small><span style="font-size:20px;font-weight:800;color:${timeInfo.color};font-family:'Space Grotesk',monospace">${timeInfo.display}</span></div>
        </div>
        <div class="row g-3 mb-3">
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Base de Datos</small><code style="font-size:15px;color:var(--accent)">${esc(q.database || '—')}</code></div>
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">IP Cliente</small><code style="font-size:13px">${esc(q.client_ip || 'unknown')}</code></div>
        </div>
        <div class="row g-3 mb-3">
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Capturada</small><span style="font-size:13px">${q.timestamp || '—'}</span></div>
            <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Host</small><code style="font-size:13px">${esc(q.client_host || '—')}</code></div>
        </div>
        <div>
            <label style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:6px">Análisis de Rendimiento</label>
            <div class="codeb" style="font-size:12px;color:var(--text-secondary)">Rows Examined: ${formatNum(q.rows_examined || 0)}
Rows Sent: ${formatNum(q.rows_sent || 0)}</div>
        </div>
        <div style="margin-top:14px">
            <label style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:6px">SQL Query</label>
            <pre style="background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-size:12.5px;color:#e2e8f0;max-height:350px;overflow:auto;margin:0;white-space:pre-wrap;word-break:break-all;font-family:'Fira Code',monospace;line-height:1.6">${esc(q.sql_text || '')}</pre>
        </div>`;

    const copyBtn = document.getElementById('copyBtn');
    copyBtn.onclick = () => {
        navigator.clipboard.writeText(q.sql_text || '');
        copyBtn.innerHTML = '<i class="bi bi-check me-1"></i>Copiado';
        setTimeout(() => { copyBtn.innerHTML = '<i class="bi bi-clipboard me-1"></i>Copiar SQL'; }, 2000);
    };

    new bootstrap.Modal(document.getElementById('detailModal')).show();
};

export async function clearRecentQueries() {
    if (!confirm('¿Limpiar el buffer de consultas recientes?')) return;
    
    try {
        const res = await fetch('/api/queries/recent', { method: 'DELETE' });
        const result = await res.json();
        if (result.success) {
            if (typeof showToast === 'function') {
                showToast('✅ Buffer limpiado');
            }
            await loadRecentQueries();
        }
    } catch (error) {
        console.error('Error limpiando buffer:', error);
    }
}

export async function initRecent() {
    // 🆕 Cargar el umbral configurado al iniciar
    await loadSlowThreshold();
    loadRecentQueries();
}

// 🆕 NUEVA FUNCIÓN: Carga el umbral de slow queries desde el backend
async function loadSlowThreshold() {
    try {
        const res = await fetch('/api/query-config/slow-log');
        const data = await res.json();
        if (data.app && data.app.threshold) {
            _slowThreshold = parseFloat(data.app.threshold);
            console.log(`✅ Umbral de slow queries cargado: ${_slowThreshold}s`);
        }
    } catch (error) {
        console.warn('No se pudo cargar el umbral, usando valor por defecto:', error);
        _slowThreshold = 3.0;
    }
}