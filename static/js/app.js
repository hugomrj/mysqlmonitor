//static/js/app.js
import { setText, setBar, esc, formatNum, showToast, updateSidebarStatus, setWSStatus } from './helpers.js';
import { initDashboard, updateDashboard } from './pages/dashboard.js';
import { loadResourceCharts } from './pages/resources.js';
import { loadSlowQueries, clearSlowHistory } from './pages/slow.js';

import { loadAudit } from './pages/audit.js';
import { loadRecentQueries, initRecent, clearRecentQueries } from './pages/recent.js';

// ═══ EXPONER AL GLOBAL para onclick del HTML ═══
window.loadSlowQueries = loadSlowQueries;
window.clearSlowHistory = clearSlowHistory;

window.setText = setText;
window.setBar = setBar;
window.esc = esc;
window.formatNum = formatNum;
window.showToast = showToast;
window.loadAudit = loadAudit;
window.loadRecentQueries = loadRecentQueries;  // NUEVO
window.clearRecentQueries = clearRecentQueries;  // NUEVO

let ws = null;
let curPage = 'dashboard';

// ── NAVEGACIÓN ──
const titles = {
    dashboard:'Dashboard', 
    slow:'Consultas Lentas', 
    
    recent:'Consultas Recientes',  // NUEVO
    databases:'Bases de Datos', 
    tables:'Tablas', 
    users:'Usuarios Conectados',
    resources:'Recursos del Servidor', 
    alerts:'Alertas', 
    audit:'Auditoría'
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
    
    if(p==='audit') loadAudit();
    if(p==='recent') initRecent();  // NUEVO
    
    document.getElementById('mc').scrollTop=0;
};

// ── WEBSOCKET PRINCIPAL ──
function connectWS(){
    const p=location.protocol==='https:'?'wss':'ws';
    ws=new WebSocket(`${p}://${location.host}/ws/metrics`);
    
    ws.onopen=()=>{
        const badge = document.getElementById('wsBadge');
        if(badge) badge.style.display = 'none';
        try {
            const data = { mysql_status: { mysql_connected: true } };
            updateSidebarStatus(true);
        } catch(x){}
    };
    
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
    
    ws.onclose=()=>{
        const badge = document.getElementById('wsBadge');
        if(badge) {
            badge.style.display = '';
            badge.textContent = 'OFF';
            badge.className = 'ws-badge off';
        }
        updateSidebarStatus(false);
        setTimeout(connectWS,3000);
    };
    
    ws.onerror=()=>ws.close();
}

// ── WEBSOCKET BINLOG (Tiempo Real) ──
function connectBinlogWS(){
    const p=location.protocol==='https:'?'wss':'ws';
    blWs=new WebSocket(`${p}://${location.host}/ws/binlog`);
    
    blWs.onopen=()=>{
        setWSStatus(true,'blWsBadge','BINLOG');
        document.getElementById('blWsBadge').style.display='';
    };
    
    blWs.onmessage=e=>{
        try{
            const msg=JSON.parse(e.data);
            if(msg.type==='binlog_event'){
                if(typeof window.handleBinlogEvent === 'function'){
                    window.handleBinlogEvent(msg.data);
                }
                if(curPage === 'audit' && typeof window.loadAudit === 'function'){
                    if(Math.random() < 0.2) window.loadAudit();
                }
            }
        }catch(x){}
    };
    
    blWs.onclose=()=>{
        setWSStatus(false,'blWsBadge','BINLOG');
        setTimeout(connectBinlogWS,3000);
    };
    
    blWs.onerror=()=>blWs.close();
}

let blWs = null;

// ── ESTADO DEL BINLOG (Indicador Sidebar) ──
async function checkBinlogIndicator(){
    try {
        const r = await fetch('/api/binlog/status');
        const s = await r.json();
        const dot = document.getElementById('auditBlDot');
        if(!dot) return;
        
        if(s.enabled){
            dot.className = 'bl-pulse live';
            dot.title = 'Binlog activo y leyendo';
        } else if(s.error) {
            dot.className = 'bl-pulse dead';
            dot.title = 'Error: ' + s.error;
        } else {
            dot.className = 'bl-pulse wait';
            dot.title = 'Binlog pendiente o reconectando...';
        }
    } catch(e) {
        const dot = document.getElementById('auditBlDot');
        if(dot) dot.className = 'bl-pulse dead';
    }
}

// ── INIT ──
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nli').forEach(l=>l.addEventListener('click',()=>go(l.dataset.p)));
    document.getElementById('bhbtn').addEventListener('click',()=>{document.getElementById('sb').classList.toggle('open');document.getElementById('sov').classList.toggle('show')});
    document.getElementById('sov').addEventListener('click',()=>{document.getElementById('sb').classList.remove('open');document.getElementById('sov').classList.remove('show')});
    
    connectWS();
    connectBinlogWS();  
    
    checkBinlogIndicator();
    setInterval(checkBinlogIndicator, 30000);
    
    // Auto-refresh de consultas recientes cada 2 segundos cuando la página está activa
    setInterval(() => {
        if(curPage === 'recent') loadRecentQueries();
    }, 2000);
    
    go('dashboard');
});