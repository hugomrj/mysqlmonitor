import { setText, setBar, chartOpts } from '../helpers.js';

let qpsHistory = [], connHistory = [];
const C = {};

const DB_COLORS = [
    '#f59e0b', '#38bdf8', '#a78bfa', '#22c55e', '#ef4444',
    '#ec4899', '#14b8a6', '#fb923c', '#6366f1', '#a855f7',
];

/* ══════════════════════════════════════
   INIT
   ══════════════════════════════════════ */
export function initDashboard() {
    initDashCharts();
    fetch('/api/metrics/snapshot')
        .then(r => r.json())
        .then(d => updateDashboard(d))
        .catch(() => {});
    fetchDBSizes();
}

async function fetchDBSizes() {
    try {
        const r = await fetch('/api/databases');
        if (!r.ok) throw new Error(r.status);
        const data = await r.json();
        updateDBSizeDonut(data);
    } catch (e) {
        console.warn('[Dashboard] No se cargaron tamaños de BD:', e.message);
    }
}

/* ══════════════════════════════════════
   UPDATE — cada mensaje del WS
   ══════════════════════════════════════ */
export function updateDashboard(data) {
    if (!data) return;
    const sys = data.system || {};
    const st  = data.mysql_status || {};

    if (sys.cpu_percent !== undefined) {
        const v = sys.cpu_percent + '%';
        setText('d_cpu', v);
        setText('r_cpu', v);
        setBar('r_cpu_bar', sys.cpu_percent);
    }
    if (sys.ram_percent !== undefined) {
        const v = sys.ram_percent + '%';
        setText('d_ram', v);
        setText('r_ram', v);
        setBar('r_ram_bar', sys.ram_percent);
    }
    if (sys.disk_percent !== undefined) {
        const v = sys.disk_percent + '%';
        setText('d_disk', v);
        setText('r_disk', v);
        setBar('r_disk_bar', sys.disk_percent);
    }
    if (st.threads_connected !== undefined) {
        setText('d_conn', st.threads_connected);
    }
    if (st.qps !== undefined) {
        setText('d_qps', st.qps.toLocaleString());
        qpsHistory.push(st.qps);
        if (qpsHistory.length > 60) qpsHistory.shift();
        updateQPSChart();
    }
    if (st.threads_connected !== undefined) {
        connHistory.push(st.threads_connected);
        if (connHistory.length > 60) connHistory.shift();
        updateConnChart();
    }
}

/* ══════════════════════════════════════
   CONSTRUCCIÓN DE GRÁFICOS
   ══════════════════════════════════════ */
function initDashCharts() {
    if (C.qps) return;

    C.qps = new Chart(document.getElementById('cQPS'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: '#00d4aa',
                backgroundColor: 'rgba(0,212,170,.07)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
            }]
        },
        options: {
            ...chartOpts,
            scales: {
                ...chartOpts.scales,
                y: { ...chartOpts.scales.y, beginAtZero: false }
            }
        }
    });

    C.connH = new Chart(document.getElementById('cConnH'), {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: '#a78bfa',
                backgroundColor: 'rgba(167,139,250,.07)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
            }]
        },
        options: chartOpts
    });

    initDBSizeDonut();
}

function initDBSizeDonut() {
    const canvas = document.getElementById('cDBSize');
    if (!canvas) return;
    C.dbSize = new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: DB_COLORS,
                borderColor: '#0a0a0f',
                borderWidth: 2,
                hoverOffset: 6,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'rgba(255,255,255,0.55)',
                        font: { size: 10, family: 'DM Sans' },
                        boxWidth: 10,
                        padding: 6,
                    }
                },
                tooltip: {
                    backgroundColor: '#0f1629',
                    borderColor: '#1a2540',
                    borderWidth: 1,
                    titleColor: '#eef2f7',
                    bodyColor: '#8b9dc3',
                    padding: 10,
                    cornerRadius: 7,
                    callbacks: {
                        label: function (ctx) {
                            const mb = ctx.parsed;
                            return mb >= 1024
                                ? ctx.label + ': ' + (mb / 1024).toFixed(1) + ' GB'
                                : ctx.label + ': ' + mb.toFixed(1) + ' MB';
                        }
                    }
                }
            }
        }
    });
}

/* ══════════════════════════════════════
   ACTUALIZACIÓN DE GRÁFICOS
   ══════════════════════════════════════ */

function updateQPSChart() {
    if (!C.qps) return;
    C.qps.data.labels.push(ts());
    C.qps.data.datasets[0].data.push(qpsHistory[qpsHistory.length - 1]);
    if (C.qps.data.labels.length > 60) {
        C.qps.data.labels.shift();
        C.qps.data.datasets[0].data.shift();
    }
    C.qps.update('none');
}

function updateConnChart() {
    if (!C.connH) return;
    C.connH.data.labels.push(ts());
    C.connH.data.datasets[0].data.push(connHistory[connHistory.length - 1]);
    if (C.connH.data.labels.length > 60) {
        C.connH.data.labels.shift();
        C.connH.data.datasets[0].data.shift();
    }
    C.connH.update('none');
}

/**
 * Normaliza los datos de bases de datos al formato { name, size_mb }
 * maneja múltiples key names que el backend podría usar:
 *   - schema / name / SCHEMA_NAME / database
 *   - size_mb / size_bytes / size / total_bytes
 */
function normalizeDBData(raw) {
    if (!Array.isArray(raw)) return [];

    return raw.map(row => {
        // Nombre: probar varias keys posibles
        const name = row.schema
            || row.name
            || row.SCHEMA_NAME
            || row.database
            || 'unknown';

        // Tamaño: probar varias keys, convertir a MB si viene en bytes
        let sizeMB = 0;
        if (row.size_mb !== undefined && row.size_mb !== null) {
            sizeMB = Number(row.size_mb);
        } else if (row.size_bytes !== undefined && row.size_bytes !== null) {
            sizeMB = Number(row.size_bytes) / (1024 * 1024);
        } else if (row.size !== undefined && row.size !== null) {
            // Si "size" es > 100000, asumimos que son bytes
            sizeMB = Number(row.size) > 100000
                ? Number(row.size) / (1024 * 1024)
                : Number(row.size);
        } else if (row.total_bytes !== undefined && row.total_bytes !== null) {
            sizeMB = Number(row.total_bytes) / (1024 * 1024);
        }

        return { name, size_mb: Math.round(sizeMB * 100) / 100 };
    });
}

function updateDBSizeDonut(raw) {
    if (!C.dbSize) return;

    const dbs = normalizeDBData(raw);
    const sorted = dbs
        .filter(d => d.size_mb > 0)
        .sort((a, b) => b.size_mb - a.size_mb);

    const top = sorted.slice(0, 8);
    const rest = sorted.slice(8);
    const otherMB = rest.reduce((s, d) => s + d.size_mb, 0);

    const labels = top.map(d => d.name);
    const sizes  = top.map(d => d.size_mb);

    if (otherMB > 0) {
        labels.push('Otros');
        sizes.push(Math.round(otherMB * 100) / 100);
    }

    C.dbSize.data.labels = labels;
    C.dbSize.data.datasets[0].data = sizes;
    C.dbSize.update('none');
}

/* ══════════════════════════════════════
   UTILIDADES
   ══════════════════════════════════════ */

function ts() {
    const n = new Date();
    return [n.getHours(), n.getMinutes(), n.getSeconds()]
        .map(v => String(v).padStart(2, '0'))
        .join(':');
}




