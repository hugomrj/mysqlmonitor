// static/js/app.js

import { setText, setBar, esc, formatNum, showToast, updateSidebarStatus, setWSStatus } from './helpers.js';
import { initDashboard, updateDashboard } from './pages/dashboard.js';
import { loadResourceCharts } from './pages/resources.js';
import { loadSlowQueries, clearSlowHistory } from './pages/slow.js';
import { loadQueries } from './pages/queries.js';
import { initBinlog, pollBinlogStatus, loadBinlogHistory, loadBinlogStats } from './pages/binlog.js';

// ═══ EXPONER AL GLOBAL para onclick del HTML ═══
window.loadSlowQueries = loadSlowQueries;
window.clearSlowHistory = clearSlowHistory;
window.loadQueries = loadQueries;
window.setText = setText;
window.setBar = setBar;
window.esc = esc;
window.formatNum = formatNum;
window.showToast = showToast;
window.restartBinlog = async () => {
    try { await fetch('/api/binlog/restart', {method:'POST'}); showToast('Streamer reiniciado'); } catch(e){}
};
window.clearBinlogHistory = async () => {
    if(!confirm('¿Limpiar historial de binlog?')) return;
    try { await fetch('/api/binlog/events',{method:'DELETE'}); window.blEvents=[]; if(typeof window.renderBinlogFeed==='function')window.renderBinlogFeed(); showToast('Historial limpiado'); } catch(e){}
};
window.loadBinlogHistory = loadBinlogHistory;

let ws = null, blWs = null;
let curPage = 'dashboard';

// ── NAVEGACIÓN ──
const titles = {
    dashboard:'Dashboard', slow:'Consultas Lentas', queries:'Consultas',
    databases:'Bases de Datos', tables:'Tablas', users:'Usuarios Conectados',
    resources:'Recursos del Servidor', alerts:'Alertas', binlog:'Binlog Live'
};

window.go = function(p) {
    document.querySelectorAll('.ps').forEach(s=>s.classList.remove('active'));
    const el=document.getElementById('p-'+p);
    if(el){el.classList.add('active');el.style.animation='none';el.offsetHeight;el.style.animation=''}
    document.querySelectorAll('.nli').forEach(l=>l.classList.remove('active'));
    const lk=document.querySelector(`.nli[data-p="${p}"]`);if(lk)lk.classList.add('active');
    document.getElementById('ptitle').textContent=titles[p]||p;
    document.getElementById('sb').classList.remove('open');
    document.getElementById('sov').classList.remove('show');
    curPage = p;

    if(p==='dashboard') initDashboard();
    if(p==='resources') loadResourceCharts();
    if(p==='slow') loadSlowQueries();
    if(p==='queries') loadQueries();
    if(p==='binlog'){ pollBinlogStatus(); loadBinlogStats(); if(!window.blEvents.length) loadBinlogHistory(); }
    document.getElementById('mc').scrollTop=0;
};

// ── WEBSOCKETS ──
function connectWS(){
    const p=location.protocol==='https:'?'wss':'ws';
    ws=new WebSocket(`${p}://${location.host}/ws/metrics`);
    ws.onopen=()=>setWSStatus(true,'wsBadge','WS');
    ws.onmessage=e=>{
        try{
            const data=JSON.parse(e.data);
            const st=data.mysql_status||{};
            const isConnected=st.mysql_connected===true;
            updateSidebarStatus(isConnected);
            if(!isConnected&&!sessionStorage.getItem('configShown')){sessionStorage.setItem('configShown','1');window.showConfigModal()}
            if(curPage==='dashboard') updateDashboard(data);
            if(curPage==='resources') loadResourceCharts();
        }catch(x){}
    };
    ws.onclose=()=>{setWSStatus(false,'wsBadge','WS');setTimeout(connectWS,3000)};
    ws.onerror=()=>ws.close();
}

function connectBinlogWS(){
    const p=location.protocol==='https:'?'wss':'ws';
    blWs=new WebSocket(`${p}://${location.host}/ws/binlog`);
    blWs.onopen=()=>{setWSStatus(true,'blWsBadge','BINLOG');document.getElementById('blWsBadge').style.display=''};
    blWs.onmessage=e=>{try{const msg=JSON.parse(e.data);if(msg.type==='binlog_event')window.handleBinlogEvent(msg.data)}catch(x){}};
    blWs.onclose=()=>{setWSStatus(false,'blWsBadge','BINLOG');setTimeout(connectBinlogWS,3000)};
    blWs.onerror=()=>blWs.close();
}

// ── BINLOG STATE ──
window.blEvents = [];
const BL_FEED_MAX = 200;

window.handleBinlogEvent = function(ev) {
    const ft=document.getElementById('blFilterType')?.value;
    const fs=document.getElementById('blFilterSchema')?.value.trim().toLowerCase();
    const fb=document.getElementById('blFilterTable')?.value.trim().toLowerCase();
    if(ft&&ev.event_type!==ft) return;
    if(fs&&!(ev.schema||'').toLowerCase().includes(fs)) return;
    if(fb&&!(ev.table||'').toLowerCase().includes(fb)) return;
    if(!ev.row_preview&&ev.row_data){try{const rows=typeof ev.row_data==='string'?JSON.parse(ev.row_data):ev.row_data;if(rows?.length)ev.row_preview=rows[0]}catch(e){}}
    window.blEvents.unshift(ev);
    if(window.blEvents.length>BL_FEED_MAX) window.blEvents.length=BL_FEED_MAX;
    if(typeof window.renderBinlogFeed==='function') window.renderBinlogFeed();
};

window.pollBinlogStatus = async function(){
    try{
        const r=await fetch('/api/binlog/status');const s=await r.json();
        setText('blTotal',(s.total_events||0).toLocaleString());
        setText('blEPS',s.events_per_second||'0');
        setText('blIns',(s.insert_count||0).toLocaleString());
        setText('blUpd',(s.update_count||0).toLocaleString());
        setText('blDel',(s.delete_count||0).toLocaleString());
        const dot=document.getElementById('blStatusDot'),txt=document.getElementById('blStatusText'),pos=document.getElementById('blPosText'),errEl=document.getElementById('blErrorText'),navDot=document.getElementById('blNavDot');
        if(s.streamer_running){dot.className='bl-pulse live';txt.textContent='Leyendo binlog';txt.style.color='var(--success)';navDot.className='bl-pulse live ms-auto'}
        else if(s.error){dot.className='bl-pulse dead';txt.textContent='Error';txt.style.color='var(--danger)';navDot.className='bl-pulse dead ms-auto';errEl.style.display='block';errEl.textContent=s.error}
        else{dot.className='bl-pulse wait';txt.textContent='Reconectando...';txt.style.color='var(--warning)';navDot.className='bl-pulse wait ms-auto'}
        if(s.current_log_file) pos.textContent=s.current_log_file+':'+s.current_log_pos;
        errEl.style.display=s.error?'block':'none';
    }catch(e){}
};

window.loadBinlogStats = async function(){
    try{const r=await fetch('/api/binlog/stats');const s=await r.json();if(typeof window.updateBlTimeChart==='function')window.updateBlTimeChart(s.per_minute||[])}catch(e){}
};

window.loadBinlogHistory = async function(){
    const ft=document.getElementById('blFilterType')?.value;
    const fs=document.getElementById('blFilterSchema')?.value.trim();
    const fb=document.getElementById('blFilterTable')?.value.trim();
    let url='/api/binlog/events?limit=200&include_data=true';
    if(ft) url+='&event_type='+ft;
    if(fs) url+='&schema='+encodeURIComponent(fs);
    if(fb) url+='&table='+encodeURIComponent(fb);
    try{const r=await fetch(url);window.blEvents=await r.json();if(typeof window.renderBinlogFeed==='function')window.renderBinlogFeed()}catch(e){}
};

// ── INIT ──
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nli').forEach(l=>l.addEventListener('click',()=>go(l.dataset.p)));
    document.getElementById('bhbtn').addEventListener('click',()=>{document.getElementById('sb').classList.toggle('open');document.getElementById('sov').classList.toggle('show')});
    document.getElementById('sov').addEventListener('click',()=>{document.getElementById('sb').classList.remove('open');document.getElementById('sov').classList.remove('show')});
    connectWS();
    connectBinlogWS();
    go('dashboard');
});