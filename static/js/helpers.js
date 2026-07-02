// static/js/helpers.js
export function setText(id,v){const e=document.getElementById(id);if(e)e.textContent=v}
export function setBar(id,pct){const e=document.getElementById(id);if(e)e.style.width=Math.min(100,pct)+'%'}
export function esc(s){if(!s)return'';const d=document.createElement('div');d.textContent=s;return d.innerHTML}
export function formatNum(n){if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return n}
export function showToast(m){document.getElementById('toastBd').innerHTML='<i class="bi bi-check-circle-fill me-2" style="color:var(--accent)"></i>'+m;new bootstrap.Toast(document.getElementById('toastEl')).show()}

export function updateSidebarStatus(c){
  const d=document.getElementById('sbDot'),s=document.getElementById('sbStatus'),h=document.getElementById('sbHost');
  if(c){d.className='sdot on';s.textContent='MySQL 5.7 — Online';h.textContent=''}else{d.className='sdot off';s.textContent='Sin conexión';h.textContent='—'}
}

export function setWSStatus(on,id,prefix){
  const b=document.getElementById(id);if(!b)return;
  b.className='ws-badge '+(on?'on':'off');
  b.textContent=(prefix||'WS')+' '+(on?'ON':'OFF');
}

export const chartOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: false,
    },
    tooltip: {
      backgroundColor: "#0f1629",
      borderColor: "#1a2540",
      borderWidth: 1,
      titleColor: "#eef2f7",
      bodyColor: "#8b9dc3",
      padding: 10,
      cornerRadius: 7,
      displayColors: false,
    },
  },
  scales: {
    x: {
      grid: {
        color: "rgba(255,255,255,.04)",
      },
      ticks: {
        color: "#5a6e8a",
        font: {
          size: 10,
        },
        maxTicksLimit: 10,
      },
    },
    y: {
      grid: {
        color: "rgba(255,255,255,.04)",
      },
      ticks: {
        color: "#5a6e8a",
        font: {
          size: 10,
        },
      },
    },
  },
  animation: false,
};