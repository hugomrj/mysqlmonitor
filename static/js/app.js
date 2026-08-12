import { setText, setBar, esc, formatNum, showToast, updateSidebarStatus, setWSStatus } from './helpers.js';
import { initDashboard, updateDashboard } from './pages/dashboard.js';
import { loadResourceCharts } from './pages/resources.js';
import { loadSlowQueries, clearSlowHistory } from './pages/slow.js';
import { loadQueries } from './pages/queries.js';
import { loadAudit } from './pages/audit.js';

// ═══ EXPONER AL GLOBAL para onclick del HTML ═══
window.loadSlowQueries = loadSlowQueries;
window.clearSlowHistory = clearSlowHistory;
window.loadQueries = loadQueries;
window.setText = setText;
window.setBar = setBar;
window.esc = esc;
window.formatNum = formatNum;
window.showToast = showToast;
window.loadAudit = loadAudit;

let ws = null;
let curPage = 'dashboard';

// ── NAVEGACIÓN ──
const titles = {
    dashboard:'Dashboard', slow:'Consultas Lentas', queries:'Consultas',
    databases:'Bases de Datos', tables:'Tablas', users:'Usuarios Conectados',
    resources:'Recursos del Servidor', alerts:'Alertas', audit:'Auditoría'
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
    if(p==='audit') loadAudit();
    
    document.getElementById('mc').scrollTop=0;
};






// ── WEBSOCKET PRINCIPAL ──
function connectWS(){
    const p=location.protocol==='https:'?'wss':'ws';
    ws=new WebSocket(`${p}://${location.host}/ws/metrics`);
    
    ws.onopen=()=>{
        // Si está conectado, OCULTAMOS el badge completamente
        const badge = document.getElementById('wsBadge');
        if(badge) badge.style.display = 'none';
        
        // El resto de la lógica del onopen sigue igual
        try {
            const data = { mysql_status: { mysql_connected: true } }; // Simulación temporal hasta llegar el primer mensaje real
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
        // Si se desconecta, MOSTRAMOS el badge con "OFF"
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
                // Si existe la función de auditoría, llamarla
                if(typeof window.handleBinlogEvent === 'function'){
                    window.handleBinlogEvent(msg.data);
                }
                // También actualizar la sección de auditoría si está activa
                if(curPage === 'audit' && typeof window.loadAudit === 'function'){
                    // Recargar auditoría cada 5 eventos para no saturar
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

// Variable global para el WebSocket de binlog
let blWs = null;




// ── ESTADO DEL BINLOG (Indicador Sidebar) ──
async function checkBinlogIndicator(){
    try {
        const r = await fetch('/api/binlog/status');
        const s = await r.json();
        const dot = document.getElementById('auditBlDot');
        if(!dot) return;
        
        if(s.enabled){
            dot.className = 'bl-pulse live'; // Verde: Leyendo eventos
            dot.title = 'Binlog activo y leyendo';
        } else if(s.error) {
            dot.className = 'bl-pulse dead'; // Rojo: Error
            dot.title = 'Error: ' + s.error;
        } else {
            dot.className = 'bl-pulse wait'; // Amarillo: Intentando reconectar
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
    
    // Conectar ambos WebSockets
    connectWS();
    connectBinlogWS();  
    
    // Iniciar indicador del binlog
    checkBinlogIndicator();
    setInterval(checkBinlogIndicator, 30000);
    
    go('dashboard');
});