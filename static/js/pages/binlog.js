// static/js/pages/binlog.js
import { setText, esc } from '../helpers.js';

// ── Estado local ──
let blEvents = [];
const BL_FEED_MAX = 200;
let blAutoScroll = true;
export let binlog_service_stats = null; // Compartida con app.js para los charts

const C = {};

// ── Funciones que APP.JS necesita (Exportadas) ──
export function initBinlog() {
    initBlCharts();
    pollBinlogStatus();
    loadBinlogStats();
    if(!blEvents.length) loadBinlogHistory();
}

export function handleBinlogEvent(ev){
  const ft=document.getElementById('blFilterType').value;
  const fs=document.getElementById('blFilterSchema').value.trim().toLowerCase();
  const fb=document.getElementById('blFilterTable').value.trim().toLowerCase();
  if(ft&&ev.event_type!==ft) return;
  if(fs&&!(ev.schema||'').toLowerCase().includes(fs)) return;
  if(fb&&!(ev.table||'').toLowerCase().includes(fb)) return;

  if(!ev.row_preview && ev.row_data) {
    try {
      const rows = typeof ev.row_data === 'string' ? JSON.parse(ev.row_data) : ev.row_data;
      if(rows && rows.length > 0) ev.row_preview = rows[0];
    } catch(e){}
  }

  blEvents.unshift(ev);
  if(blEvents.length>BL_FEED_MAX) blEvents.length=BL_FEED_MAX;
  renderBinlogFeed();
}

export async function pollBinlogStatus(){
  try{
    const r=await fetch('/api/binlog/status');
    const s=await r.json();
    binlog_service_stats=s;
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

    renderBlTopTables(s.tables_hot||[]);
    updateBlTypeChart(s.insert_count||0,s.update_count||0,s.delete_count||0);
  }catch(e){}
}

export async function loadBinlogStats(){
  try{
    const r=await fetch('/api/binlog/stats');
    const s=await r.json();
    updateBlTimeChart(s.per_minute||[]);
  }catch(e){}
}

export async function loadBinlogHistory(){
  const ft=document.getElementById('blFilterType').value;
  const fs=document.getElementById('blFilterSchema').value.trim();
  const fb=document.getElementById('blFilterTable').value.trim();
  let url='/api/binlog/events?limit=200&include_data=true';
  if(ft) url+='&event_type='+ft;
  if(fs) url+='&schema='+encodeURIComponent(fs);
  if(fb) url+='&table='+encodeURIComponent(fb);
  try{
    const r=await fetch(url);
    blEvents=await r.json();
    renderBinlogFeed();
  }catch(e){}
}

// ── Funciones que el HTML llama por onclick (Window) ──
window.toggleBlDetail = function(row, idx) {
  const detailRow = row.nextElementSibling;
  const icon = row.querySelector('i');
  const isVisible = detailRow.style.display !== 'none';
  
  document.querySelectorAll('.bl-detail-row').forEach(r => r.style.display = 'none');
  document.querySelectorAll('.bl-feed i.bi-chevron-right').forEach(i => i.style.transform = '');
  
  if (!isVisible) {
    detailRow.style.display = '';
    icon.style.transform = 'rotate(90deg)';
    
    const ev = blEvents[idx];
    let detailContent = '';
    
    if(ev.row_preview) {
      if(ev.event_type === 'UPDATE' && ev.row_preview.before && ev.row_preview.after) {
        detailContent = '<div style="margin-bottom:8px; color:var(--danger); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.5px">Antes</div>' + formatRowData(ev.row_preview.before);
        detailContent += '<div style="margin:12px 0 8px; color:var(--success); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.5px">Después</div>' + formatRowData(ev.row_preview.after);
      } else {
        detailContent = formatRowData(ev.row_preview.values || ev.row_preview);
      }
    } else {
      detailContent = '<span class="text-muted">Preview no disponible.</span>';
    }
    
    document.getElementById('blDetail-'+idx).innerHTML = detailContent;
  }
};

window.clearBinlogHistory = async function(){
  if(!confirm('¿Limpiar todo el historial de eventos del binlog?')) return;
  try{
    await fetch('/api/binlog/events',{method:'DELETE'});
    blEvents=[];
    renderBinlogFeed();
    import('../helpers.js').then(h => h.showToast('Historial de binlog limpiado'));
  }catch(e){}
};

window.restartBinlog = async function(){
  try{
    await fetch('/api/binlog/restart',{method:'POST'});
    import('../helpers.js').then(h => h.showToast('Streamer de binlog reiniciado'));
  }catch(e){}
};


// ── Funciones internas (Sin export) ──
function renderBinlogFeed(){
  const body=document.getElementById('blFeedBody');
  if(!blEvents.length){body.innerHTML='<tr><td colspan="7" class="empty-state"><i class="bi bi-broadcast-pin"></i><p>Esperando eventos del binlog...</p></td></tr>';return}
  document.getElementById('blFeedCount').textContent=blEvents.length+' eventos';

  const show=blEvents.slice(0,100);
  let html='';
  show.forEach((ev, idx) => {
    const t=ev.event_type||'?';
    const cls=t==='INSERT'?'bl-insert':t==='UPDATE'?'bl-update':t==='DELETE'?'bl-delete':'';
    const bsCls=t==='INSERT'?'bs-s':t==='UPDATE'?'bs-w':t==='DELETE'?'bs-d':'bs-m';
    const time=ev.event_time?ev.event_time.slice(11,19):'—';
    
    let previewHtml = '<span class="text-muted" style="font-size:11px">—</span>';
    if(ev.row_preview) {
      let obj = ev.row_preview;
      if(obj.after) obj = obj.after;
      else if(obj.values) obj = obj.values;
      
      const parts = Object.entries(obj).slice(0, 3).map(([k,v]) => 
        `<span style="color:var(--text-muted)">${esc(k)}:</span> <span style="color:var(--accent)">${esc(String(v).substring(0, 20))}</span>`
      );
      const extra = Object.keys(obj).length > 3 ? '…' : '';
      previewHtml = `<div style="font-size:11px; line-height:1.4; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${parts.join(', ')}${extra}</div>`;
    }
    
    html += `<tr class="${cls}" style="cursor:pointer" onclick="toggleBlDetail(this, ${idx})">
      <td style="width:30px"><i class="bi bi-chevron-right" style="font-size:10px; transition: transform .2s"></i></td>
      <td class="text-muted" style="font-size:11.5px;white-space:nowrap">${time}</td>
      <td><span class="bs ${bsCls}">${t}</span></td>
      <td><span class="fd" style="font-weight:600;font-size:12px">${esc(ev.schema)}.${esc(ev.table)}</span></td>
      <td>${previewHtml}</td>
      <td class="fd" style="font-weight:600">${ev.affected_rows||1}</td>
      <td class="text-muted" style="font-size:11px;white-space:nowrap">${esc(ev.log_file)}:${ev.log_pos}</td>
    </tr>
    <tr class="bl-detail-row" style="display:none">
      <td colspan="7" style="padding:0 14px 14px 50px; background: rgba(0,0,0,.2)">
        <div class="codeb" style="font-size:11.5px; max-height:150px; overflow-y:auto" id="blDetail-${idx}">Cargando...</div>
      </td>
    </tr>`;
  });
  body.innerHTML = html;

  if(blAutoScroll){
    const wrap=document.getElementById('blFeedWrap');
    wrap.scrollTop=0;
  }
}

function formatRowData(obj) {
  if(!obj || typeof obj !== 'object') return '';
  return Object.entries(obj).map(([k, v]) => {
    const val = v === null ? 'NULL' : String(v);
    const display = val.length > 100 ? val.substring(0, 100) + '…' : val;
    const color = v === null ? 'var(--text-muted)' : 'var(--accent)';
    return `<span style="color:var(--info)">${esc(k)}</span>: <span style="color:${color}">${esc(display)}</span>`;
  }).join('<br>');
}

function renderBlTopTables(tables){
  const el=document.getElementById('blTopTables');
  if(!tables.length){el.innerHTML='<div class="empty-state" style="padding:16px"><p>Sin datos</p></div>';return}
  const max=tables[0][1];
  el.innerHTML=tables.slice(0,8).map(([name,cnt])=>{
    const pct=max>0?((cnt/max)*100).toFixed(0):0;
    return `<div class="top-table-item">
      <div><div class="fd" style="font-size:12px;font-weight:600">${esc(name)}</div><div class="text-muted" style="font-size:10.5px">${cnt} eventos</div></div>
      <div style="width:80px"><div style="background:var(--border);height:4px;border-radius:2px"><div class="top-table-bar" style="width:${pct}%"></div></div></div>
    </div>`;
  }).join('');
}

// ── Charts Internos ──
function initBlCharts(){
  if(C.blType)return;
  const cO={responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{backgroundColor:'#0f1629',borderColor:'#1a2540',borderWidth:1,titleColor:'#eef2f7',bodyColor:'#8b9dc3',padding:10,cornerRadius:7,displayColors:false}},scales:{x:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#5a6e8a',font:{size:10},maxTicksLimit:10}},y:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#5a6e8a',font:{size:10}}}},animation:false};

  C.blType=new Chart(document.getElementById('cBlType'),{
    type:'doughnut',
    data:{labels:['INSERT','UPDATE','DELETE'],datasets:[{data:[0,0,0],backgroundColor:['rgba(34,197,94,.7)','rgba(245,158,11,.7)','rgba(239,68,68,.7)'],borderColor:'#0f1629',borderWidth:3,hoverOffset:6}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'60%',plugins:{legend:{position:'bottom',labels:{color:'#8b9dc3',font:{size:10},padding:8,usePointStyle:true,pointStyleWidth:8}},tooltip:{...cO.plugins.tooltip}}}
  });
  C.blTime=new Chart(document.getElementById('cBlTime'),{
    type:'line',
    data:{labels:[],datasets:[
      {label:'INSERT',data:[],borderColor:'#22c55e',backgroundColor:'rgba(34,197,94,.08)',borderWidth:1.5,fill:true,tension:.3,pointRadius:0,stacked:true},
      {label:'UPDATE',data:[],borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,.08)',borderWidth:1.5,fill:true,tension:.3,pointRadius:0,stacked:true},
      {label:'DELETE',data:[],borderColor:'#ef4444',backgroundColor:'rgba(239,68,68,.08)',borderWidth:1.5,fill:true,tension:.3,pointRadius:0,stacked:true},
    ]},
    options:{...cO,plugins:{...cO.plugins,legend:{display:true,position:'top',align:'end',labels:{color:'#8b9dc3',font:{size:10},padding:12,usePointStyle:true,pointStyleWidth:8,boxWidth:8}}},scales:{...cO.scales,y:{...cO.scales.y,stacked:true,beginAtZero:true}}}
  });
}

function updateBlTypeChart(ins,upd,del){
  if(!C.blType)return;
  C.blType.data.datasets[0].data=[ins,upd,del];
  C.blType.update('none');
}

function updateBlTimeChart(perMinute){
  if(!C.blTime)return;
  const labels=perMinute.map(p=>{const m=p.minute||'';return m.slice(11)||m});
  const totals=perMinute.map(p=>p.cnt||0);
  C.blTime.data.labels=labels;
  const s=binlog_service_stats||{insert_count:1,update_count:1,delete_count:1};
  const total=s.insert_count+s.update_count+s.delete_count||1;
  const pI=s.insert_count/total, pU=s.update_count/total, pD=s.delete_count/total;
  C.blTime.data.datasets[0].data=totals.map(t=>Math.round(t*pI));
  C.blTime.data.datasets[1].data=totals.map(t=>Math.round(t*pU));
  C.blTime.data.datasets[2].data=totals.map(t=>Math.round(t*pD));
  C.blTime.update('none');
}

// ── Auto-scroll ──
document.addEventListener('DOMContentLoaded',()=>{
  const wrap=document.getElementById('blFeedWrap');
  if(wrap){
    let scrollTimeout;
    wrap.addEventListener('scroll',()=>{
      blAutoScroll=false;
      clearTimeout(scrollTimeout);
      scrollTimeout=setTimeout(()=>{blAutoScroll=true},3000);
    });
  }
});