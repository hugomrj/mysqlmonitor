/* ─────────────────────────────────────────────
   slow.js — Consultas Lentas (persistidas)
   ───────────────────────────────────────────── */

import { esc, formatNum } from '../helpers.js';

let _total = 0;
let _page = 0;
const _limit = 50;

/* ══════════════════════════════════════
   ENTRY POINT
   ══════════════════════════════════════ */
export async function loadSlowQueries() {
    loadDBDropdown();
    await fetchAndRender();
}

/* ══════════════════════════════════════
   FETCH + RENDER
   ══════════════════════════════════════ */
async function fetchAndRender() {
    const body = document.getElementById('slowBody');
    body.innerHTML = `<tr><td colspan="7" class="empty-state"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Cargando...</td></tr>`;

    const params = new URLSearchParams();
    params.set('limit', _limit);
    params.set('offset', _page * _limit);

    const minTime = document.getElementById('slowMinTime').value;
    if (minTime) params.set('min_time', minTime);

    const db = document.getElementById('slowDb').value;
    if (db) params.set('db', db);

    const dateFrom = document.getElementById('slowDate').value;
    if (dateFrom) params.set('date_from', dateFrom);

    try {
        const r = await fetch('/api/slow-queries?' + params);
        const res = await r.json();
        _total = res.total || 0;
        renderTable(res.data || []);
    } catch (e) {
        body.innerHTML = `<tr><td colspan="7" class="empty-state"><i class="bi bi-exclamation-triangle"></i><p>Error al cargar: ${e.message}</p></td></tr>`;
    }
}

/* ══════════════════════════════════════
   RENDER TABLA
   ══════════════════════════════════════ */
function renderTable(rows) {
    const body = document.getElementById('slowBody');

    if (!rows.length) {
        body.innerHTML = `<tr><td colspan="7" class="empty-state"><i class="bi bi-hourglass-split"></i><p>No hay consultas lentas${_total === 0 ? ' registradas' : ' con estos filtros'}</p></td></tr>`;
        return;
    }

    body.innerHTML = rows.map((q, i) => {
        const idx = _page * _limit + i + 1;
        const sql = truncateSQL(q.sql_text);
        const timeClr = timeColor(q.query_time);
        const time = q.query_time.toFixed(2) + 's';
        const ts = formatTS(q.start_time);

        return `<tr style="cursor:pointer" onclick="window.showSlowDetail(${q.id})">
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${idx}</td>
            <td><code class="sql-snippet">${esc(sql)}</code></td>
            <td><span style="color:${timeClr};font-weight:700;font-family:'Space Grotesk',monospace">${time}</span></td>
            <td style="font-family:'Space Grotesk',monospace;font-size:13px">${formatNum(q.rows_examined)}</td>
            <td style="font-family:'Space Grotesk',monospace;font-size:13px">${formatNum(q.rows_sent)}</td>
            <td><span class="bs bs-i">${esc(q.db || '—')}</span></td>
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${ts}</td>
        </tr>`;
    }).join('');

    renderPagination();
}

/* ══════════════════════════════════════
   PAGINACIÓN
   ══════════════════════════════════════ */
function renderPagination() {
    // Quitar paginación anterior si existe
    const old = document.getElementById('slowPagination');
    if (old) old.remove();

    const totalPages = Math.ceil(_total / _limit);
    if (totalPages <= 1) return;

    const table = document.getElementById('tSlow');
    const wrapper = document.createElement('div');
    wrapper.id = 'slowPagination';
    wrapper.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-top:1px solid rgba(255,255,255,.06)';

    const info = document.createElement('span');
    info.style.cssText = 'font-size:12px;color:var(--text-muted)';
    info.textContent = `${_total} consultas · Página ${_page + 1} de ${totalPages}`;

    const btns = document.createElement('div');
    btns.style.cssText = 'display:flex;gap:6px';

    const prevBtn = document.createElement('button');
    prevBtn.className = 'boc btn-sm';
    prevBtn.innerHTML = '<i class="bi bi-chevron-left"></i>';
    prevBtn.disabled = _page === 0;
    prevBtn.onclick = () => { _page--; fetchAndRender(); };

    const nextBtn = document.createElement('button');
    nextBtn.className = 'boc btn-sm';
    nextBtn.innerHTML = '<i class="bi bi-chevron-right"></i>';
    nextBtn.disabled = _page >= totalPages - 1;
    nextBtn.onclick = () => { _page++; fetchAndRender(); };

    btns.append(prevBtn, nextBtn);
    wrapper.append(info, btns);
    table.parentElement.appendChild(wrapper);
}

/* ══════════════════════════════════════
   DETALLE (modal)
   ══════════════════════════════════════ */
window.showSlowDetail = async function (id) {
    // Buscar en la data actual primero para evitar fetch extra
    const rows = document.querySelectorAll('#slowBody tr[data-id]');
    // Simpler: fetch individual
    try {
        const r = await fetch('/api/slow-queries?limit=500');
        const res = await r.json();
        const q = res.data.find(d => d.id === id);
        if (!q) return;

        const title = document.getElementById('mTitle');
        const body = document.getElementById('mBody');
        const copyBtn = document.getElementById('copyBtn');

        title.innerHTML = '<i class="bi bi-hourglass-split me-2" style="color:var(--warning)"></i>Consulta Lenta';

        const timeClr = timeColor(q.query_time);
        body.innerHTML = `
            <div class="rs-grid mb-3">
                <span class="rs-cell">Tiempo</span>
                <span class="rs-val" style="color:${timeClr};font-weight:700">${q.query_time.toFixed(2)}s</span>
                <span class="rs-cell">Lock Time</span>
                <span class="rs-val">${q.lock_time || '—'}</span>
                <span class="rs-cell">Rows Examined</span>
                <span class="rs-val">${formatNum(q.rows_examined)}</span>
                <span class="rs-cell">Rows Sent</span>
                <span class="rs-val">${formatNum(q.rows_sent)}</span>
                <span class="rs-cell">Base de Datos</span>
                <span class="rs-val">${esc(q.db || '—')}</span>
                <span class="rs-cell">Usuario</span>
                <span class="rs-val">${esc(q.user_host || '—')}</span>
                <span class="rs-cell">Timestamp</span>
                <span class="rs-val">${q.start_time}</span>
            </div>
            <div style="margin-top:12px">
                <label style="font-size:12px;color:var(--text-muted);margin-bottom:6px;display:block">SQL Query</label>
                <pre style="background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-size:12.5px;color:#e2e8f0;max-height:400px;overflow:auto;margin:0;white-space:pre-wrap;word-break:break-all;font-family:'Fira Code',monospace;line-height:1.6">${esc(q.sql_text)}</pre>
            </div>`;

        copyBtn.onclick = () => {
            navigator.clipboard.writeText(q.sql_text);
            copyBtn.innerHTML = '<i class="bi bi-check me-1"></i>Copiado';
            setTimeout(() => {
                copyBtn.innerHTML = '<i class="bi bi-clipboard me-1"></i>Copiar SQL';
            }, 2000);
        };

        new bootstrap.Modal(document.getElementById('detailModal')).show();
    } catch (e) {
        console.error('Error mostrando detalle:', e);
    }
};

/* ══════════════════════════════════════
   DROPDOWN DE BASES DE DATOS
   ══════════════════════════════════════ */
async function loadDBDropdown() {
    const select = document.getElementById('slowDb');
    if (!select) return;
    const current = select.value;

    try {
        const r = await fetch('/api/slow-queries/databases');
        const dbs = await r.json();
        select.innerHTML = '<option value="">Todas</option>' +
            dbs.map(d => `<option value="${esc(d)}"${d === current ? ' selected' : ''}>${esc(d)}</option>`).join('');
    } catch (e) {
        // Silencioso, el dropdown se queda con lo que tenga
    }
}

/* ══════════════════════════════════════
   LIMPIAR HISTORIAL
   ══════════════════════════════════════ */
export async function clearSlowHistory() {    
    if (!confirm('¿Borrar todo el historial de consultas lentas?')) return;
    try {
        await fetch('/api/slow-queries', { method: 'DELETE' });
        _page = 0;
        _total = 0;
        loadDBDropdown();
        fetchAndRender();
    } catch (e) {
        console.error('Error limpiando:', e);
    }
};

/* ══════════════════════════════════════
   UTILIDADES
   ══════════════════════════════════════ */

function truncateSQL(sql) {
    if (!sql) return '—';
    const clean = sql.replace(/\s+/g, ' ').trim();
    if (clean.length <= 100) return clean;
    return clean.substring(0, 100) + '...';
}

function timeColor(seconds) {
    if (seconds >= 10) return 'var(--danger)';
    if (seconds >= 5)  return 'var(--warning)';
    if (seconds >= 2)  return '#facc15';
    return 'var(--text-primary)';
}

function formatTS(ts) {
    if (!ts) return '—';
    try {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return ts;
        return d.toLocaleString('es-ES', {
            day: '2-digit', month: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
    } catch {
        return ts;
    }
}

window.clearSlowHistory = clearSlowHistory;