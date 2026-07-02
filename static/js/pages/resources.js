/* ─────────────────────────────────────────────
   resources.js — Gauges + Stats + Charts
   ───────────────────────────────────────────── */

import { setText, setBar, chartOpts, formatNum } from '../helpers.js';

const C = {};
let inited = false;
let _dbLoaded = false;

const BAR_C = [
    'rgba(245,158,11,.8)', 'rgba(56,189,248,.8)', 'rgba(167,139,250,.8)',
    'rgba(34,197,94,.8)', 'rgba(239,68,68,.8)', 'rgba(236,72,153,.8)',
    'rgba(20,184,166,.8)', 'rgba(251,146,60,.8)', 'rgba(99,102,241,.8)',
    'rgba(168,85,247,.8)',
];

/* ══════════════════════════════════════
   ENTRY POINT
   ══════════════════════════════════════ */
export async function loadResourceCharts() {
    if (!inited) {
        buildGauges();
        buildBarCharts();
        inited = true;
    }

    try {
        const r = await fetch('/api/metrics/snapshot');
        const d = await r.json();
        updateAll(d);
    } catch (e) {
        console.warn('[Resources] Error snapshot:', e.message);
    }

    if (!_dbLoaded) {
        loadDBCharts();
        _dbLoaded = true;
    }
}

/* ══════════════════════════════════════
   UPDATE — called with each snapshot
   ══════════════════════════════════════ */
function updateAll(d) {
    const sys = d.system || {};
    const st  = d.mysql_status || {};

    // Gauges
    if (sys.cpu_percent != null)  updateGauge('gaugeCPU',  sys.cpu_percent);
    if (sys.ram_percent != null)  updateGauge('gaugeRAM',  sys.ram_percent);
    if (sys.disk_percent != null) updateGauge('gaugeDisk', sys.disk_percent);

    // Tarjetas de detalle
    populateDiskCard(sys);
    populateRAMCard(sys);
    populateCPUCard(sys);

    // InnoDB + Threads
    renderInnoDB(st);
    renderThreads(st);
}

/* ══════════════════════════════════════
   GAUGES (semicírculos)
   ══════════════════════════════════════ */

function buildGauges() {
    createGauge('gaugeCPU',  'rgba(56,189,248,.85)',  'rgba(56,189,248,.12)');
    createGauge('gaugeRAM',  'rgba(167,139,250,.85)', 'rgba(167,139,250,.12)');
    createGauge('gaugeDisk', 'rgba(245,158,11,.85)',  'rgba(245,158,11,.12)');
}

function createGauge(canvasId, color, bgColor) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    C[canvasId] = new Chart(canvas, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [0, 100],
                backgroundColor: [color, bgColor],
                borderWidth: 0,
                borderRadius: 6,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            rotation: -90,
            circumference: 180,
            cutout: '76%',
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
            },
            animation: {
                duration: 600,
                easing: 'easeOutQuart',
            },
        },
    });
}

function updateGauge(canvasId, value) {
    const chart = C[canvasId];
    if (!chart) return;
    const v = Math.min(100, Math.max(0, Number(value)));
    chart.data.datasets[0].data = [v, 100 - v];
    chart.update();

    const valEl = document.getElementById(canvasId + '_val');
    if (valEl) valEl.textContent = v.toFixed(1) + '%';
}

/* ══════════════════════════════════════
   TARJETAS DE DETALLE
   ══════════════════════════════════════ */

function populateDiskCard(sys) {
    setText('rs_disk_total', (sys.disk_total_gb || 0) + ' GB');
    setText('rs_disk_used',  (sys.disk_used_gb || 0) + ' GB');
    setText('rs_disk_free',  (sys.disk_free_gb || 0) + ' GB');
    setBar('rs_disk_bar', sys.disk_percent || 0);
    setText('rs_disk_pct', (sys.disk_percent || 0).toFixed(1) + '% utilizado');
}

function populateRAMCard(sys) {
    setText('rs_ram_total', (sys.ram_total_gb || 0) + ' GB');
    setText('rs_ram_used',  (sys.ram_used_gb || 0) + ' GB');
    setText('rs_ram_free',  (sys.ram_free_gb || 0) + ' GB');
    setBar('rs_ram_bar', sys.ram_percent || 0);
    setText('rs_ram_pct', (sys.ram_percent || 0).toFixed(1) + '% utilizado');
}

function populateCPUCard(sys) {
    const cores = sys.cpu_cores || 1;
    const load1 = sys.load_avg_1m || 0;
    const loadPct = Math.min(100, Math.round((load1 / cores) * 100));

    setText('rs_cpu_cores', cores);
    setText('rs_load1', load1.toFixed(2));
    setText('rs_load5', (sys.load_avg_5m || 0).toFixed(2));
    setBar('rs_load_bar', loadPct);
    setText('rs_load_pct', loadPct + '% utilización promedio');
}

/* ══════════════════════════════════════
   INNODB + THREADS (grilla)
   ══════════════════════════════════════ */

function renderInnoDB(st) {
    const box = document.getElementById('innodbStats');
    if (!box) return;
    if (st.mysql_connected === false) { box.innerHTML = offline(); return; }

    const pct = st.buffer_pool_used_pct || 0;
    const hit = st.buffer_pool_hit_ratio || 0;
    const hitClr = hit >= 99.5 ? 'var(--success)' : hit >= 95 ? 'var(--warning)' : 'var(--danger)';
    const usedClr = pct > 85 ? 'var(--danger)' : 'var(--warning)';

    box.innerHTML = `
        <div class="rs-grid">
            <span class="rs-cell">Tamaño Pool</span><span class="rs-val">${st.buffer_pool_size_gb||0} GB</span>
            <span class="rs-cell">Usado</span><span class="rs-val" style="color:${usedClr}">${st.buffer_pool_used_gb||0} GB</span>
            <span class="rs-cell">Ocupación</span><span class="rs-val">${pct}%</span>
        </div>
        <div class="pc mt-1 mb-2"><div class="pb" style="width:${Math.min(100,pct)}%;background:${usedClr}"></div></div>
        <div class="rs-grid">
            <span class="rs-cell">Hit Ratio</span><span class="rs-val" style="color:${hitClr};font-weight:700">${hit}%</span>
            <span class="rs-cell">Páginas Leídas</span><span class="rs-val">${formatNum(st.innodb_pages_read||0)}</span>
            <span class="rs-cell">Páginas Creadas</span><span class="rs-val">${formatNum(st.innodb_pages_created||0)}</span>
        </div>`;
}

function renderThreads(st) {
    const box = document.getElementById('connStats');
    if (!box) return;
    if (st.mysql_connected === false) { box.innerHTML = offline(); return; }

    const conn = st.threads_connected || 0;
    const max  = st.max_connections || 500;
    const maxUsed = st.max_used_connections || 0;
    const pct  = max ? Math.round((conn / max) * 100) : 0;
    const maxPct = max ? Math.round((maxUsed / max) * 100) : 0;
    const clr  = pct > 80 ? 'var(--danger)' : pct > 50 ? 'var(--warning)' : 'var(--success)';
    const maxClr = maxPct > 80 ? 'var(--danger)' : maxPct > 50 ? 'var(--warning)' : 'var(--info)';

    box.innerHTML = `
        <div class="rs-grid">
            <span class="rs-cell">Conectados</span><span class="rs-val" style="color:var(--accent)">${conn}</span>
            <span class="rs-cell">Ejecutando</span><span class="rs-val" style="color:var(--info)">${st.threads_running||0}</span>
            <span class="rs-cell">En Cache</span><span class="rs-val">${st.threads_cached||0}</span>
        </div>
        <div class="pc mt-1 mb-2"><div class="pb" style="width:${Math.min(100,pct)}%;background:${clr}"></div></div>
        <small style="color:var(--text-muted);font-size:11px">${pct}% de ${max} máx.</small>
        <div class="rs-grid mt-2">
            <span class="rs-cell">Max Conexiones</span><span class="rs-val">${max}</span>
            <span class="rs-cell">Max Usadas (pico)</span><span class="rs-val" style="color:${maxClr}">${maxUsed} <small style="opacity:.6">(${maxPct}%)</small></span>
            <span class="rs-cell">Total Histórico</span><span class="rs-val">${formatNum(st.connections_total||0)}</span>
            <span class="rs-cell">Aborted Connects</span><span class="rs-val" style="color:${(st.aborted_connects||0)>0?'var(--danger)':'inherit'}">${formatNum(st.aborted_connects||0)}</span>
            <span class="rs-cell">Aborted Clients</span><span class="rs-val" style="color:${(st.aborted_clients||0)>0?'var(--danger)':'inherit'}">${formatNum(st.aborted_clients||0)}</span>
        </div>`;
}

function offline() {
    return '<div style="color:var(--danger);font-size:13px;padding:8px 0"><i class="bi bi-x-circle me-1"></i>Sin conexión a MySQL</div>';
}

/* ══════════════════════════════════════
   BARRAS HORIZONTALES
   ══════════════════════════════════════ */

function buildBarCharts() {
    const ctxDB = document.getElementById('cSpDB');
    if (ctxDB) {
        C.db = new Chart(ctxDB, {
            type: 'bar',
            data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 4, barThickness: 20 }] },
            options: hBarOpts()
        });
    }
    const ctxTbl = document.getElementById('cSpTbl');
    if (ctxTbl) {
        C.tbl = new Chart(ctxTbl, {
            type: 'bar',
            data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderRadius: 4, barThickness: 20 }] },
            options: hBarOpts()
        });
    }
}

async function loadDBCharts() {
    try {
        const [dbRes, tblRes] = await Promise.all([
            fetch('/api/databases'),
            fetch('/api/databases/top-tables?limit=10'),
        ]);
        const dbs  = await dbRes.json();
        const tbls = await tblRes.json();
        updateDBChart(dbs);
        updateTblChart(tbls);
    } catch (e) {
        console.warn('[Resources] Error charts BD:', e.message);
    }
}

function updateDBChart(dbs) {
    if (!C.db || !Array.isArray(dbs)) return;
    const sorted = [...dbs]
        .map(d => ({ name: d.name, mb: (d.size_bytes || 0) / (1024 * 1024) }))
        .filter(d => d.mb > 0.01)
        .sort((a, b) => b.mb - a.mb)
        .slice(0, 10);

    C.db.data.labels = sorted.map(d => d.name);
    C.db.data.datasets[0].data = sorted.map(d => Math.round(d.mb * 10) / 10);
    C.db.data.datasets[0].backgroundColor = sorted.map((_, i) => BAR_C[i % BAR_C.length]);
    C.db.update('none');
}

function updateTblChart(tbls) {
    if (!C.tbl || !Array.isArray(tbls)) return;
    const sorted = [...tbls]
        .map(t => ({ label: t.schema + '.' + t.table, mb: (t.size_bytes || 0) / (1024 * 1024) }))
        .filter(t => t.mb > 0.01)
        .sort((a, b) => b.mb - a.mb)
        .slice(0, 10);

    C.tbl.data.labels = sorted.map(t => t.label);
    C.tbl.data.datasets[0].data = sorted.map(t => Math.round(t.mb * 10) / 10);
    C.tbl.data.datasets[0].backgroundColor = sorted.map((_, i) => BAR_C[i % BAR_C.length]);
    C.tbl.update('none');
}

function hBarOpts() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        indexAxis: 'y',
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: '#0f1629',
                borderColor: '#1a2540',
                borderWidth: 1,
                titleColor: '#eef2f7',
                bodyColor: '#8b9dc3',
                padding: 10,
                cornerRadius: 7,
                callbacks: {
                    label: (ctx) => {
                        const mb = ctx.parsed.x;
                        return mb >= 1024 ? (mb/1024).toFixed(1)+' GB' : mb.toFixed(1)+' MB';
                    }
                }
            }
        },
        scales: {
            x: {
                beginAtZero: true,
                grid: { color: 'rgba(255,255,255,.04)' },
                ticks: { color: '#5a6e8a', font: { size: 10 }, maxTicksLimit: 6,
                    callback: v => v >= 1024 ? (v/1024).toFixed(1)+'G' : v+'M'
                },
                border: { color: 'rgba(255,255,255,.06)' }
            },
            y: {
                grid: { display: false },
                ticks: { color: '#8b9dc3', font: { size: 10, family: 'DM Sans' } },
                border: { color: 'rgba(255,255,255,.06)' }
            }
        }
    };
}