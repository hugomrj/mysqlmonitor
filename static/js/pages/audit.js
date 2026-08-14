import { setText, esc, formatNum } from '../helpers.js';

let _total = 0;
let _page = 0;
const _limit = 50;
let _filtersLoaded = false; // 🆕 Evita recargar filtros cada vez

export async function loadAudit(initialLoad = false) {
    // 🆕 Solo cargar filtros la primera vez o si se fuerza
    if (initialLoad || !_filtersLoaded) {
        await loadFilters();
        _filtersLoaded = true;
    }
    
    await fetchSummary();
    await fetchAndRender();
}

/* ── Resumen (tarjetas) ── */
async function fetchSummary() {
    try {
        const r = await fetch('/api/audit/summary');
        const s = await r.json();
        setText('aud_total', s.total.toLocaleString());
        setText('aud_ins', s.inserts.toLocaleString());
        setText('aud_upd', s.updates.toLocaleString());
        setText('aud_del', s.deletes.toLocaleString());
    } catch (e) {}
}

/* ── Fetch principal ── */
async function fetchAndRender() {
    const body = document.getElementById('auditBody');
    body.innerHTML = `<tr><td colspan="7" class="empty-state"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Cargando...</td></tr>`;

    const params = new URLSearchParams();
    params.set('limit', _limit);
    params.set('offset', _page * _limit);

    const op = document.getElementById('audOp').value;
    if (op) params.set('operation', op);

    const schema = document.getElementById('audSchema').value;
    if (schema) params.set('schema', schema);

    const table = document.getElementById('audTable').value;
    if (table) params.set('table', table);

    const from = document.getElementById('audFrom').value;
    if (from) params.set('date_from', from);

    const to = document.getElementById('audTo').value;
    if (to) params.set('date_to', to);

    try {
        const r = await fetch('/api/audit?' + params);
        const res = await r.json();
        _total = res.total || 0;
        renderTable(res.data || []);
    } catch (e) {
        body.innerHTML = `<tr><td colspan="7" class="empty-state"><i class="bi bi-exclamation-triangle"></i><p>Error al cargar</p></td></tr>`;
        hidePagination();
    }
}

/* ── Render tabla ── */
function renderTable(rows) {
    const body = document.getElementById('auditBody');

    if (!rows.length) {
        body.innerHTML = `<tr><td colspan="7" class="empty-state"><i class="bi bi-journal-text"></i><p>${_total === 0 ? 'Sin eventos de auditoría' : 'Sin resultados con estos filtros'}</p></td></tr>`;
        hidePagination();
        return;
    }

    body.innerHTML = rows.map((ev, i) => {
        const idx = _page * _limit + i + 1;
        const op = ev.event_type || '?';
        const opCls = op === 'INSERT' ? 'bs-s' : op === 'UPDATE' ? 'bs-w' : op === 'DELETE' ? 'bs-d' : 'bs-m';
        const opIcon = op === 'INSERT' ? 'bi-plus-circle-fill' : op === 'UPDATE' ? 'bi-pencil-fill' : op === 'DELETE' ? 'bi-trash3-fill' : 'bi-circle';
        const ts = fmtTS(ev.event_time);
        const tbl = ev.schema ? `${esc(ev.schema)}.${esc(ev.table || '—')}` : esc(ev.table || '—');

        let preview = '<span class="text-muted" style="font-size:11px">—</span>';
        if (ev.row_data) {
            try {
                const rws = typeof ev.row_data === 'string' ? JSON.parse(ev.row_data) : ev.row_data;
                if (rws && rws.length > 0) {
                    const obj = rws[0].after || rws[0].values || rws[0];
                    if (obj && typeof obj === 'object') {
                        const parts = Object.entries(obj).slice(0, 3).map(([k, v]) =>
                            `<span style="color:var(--text-muted)">${esc(k)}:</span> <span style="color:var(--accent)">${esc(String(v).substring(0, 20))}</span>`
                        );
                        const extra = Object.keys(obj).length > 3 ? '…' : '';
                        preview = `<div style="font-size:11px;line-height:1.4;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${parts.join(', ')}${extra}</div>`;
                    }
                }
            } catch (e) {}
        }

        return `<tr style="cursor:pointer" onclick="window.showAuditDetail(${ev.id})">
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${idx}</td>
            <td><span class="bs ${opCls}"><i class="bi ${opIcon} me-1" style="font-size:10px"></i>${op}</span></td>
            <td style="font-size:12.5px;font-weight:600">${tbl}</td>
            <td>${preview}</td>
            <td class="fd" style="font-weight:600">${formatNum(ev.affected_rows || 0)}</td>
            <td class="text-secondary" style="font-size:12px;white-space:nowrap">${ts}</td>
            <td><button class="bsa" onclick="event.stopPropagation();window.showAuditDetail(${ev.id})"><i class="bi bi-eye"></i></button></td>
        </tr>`;
    }).join('');

    renderPagination();
}

/* ── Paginación ── */
function renderPagination() {
    const wrap = document.getElementById('auditPagination');
    const info = document.getElementById('auditInfo');
    const pages = document.getElementById('auditPages');
    const totalPages = Math.ceil(_total / _limit);

    if (totalPages <= 1) { 
        hidePagination();
        return; 
    }

    wrap.style.display = 'flex';
    const from = _page * _limit + 1;
    const to = Math.min((_page + 1) * _limit, _total);
    info.textContent = `Mostrando ${from.toLocaleString()}-${to.toLocaleString()} de ${_total.toLocaleString()} registros`;

    let html = '';
    html += `<li class="page-item${_page === 0 ? ' disabled' : ''}"><a class="page-link" href="#" onclick="event.preventDefault();window.goAuditPage(${_page - 1})" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">‹ Anterior</a></li>`;

    const maxVis = 5;
    let startP = Math.max(0, _page - Math.floor(maxVis / 2));
    let endP = Math.min(totalPages - 1, startP + maxVis - 1);
    if (endP - startP < maxVis - 1) startP = Math.max(0, endP - maxVis + 1);

    if (startP > 0) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="event.preventDefault();window.goAuditPage(0)" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">1</a></li>`;
        if (startP > 1) html += `<li class="page-item disabled"><span class="page-link" style="background:var(--bg-card);border-color:var(--border);color:var(--text-muted)">…</span></li>`;
    }
    for (let i = startP; i <= endP; i++) {
        const active = i === _page;
        html += `<li class="page-item${active ? ' active' : ''}"><a class="page-link" href="#" onclick="event.preventDefault();window.goAuditPage(${i})" style="background:${active ? 'var(--accent)' : 'var(--bg-card)'};border-color:${active ? 'var(--accent)' : 'var(--border)'};color:${active ? '#060a13' : 'var(--text-secondary)'};font-weight:${active ? '700' : '400'}">${i + 1}</a></li>`;
    }
    if (endP < totalPages - 1) {
        if (endP < totalPages - 2) html += `<li class="page-item disabled"><span class="page-link" style="background:var(--bg-card);border-color:var(--border);color:var(--text-muted)">…</span></li>`;
        html += `<li class="page-item"><a class="page-link" href="#" onclick="event.preventDefault();window.goAuditPage(${totalPages - 1})" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">${totalPages}</a></li>`;
    }

    html += `<li class="page-item${_page >= totalPages - 1 ? ' disabled' : ''}"><a class="page-link" href="#" onclick="event.preventDefault();window.goAuditPage(${_page + 1})" style="background:var(--bg-card);border-color:var(--border);color:var(--text-secondary)">Siguiente ›</a></li>`;
    pages.innerHTML = html;
}

function hidePagination() {
    const wrap = document.getElementById('auditPagination');
    if (wrap) wrap.style.display = 'none';
}

// 🆕 Función limpia para cambiar de página
window.goAuditPage = function(page) {
    const totalPages = Math.ceil(_total / _limit);
    if (page < 0 || page >= totalPages) return;
    _page = page;
    fetchAndRender(); // No recarga todo, solo la tabla
};

/* ── Dropdowns (CORREGIDO: preserva valores) ── */
async function loadFilters() {
    try {
        const r = await fetch('/api/audit/filters');
        const f = await r.json();
        
        const sSel = document.getElementById('audSchema');
        const tSel = document.getElementById('audTable');
        
        // 🆕 Guardar valores actuales ANTES de reconstruir
        const currentSchema = sSel.value;
        const currentTable = tSel.value;
        
        // Reconstruir Schema dropdown
        sSel.innerHTML = '<option value="">Todos</option>' + 
            (f.schemas || []).map(s => 
                `<option value="${esc(s)}"${s === currentSchema ? ' selected' : ''}>${esc(s)}</option>`
            ).join('');
        
        // Reconstruir Table dropdown
        tSel.innerHTML = '<option value="">Todas</option>' + 
            (f.tables || []).map(t => 
                `<option value="${esc(t)}"${t === currentTable ? ' selected' : ''}>${esc(t)}</option>`
            ).join('');
    } catch (e) {
        console.error('Error cargando filtros:', e);
    }
}

/* ── Aplicar filtros (resetea a página 0) ── */
window.applyAuditFilters = function() {
    _page = 0;
    fetchAndRender();
};

/* ── Limpiar filtros ── */
window.clearAuditFilters = function () {
    document.getElementById('audOp').value = '';
    document.getElementById('audSchema').value = '';
    document.getElementById('audTable').value = '';
    document.getElementById('audFrom').value = '';
    document.getElementById('audTo').value = '';
    _page = 0;
    fetchAndRender();
};

/* ── Detalle en modal ── */
window.showAuditDetail = async function (id) {
    try {
        // 🆕 Buscar en los datos actuales en lugar de hacer otra petición
        const r = await fetch(`/api/audit?limit=1&offset=0`);
        // Mejor: obtener el evento específico por ID
        const r2 = await fetch(`/api/audit?limit=500&offset=0`);
        const res2 = await r2.json();
        const ev = res2.data.find(d => d.id === id);
        if (!ev) {
            console.error('Evento no encontrado:', id);
            return;
        }

        const op = ev.event_type || '?';
        const opCls = op === 'INSERT' ? 'bs-s' : op === 'UPDATE' ? 'bs-w' : op === 'DELETE' ? 'bs-d' : 'bs-m';

        document.getElementById('mTitle').innerHTML = `<i class="bi bi-journal-text me-2" style="color:var(--accent)"></i>Auditoría #${ev.id}`;
        document.getElementById('mBody').innerHTML = `
            <div class="rs-grid mb-3">
                <span class="rs-cell">Operación</span><span class="bs ${opCls}" style="font-size:12px;padding:4px 10px">${op}</span>
                <span class="rs-cell">Tabla</span><span class="rs-val" style="color:var(--accent)">${esc(ev.schema || '—')}.${esc(ev.table || '—')}</span>
                <span class="rs-cell">Filas Afectadas</span><span class="rs-val">${formatNum(ev.affected_rows || 0)}</span>
                <span class="rs-cell">Fecha y Hora</span><span class="rs-val">${ev.event_time}</span>
                <span class="rs-cell">Posición Binlog</span><span class="rs-val">${esc(ev.log_file || '—')}:${ev.log_pos || '—'}</span>
            </div>
            <div>
                <label style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:6px">Datos del Evento</label>
                <pre style="background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-size:12px;color:#e2e8f0;max-height:400px;overflow:auto;margin:0;white-space:pre-wrap;word-break:break-all;font-family:'Fira Code',monospace;line-height:1.6">${formatRowData(ev.row_data)}</pre>
            </div>`;

        const copyBtn = document.getElementById('copyBtn');
        copyBtn.onclick = () => {
            navigator.clipboard.writeText(typeof ev.row_data === 'string' ? ev.row_data : JSON.stringify(ev.row_data, null, 2));
            copyBtn.innerHTML = '<i class="bi bi-check me-1"></i>Copiado';
            setTimeout(() => { copyBtn.innerHTML = '<i class="bi bi-clipboard me-1"></i>Copiar JSON'; }, 2000);
        };

        new bootstrap.Modal(document.getElementById('detailModal')).show();
    } catch (e) {
        console.error('Error detalle auditoría:', e);
    }
};

function formatRowData(raw) {
    if (!raw) return '—';
    try {
        const rows = typeof raw === 'string' ? JSON.parse(raw) : raw;
        if (!Array.isArray(rows) || !rows.length) return typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2);
        return rows.map((r, i) => {
            const obj = r.after || r.values || r;
            if (typeof obj !== 'object' || obj === null) return `Row ${i + 1}: ${JSON.stringify(r, null, 2)}`;
            const entries = Object.entries(obj).map(([k, v]) => {
                const val = v === null ? 'NULL' : String(v);
                const display = val.length > 120 ? val.substring(0, 120) + '…' : val;
                return v === null ? `  ${esc(k)}: <span style="color:var(--text-muted)">NULL</span>` : `  ${esc(k)}: <span style="color:var(--accent)">${esc(display)}</span>`;
            }).join('\n');
            return `── Row ${i + 1} ──\n${entries}`;
        }).join('\n\n');
    } catch (e) {
        return raw;
    }
}

function fmtTS(ts) {
    if (!ts) return '—';
    try {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return ts;
        return d.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return ts; }
}








