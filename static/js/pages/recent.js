//static/js/pages/recent.js
import { setText, esc } from '../helpers.js';

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
        
        // Actualizar estadísticas
        setText('recentTotal', statsData.total || 0);
        setText('recentAvg', (statsData.avg_time_ms || 0).toFixed(2));
        setText('recentMax', (statsData.max_time_ms || 0).toFixed(2));
        setText('recentMin', (statsData.min_time_ms || 0).toFixed(2));
        
        // Actualizar tabla
        const tbody = document.getElementById('recentBody');
        if (!tbody) return;
        
        if (!queriesData.data || queriesData.data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="empty-state">
                <i class="bi bi-inbox"></i>
                <p>No hay consultas recientes</p>
            </td></tr>`;
            return;
        }
        
        tbody.innerHTML = queriesData.data.map((q, i) => {
            const sqlPreview = esc(q.sql_text || '').substring(0, 80);
            const sqlFull = esc(q.sql_text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            
            return `
                <tr>
                    <td>${i + 1}</td>
                    <td>
                        <code title="${sqlFull}" style="font-size:11px">${sqlPreview}${sqlPreview.length >= 80 ? '...' : ''}</code>
                    </td>
                    <td><span class="${q.query_time_ms > 100 ? 'text-danger' : q.query_time_ms > 10 ? 'text-warning' : 'text-success'}">${q.query_time_ms.toFixed(2)}</span></td>
                    <td><small>${esc(q.client_ip || 'unknown')}</small></td>
                    <td>${esc(q.username || '—')}</td>
                    <td>${esc(q.database || '—')}</td>
                    <td>${q.rows_examined.toLocaleString()}</td>
                    <td>${q.rows_sent.toLocaleString()}</td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Error cargando consultas recientes:', error);
    }
}

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

export function initRecent() {
    loadRecentQueries();
}