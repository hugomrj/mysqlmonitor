import { esc, formatNum } from '../helpers.js';

let _total = 0;
let _page = 0;
const _limit = 15;

export async function loadQueries() {
    loadDropdowns();
    await fetchAndRender();
}



async function fetchAndRender() {
    const body = document.getElementById('queriesBody');
    body.innerHTML = `<tr><td colspan="8" class="empty-state"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Cargando...</td></tr>`;

    const params = new URLSearchParams();
    params.set('limit', _limit);
    params.set('offset', _page * _limit);

    const user = document.getElementById('qUser').value;
    if (user) params.set('user', user);

    const db = document.getElementById('qDb').value;
    if (db) params.set('db', db);

    const date = document.getElementById('qDate').value;
    if (date) params.set('date_from', date);

    const search = document.getElementById('qSearch').value.trim();
    if (search) params.set('search', search);

    try {
        const r = await fetch('/api/queries?' + params);
        const res = await r.json();
        _total = res.total || 0;
        renderTable(res.data || []);
    } catch (e) {
        body.innerHTML = `<tr><td colspan="8" class="empty-state"><i class="bi bi-exclamation-triangle"></i><p>Error: ${e.message}</p></td></tr>`;
    }
}




function renderTable(rows) {
    const body = document.getElementById('queriesBody');

    if (!rows.length) {
        body.innerHTML = `<tr><td colspan="8" class="empty-state"><i class="bi bi-code-slash"></i><p>${_total === 0 ? 'Sin consultas registradas' : 'Sin resultados para estos filtros'}</p></td></tr>`;
        document.getElementById('queriesPagination').style.display = 'none';
        return;
    }

    body.innerHTML = rows.map((q, i) => {
        const idx = _page * _limit + i + 1;
        const op = parseOp(q.sql_text);
        const tbl = parseTable(q.sql_text, op);
        const { user, host } = parseUserHost(q.user_host);

        const ms = q.query_time > 0 ? (q.query_time * 1000).toFixed(0) + ' ms' : '—';
        const timeClr = q.query_time > 0 ? timeColor(q.query_time) : 'var(--text-muted)';


        const opCls = op === 'SELECT' ? 'bs-i' : op === 'INSERT' ? 'bs-s' : op === 'UPDATE' ? 'bs-w' : op === 'DELETE' ? 'bs-d' : 'bs-m';
        const ts = fmtTS(q.start_time);

        return `<tr>
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${idx}</td>
            <td><code class="sql-snippet">${esc(truncateSQL(q.sql_text))}</code></td>
            <td><span style="color:${timeClr};font-weight:700;font-family:'Space Grotesk',monospace;font-size:13px">${ms} ms</span></td>
            <td style="font-size:12.5px">${esc(user)}</td>
            <td><span class="bs bs-i">${esc(q.db || '—')}</span></td>
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${ts}</td>
            <td><span class="bs ${opCls}">${op}</span></td>
            <td><button class="bsa" onclick="window.showQueryDetail(${q.id})"><i class="bi bi-eye"></i></button></td>
        </tr>`;
    }).join('');

    renderPagination();
}

function renderPagination() {
    const wrap = document.getElementById('queriesPagination');
    const info = document.getElementById('queriesInfo');
    const pages = document.getElementById('queriesPages');
    const totalPages = Math.ceil(_total / _limit);

    if (totalPages <= 1) { wrap.style.display = 'none'; return; }

    wrap.style.display = 'flex';
    const from = _page * _limit + 1;
    const to = Math.min((_page + 1) * _limit, _total);
    info.textContent = `Mostrando ${from}-${to} de ${_total.toLocaleString()} resultados`;

    let html = '';
    // Prev
    html += `<li class="page-item${_page === 0 ? ' disabled' : ''}"><a class="page-link" href="#" onclick="event.preventDefault();window._qPage=${_page - 1};loadQueries()" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">Anterior</a></li>`;

    // Page numbers
    const maxVisible = 5;
    let startP = Math.max(0, _page - Math.floor(maxVisible / 2));
    let endP = Math.min(totalPages - 1, startP + maxVisible - 1);
    if (endP - startP < maxVisible - 1) startP = Math.max(0, endP - maxVisible + 1);

    if (startP > 0) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="event.preventDefault();window._qPage=0;loadQueries()" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">1</a></li>`;
        if (startP > 1) html += `<li class="page-item disabled"><span class="page-link" style="background:var(--bg-card);border-color:var(--border);color:var(--text-muted)">...</span></li>`;
    }

    for (let i = startP; i <= endP; i++) {
        const active = i === _page;
        html += `<li class="page-item${active ? ' active' : ''}"><a class="page-link" href="#" onclick="event.preventDefault();window._qPage=${i};loadQueries()" style="background:${active ? 'var(--accent)' : 'var(--bg-card)'};border-color:${active ? 'var(--accent)' : 'var(--border)'};color:${active ? '#060a13' : 'var(--text-secondary)'};font-weight:${active ? '700' : '400'}">${i + 1}</a></li>`;
    }

    if (endP < totalPages - 1) {
        if (endP < totalPages - 2) html += `<li class="page-item disabled"><span class="page-link" style="background:var(--bg-card);border-color:var(--border);color:var(--text-muted)">...</span></li>`;
        html += `<li class="page-item"><a class="page-link" href="#" onclick="event.preventDefault();window._qPage=${totalPages - 1};loadQueries()" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">${totalPages}</a></li>`;
    }

    // Next
    html += `<li class="page-item${_page >= totalPages - 1 ? ' disabled' : ''}"><a class="page-link" href="#" onclick="event.preventDefault();window._qPage=${_page + 1};loadQueries()" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">Siguiente</a></li>`;

    pages.innerHTML = html;
}

// Expose page setter for pagination onclick
window._qPage = 0;
Object.defineProperty(window, '_qPage', {
    set(v) { _page = v; },
    get() { return _page; }
});

/* ── DETAIL MODAL ── */
window.showQueryDetail = async function (id) {
    try {
        const r = await fetch('/api/queries?limit=500');
        const res = await r.json();
        const q = res.data.find(d => d.id === id);
        if (!q) return;

        const op = parseOp(q.sql_text);
        const tbl = parseTable(q.sql_text, op);
        const { user, host } = parseUserHost(q.user_host);
        const opCls = op === 'SELECT' ? 'bs-i' : op === 'INSERT' ? 'bs-s' : op === 'UPDATE' ? 'bs-w' : op === 'DELETE' ? 'bs-d' : 'bs-m';

        document.getElementById('mTitle').innerHTML = `<i class="bi bi-code-slash me-2" style="color:var(--accent)"></i>Consulta #${q.id}`;
        document.getElementById('mBody').innerHTML = `
            <div class="row g-3 mb-3">
                <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Usuario</small><span class="fd" style="font-weight:700;font-size:18px">${esc(user)}</span></div>
                <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Operación</small><span class="bs ${opCls}" style="font-size:12px;padding:5px 12px">${op}</span></div>
            </div>
            <div class="row g-3 mb-3">
                <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Tabla</small><code style="font-size:15px;color:var(--accent)">${esc(tbl)}</code></div>
                <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Estado</small><span class="bs bs-s" style="font-size:12px;padding:5px 12px">Completada</span></div>
            </div>
            <div class="row g-3 mb-3">
                <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Fecha y Hora</small><span style="font-size:13px">${q.start_time}</span></div>
                <div class="col-6"><small style="font-size:11px;text-transform:uppercase;font-weight:600;color:var(--text-muted);display:block">Host / IP</small><code style="font-size:13px">${esc(host)}</code></div>
            </div>
            <div>
                <label style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:6px">Contexto Adicional</label>
                <div class="codeb" style="font-size:12px;color:var(--text-secondary)">Base de Datos: ${esc(q.db || '—')}
Query Time: ${(q.query_time * 1000).toFixed(0)} ms
Lock Time: ${q.lock_time || '—'}
Rows Examined: ${formatNum(q.rows_examined)}
Rows Sent: ${formatNum(q.rows_sent)}</div>
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
    } catch (e) {
        console.error('Error detalle:', e);
    }
};

/* ── CLEAR FILTERS ── */
window.clearQueryFilters = function () {
    document.getElementById('qUser').value = '';
    document.getElementById('qDb').value = '';
    document.getElementById('qDate').value = '';
    document.getElementById('qSearch').value = '';
    _page = 0;
    loadQueries();
};

/* ── DROPDOWNS ── */
async function loadDropdowns() {
    try {
        
        const [uRes, dRes] = await Promise.all([
            fetch('/api/queries/users'),      
            fetch('/api/queries/databases')   
        ]);


        const users = await uRes.json();
        const dbs = await dRes.json();
        const uSel = document.getElementById('qUser');
        const dSel = document.getElementById('qDb');
        const cu = uSel.value, cd = dSel.value;
        uSel.innerHTML = '<option value="">Todos</option>' + users.map(u => `<option value="${esc(u)}"${u === cu ? ' selected' : ''}>${esc(u)}</option>`).join('');
        dSel.innerHTML = '<option value="">Todas</option>' + dbs.map(d => `<option value="${esc(d)}"${d === cd ? ' selected' : ''}>${esc(d)}</option>`).join('');
    } catch (e) {}
}

/* ── SQL PARSERS ── */
function parseOp(sql) {
    if (!sql) return 'UNKNOWN';
    const first = sql.trim().toUpperCase().split(/\s+/)[0];
    return ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'REPLACE', 'CALL', 'SET'].includes(first) ? first : 'OTHER';
}

function parseTable(sql, op) {
    if (!sql) return '—';
    const u = sql.toUpperCase();
    switch (op) {
        case 'SELECT': { const m = u.match(/FROM\s+`?(\w+)`?/); return m ? m[1] : '—'; }
        case 'INSERT': { const m = u.match(/INTO\s+`?(\w+)`?/); return m ? m[1] : '—'; }
        case 'UPDATE': { const m = u.match(/UPDATE\s+`?(\w+)`?/); return m ? m[1] : '—'; }
        case 'DELETE': { const m = u.match(/FROM\s+`?(\w+)`?/); return m ? m[1] : '—'; }
        default: return '—';
    }
}

function parseUserHost(uh) {
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

function timeColor(s) {
    if (s >= 10) return 'var(--danger)';
    if (s >= 5) return 'var(--warning)';
    if (s >= 2) return '#facc15';
    return 'var(--text-primary)';
}

function fmtTS(ts) {
    if (!ts) return '—';
    try {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return ts;
        return d.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return ts; }
}