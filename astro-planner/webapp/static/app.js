/* 天文观测计划生成器前端 (原生 JS + Canvas, 无外部依赖) */
"use strict";

const $ = (id) => document.getElementById(id);
let DATA = null;                 // /api/plan 完整返回
let CATALOG = [];
let SITES = [];
let animTimer = null;
const colors = ["#5aa2ff","#49d17d","#ffb84d","#ff8fa3","#7fe0e0","#c08cff",
                "#f48fb1","#9ccc65","#ffab73","#80cbc4","#b39ddb","#fff176",
                "#4fc3f7","#aed581","#ff8a65","#ba68c8"];
const colorOf = (name) => {
  let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return colors[h % colors.length];
};

/* ------------------------------------------------------------ 初始化 */

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}

async function init() {
  const r = await fetch("/api/sites");
  const meta = await r.json();
  SITES = meta.sites; CATALOG = meta.catalog;
  $("site").innerHTML = SITES.map(s => `<option>${s}</option>`).join("");
  $("date").value = todayStr();
  $("site").value = SITES.includes("兴隆观测站") ? "兴隆观测站" : SITES[0];

  buildTargetTable(CATALOG);
  $("generate").addEventListener("click", () => generate(false));
  $("autoOrder").addEventListener("click", () => {
    if (!DATA) return;
    generate(true);
  });
  $("site").addEventListener("change", () => {
    const s = $("site").value;
    // 站点切换仅在用户没手动改坐标时回填
  });
  $("timeSlider").addEventListener("input", onTimeMove);
  $("playBtn").addEventListener("click", togglePlay);
  await generate(false);
}

function readTargets() {
  const rows = [...$("targetTable").querySelectorAll("tbody tr")];
  return rows.map(tr => ({
    name: tr.dataset.name,
    ra_deg: parseFloat(tr.querySelector(".f-ra").value),
    dec_deg: parseFloat(tr.querySelector(".f-dec").value),
    priority: parseInt(tr.querySelector(".f-pri").value, 10),
    exposure_s: parseFloat(tr.querySelector(".f-exp").value),
    n_frames: parseInt(tr.querySelector(".f-n").value, 10),
    min_alt: parseFloat(tr.querySelector(".f-alt").value),
    avoid_moon: tr.querySelector(".f-moon").checked,
    moon_sep: parseFloat(tr.querySelector(".f-sep").value),
    note: tr.dataset.note || "",
  }));
}

function buildTargetTable(targets) {
  const tb = $("targetTable").querySelector("tbody");
  tb.innerHTML = targets.map(t => `
    <tr data-name="${escapeHtml(t.name)}" data-note="${escapeHtml(t.note||"")}">
      <td>${escapeHtml(t.name)}</td>
      <td><input class="f-ra" type="number" step="0.01" value="${t.ra_deg}"></td>
      <td><input class="f-dec" type="number" step="0.01" value="${t.dec_deg}"></td>
      <td><input class="f-pri" type="number" min="1" max="5" value="${t.priority}" style="width:52px"></td>
      <td><input class="f-exp" type="number" step="10" min="10" value="${t.exposure_s}" style="width:74px"></td>
      <td><input class="f-n" type="number" min="1" value="${t.n_frames}" style="width:58px"></td>
      <td><input class="f-alt" type="number" min="0" max="90" value="${t.min_alt}" style="width:60px"></td>
      <td style="text-align:center"><input class="f-moon" type="checkbox" ${t.avoid_moon ? "checked" : ""}></td>
      <td><input class="f-sep" type="number" min="0" max="180" value="${t.moon_sep}" style="width:60px"></td>
      <td class="f-stat">—</td>
    </tr>`).join("");
}

function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

/* ------------------------------------------------------------ 请求 */

function sitePayload() {
  const lat = parseFloat($("lat").value), lon = parseFloat($("lon").value);
  if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
    return {name:"自定义", lat, lon, elev: parseFloat($("elev").value)||0};
  }
  return $("site").value;
}

async function generate(resetOrder) {
  const status = $("status");
  status.textContent = "计算中…"; status.style.color = "var(--dim)";
  const payload = {
    site: sitePayload(),
    date: $("date").value,
    utc_offset: parseFloat($("tz").value),
    horizon: $("horizon").value,
    targets: readTargets(),
    settings: {
      min_alt_global: parseFloat($("minAlt").value),
      max_hour_angle: parseFloat($("maxHA").value),
      step_seconds: parseInt($("step").value, 10),
      slew_minutes: parseFloat($("slew").value),
      mount_flip_hours: parseFloat($("flip").value) / 60.0,
    },
  };
  if (!resetOrder && DATA && DATA.plan) {
    // 重新生成默认自动排序; 若用户当前是手工顺序, 由按钮“恢复自动排序”显式重置
  }
  try {
    const r = await fetch("/api/plan", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(payload),
    });
    if (!r.ok) { status.textContent = await r.text(); status.style.color="var(--bad)"; return; }
    DATA = await r.json();
    status.textContent = "完成"; status.style.color = "var(--good)";
    renderAll();
  } catch (e) {
    status.textContent = "请求失败: " + e; status.style.color = "var(--bad)";
  }
}

/* 仅按新顺序在前端重新排程(复用已算出的星历) */
async function reorder(order) {
  const status = $("status");
  status.textContent = "重新排程…";
  const targets = DATA.targets.map(t => ({
    ...t.target,
    // 保留计算时的窗口: 直接把整份 DATA.targets/ sun/moon 传回不现实,
    // 因此重新请求一次后端(步长可较大时很快), 但带上 order。
  }));
  const payload = {
    site: sitePayload(), date: DATA.date, utc_offset: DATA.utc_offset,
    horizon: $("horizon").value,
    targets: DATA.targets.map(t => t.target),
    settings: DATA.settings, order,
  };
  const r = await fetch("/api/plan", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload),
  });
  DATA = await r.json();
  status.textContent = "已按新顺序排程"; status.style.color = "var(--good)";
  renderAll();
}

/* ------------------------------------------------------------ 渲染总入口 */

function renderAll() {
  renderNightInfo();
  drawAltChart();
  setupTimeRange();
  drawSkyChart();
  renderPlan();
  renderTargetStats();
  renderWarnings();
}

/* ------------------------------------------------------------ 夜间信息 */

function renderNightInfo() {
  const s = DATA.sun, m = DATA.moon, site = DATA.site;
  const phaseTxt = m.illumination > 0.95 ? "满月" : m.illumination > 0.55 ? "凸月"
    : m.illumination > 0.45 ? "弦月" : m.illumination > 0.05 ? "娥眉/残月" : "新月";
  $("nightinfo").classList.remove("hidden");
  $("nightinfo").innerHTML = `
    <div class="night-grid">
      <span>观测点 <b>${escapeHtml(site.name)}</b> ${site.lat.toFixed(3)}°, ${site.lon.toFixed(3)}°</span>
      <span>民用暮光 <b>${hhmm(s.dusk_civil)} / ${hhmm(s.dawn_civil)}</b></span>
      <span>天文暗夜 <b>${hhmm(s.dusk_astro)} → ${hhmm(s.dawn_astro)}</b></span>
      <span class="moonico">🌙 照亮 <b>${(m.illumination*100).toFixed(0)}%</b> (${phaseTxt})</span>
      <span>月龄 <b>${m.age_days.toFixed(1)} 天</b></span>
      <span>半夜月亮 <b>${m.up_at_midnight ? "在地平线上 ⚠" : "已落下 ✓"}</b></span>
    </div>`;
}

function hhmm(h){
  if (h==null) return "--:--";
  // h 以地方 12:00 为 12 计, 可超过 24 (次日凌晨)
  const total=Math.round(h*60);
  const H=((Math.floor(total/60)%24)+24)%24, M=((total%60)+60)%60;
  return `${String(H).padStart(2,"0")}:${String(M).padStart(2,"0")}`;
}

/* ------------------------------------------------------------ Canvas 通用 */

function fitCanvas(cv) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = parseInt(cv.getAttribute("height"), 10);
  cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0);
  return {ctx, w, h};
}

/* ------------------------------------------------------------ 高度曲线 */

function drawAltChart() {
  const cv = $("altChart");
  const {ctx,w,h} = fitCanvas(cv);
  const hours = DATA.chart.hours;
  const x0=58, x1=w-14, y0=14, y1=h-30;
  const tmin=hours[0], tmax=hours[hours.length-1];
  const X = t => x0+(t-tmin)/(tmax-tmin)*(x1-x0);
  const Y = a => y1-(a+5)/95*(y1-y0);   // -5°..90°

  ctx.clearRect(0,0,w,h);
  // 夜间分区底色
  const bands = [
    [DATA.sun.dusk_civil, DATA.sun.dawn_civil, "rgba(40,60,110,0.28)"],
    [DATA.sun.dusk_astro, DATA.sun.dawn_astro, "rgba(8,12,28,0.55)"],
  ];
  for (const [a,b,c] of bands) {
    if (a==null) continue;
    ctx.fillStyle=c;
    ctx.fillRect(X(Math.max(a,tmin)), y0, X(Math.min(b,tmax))-X(Math.max(a,tmin)), y1-y0);
  }
  // 网格
  ctx.strokeStyle="rgba(120,140,190,.18)"; ctx.fillStyle="#8fa0c8";
  ctx.lineWidth=1; ctx.font="11px sans-serif"; ctx.textAlign="center";
  for (let hh=Math.ceil(tmin); hh<=Math.floor(tmax); hh++) {
    ctx.beginPath(); ctx.moveTo(X(hh),y0); ctx.lineTo(X(hh),y1); ctx.stroke();
    ctx.fillText(`${String(hh%24).padStart(2,"0")}:00`, X(hh), y1+16);
  }
  ctx.textAlign="right";
  for (let a=0; a<=90; a+=15) {
    ctx.beginPath(); ctx.moveTo(x0,Y(a)); ctx.lineTo(x1,Y(a)); ctx.stroke();
    ctx.fillText(a+"°", x0-6, Y(a)+4);
  }
  // 最低高度线
  ctx.strokeStyle="rgba(255,184,77,.6)"; ctx.setLineDash([4,4]);
  ctx.beginPath(); ctx.moveTo(x0,Y(DATA.settings.min_alt_global));
  ctx.lineTo(x1,Y(DATA.settings.min_alt_global)); ctx.stroke();
  ctx.setLineDash([]);

  // 太阳
  drawCurve(ctx, DATA.sun.alt, hours, X, Y, "#ffd36b", 1.4, false);

  // 月亮(只画在地平线附近以上的部分)
  drawCurve(ctx, DATA.moon.alt, hours, X, Y, "#e8e2b0", 1.4, false);

  // 目标曲线 + 可观测窗口加粗
  for (const t of DATA.targets) {
    const col = colorOf(t.target.name);
    ctx.strokeStyle=col; ctx.globalAlpha=.85;
    drawCurve(ctx, t.alt_app, hours, X, Y, col, 1.1, false);
    // 可观测段
    ctx.globalAlpha=1; ctx.lineWidth=2.6; ctx.strokeStyle=col;
    ctx.beginPath();
    let pen=false;
    t.mask.forEach((ok,i)=>{
      const xx=X(hours[i]), yy=Y(t.alt_app[i]);
      if (ok){ ctx.moveTo(xx,yy); pen=true; }
    });
    // 分段画, 避免跨断点连线
    let seg=[];
    const flush=()=>{ if(seg.length>1){ctx.beginPath();seg.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.stroke();} seg=[]; };
    t.mask.forEach((ok,i)=>{ if(ok) seg.push([X(hours[i]),Y(t.alt_app[i])]); else flush(); });
    flush();
    // 过中天标记
    if (t.transit_h>=tmin && t.transit_h<=tmax) {
      ctx.fillStyle=col;
      ctx.beginPath();
      ctx.moveTo(X(t.transit_h),Y(t.transit_alt)-7);
      ctx.lineTo(X(t.transit_h)-4,Y(t.transit_alt)-1);
      ctx.lineTo(X(t.transit_h)+4,Y(t.transit_alt)-1);
      ctx.closePath(); ctx.fill();
    }
  }
  // 时间游标
  const cur = currentTime();
  ctx.strokeStyle="rgba(255,255,255,.5)"; ctx.lineWidth=1;
  ctx.beginPath(); ctx.moveTo(X(cur),y0); ctx.lineTo(X(cur),y1); ctx.stroke();

  // 图例(前 8 个有窗口目标)
  const legend = DATA.targets.filter(t=>t.windows.length).slice(0,8);
  ctx.textAlign="left"; ctx.font="11px sans-serif";
  legend.forEach((t,i)=>{
    const lx=x0+8+(i%2)*Math.min(330,(x1-x0)/2), ly=y0+12+Math.floor(i/2)*13;
    ctx.fillStyle=colorOf(t.target.name); ctx.fillRect(lx,ly-7,10,3);
    ctx.fillStyle="#cdd9f5";
    ctx.fillText(shortName(t.target.name), lx+14, ly);
  });
}

function drawCurve(ctx, vals, hours, X, Y, color, lw, dashed) {
  ctx.strokeStyle=color; ctx.lineWidth=lw;
  if (dashed) ctx.setLineDash([3,3]); else ctx.setLineDash([]);
  ctx.beginPath();
  vals.forEach((v,i)=>{ const xx=X(hours[i]), yy=Y(v); i?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy); });
  ctx.stroke(); ctx.setLineDash([]);
}

function shortName(n){ return n.length>14 ? n.slice(0,14)+"…" : n; }

/* ------------------------------------------------------------ 时间游标 */

function setupTimeRange(){
  // 默认定位到子夜
  const mid = (DATA.sun.dusk_astro + DATA.sun.dawn_astro)/2;
  if (window._curTime==null) window._curTime = mid;
  window._tmin = DATA.chart.hours[0];
  window._tmax = DATA.chart.hours[DATA.chart.hours.length-1];
  onTimeMove();
}
function currentTime(){
  return Math.min(window._tmax, Math.max(window._tmin, window._curTime));
}
function onTimeMove(){
  if (!DATA) return;
  const frac = $("timeSlider").value/1000;
  window._curTime = window._tmin + frac*(window._tmax-window._tmin);
  $("timeLabel").textContent = `地方时 ${hhmm(window._curTime)}`;
  if (animTimer==null) { drawAltChart(); drawSkyChart(); }
}
function togglePlay(){
  if (animTimer){ clearInterval(animTimer); animTimer=null; $("playBtn").textContent="▶ 动画"; return; }
  $("playBtn").textContent="⏸ 暂停";
  animTimer=setInterval(()=>{
    const sl=$("timeSlider");
    sl.value = (parseInt(sl.value,10)+4) % 1001;
    onTimeMove();
  },120);
}
function nearestIndex(t){
  const h=DATA.chart.hours;
  let lo=0,hi=h.length-1;
  while(lo<hi){ const m=(lo+hi)>>1; if(h[m]<t) lo=m+1; else hi=m; }
  return Math.max(0,lo-1);
}

/* ------------------------------------------------------------ 星图(极投影) */

function drawSkyChart() {
  const cv=$("skyChart");
  const {ctx,w,h}=fitCanvas(cv);
  const cx=w/2, cy=h/2+6, R=Math.min(w,h)/2-46;
  ctx.clearRect(0,0,w,h);

  // 背景
  ctx.fillStyle="#070b18"; ctx.beginPath(); ctx.arc(cx,cy,R,0,7); ctx.fill();

  const project=(az,alt)=>{
    // 天顶距 r = R*(90-alt)/90; 方位 N(上)->E(左)->S(下)->W(右)
    const r=R*(90-Math.max(-2,alt))/90;
    const th=az*Math.PI/180;
    return [cx - r*Math.sin(th), cy - r*Math.cos(th)];
  };

  // 高度环
  ctx.strokeStyle="rgba(130,150,200,.22)"; ctx.fillStyle="#8fa0c8";
  ctx.font="10px sans-serif"; ctx.textAlign="center";
  for (const a of [0,30,60]){
    ctx.beginPath(); ctx.arc(cx,cy,R*(90-a)/90,0,7); ctx.stroke();
    ctx.fillText(a+"°", cx+4, cy-R*(90-a)/90+4);
  }
  // 方位十字 + NESW
  ctx.strokeStyle="rgba(130,150,200,.2)";
  for (const [dx,dy,lab,lx,ly] of [[0,-1,"N",0,-R-16],[1,0,"W",R+14,4],
                                   [0,1,"S",0,R+18],[-1,0,"E",-R-14,4]]){
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(cx+dx*R,cy+dy*R); ctx.stroke();
    ctx.fillStyle="#cdd9f5"; ctx.font="12px sans-serif";
    ctx.fillText(lab,cx+lx,cy+ly);
  }

  // 山头遮挡轮廓
  ctx.fillStyle="rgba(90,75,55,.55)";
  ctx.strokeStyle="rgba(160,140,100,.9)"; ctx.lineWidth=1.2;
  ctx.beginPath();
  DATA.horizon.forEach((p,i)=>{
    const [x,y]=project(p.az, Math.max(p.alt,0));
    i?ctx.lineTo(x,y):ctx.moveTo(x,y);
  });
  const [ex,ey]=project(DATA.horizon[0].az, Math.max(DATA.horizon[0].alt,0));
  ctx.lineTo(ex,ey);
  // 填到外圆: 沿外轮廓补一圈
  for (let az=360; az>=0; az-=15){
    const [x,y]=project(az,-2); ctx.lineTo(x,y);
  }
  ctx.closePath(); ctx.fill();

  // 月球
  const ti=nearestIndex(currentTime());
  const mAlt=DATA.moon.alt[ti], mAz=DATA.moon.az[ti];
  if (mAlt>-3){
    const [mx,my]=project(mAz,mAlt);
    ctx.fillStyle="#e8e2b0"; ctx.beginPath(); ctx.arc(mx,my,7,0,7); ctx.fill();
    ctx.fillStyle="#0b1020";
    ctx.beginPath(); ctx.arc(mx+3,my-2,6,0,7); ctx.fill();
    ctx.fillStyle="#e8e2b0"; ctx.font="11px sans-serif"; ctx.textAlign="left";
    ctx.fillText(`月 ${(DATA.moon.illumination*100).toFixed(0)}%`, mx+9,my+4);
  }

  // 目标点
  const schedTargets = new Set(
    DATA.plan.entries.filter(e=>e.kind==="exposure").map(e=>e.target));
  const legendItems=[];
  for (const t of DATA.targets){
    const alt=t.alt_app[ti], az=t.az[ti];
    if (alt < -3) continue;
    const [x,y]=project(az,alt);
    const col=colorOf(t.target.name);
    const ok=t.mask[ti];
    ctx.fillStyle=ok?col:"rgba(150,160,190,.55)";
    ctx.beginPath(); ctx.arc(x,y,ok?4.5:3,0,7); ctx.fill();
    if (ok){
      ctx.strokeStyle=col; ctx.lineWidth=1.4; ctx.beginPath(); ctx.arc(x,y,7,0,7); ctx.stroke();
    }
    ctx.font="10.5px sans-serif"; ctx.textAlign="left";
    ctx.fillStyle=ok?"#eef3ff":"rgba(170,180,210,.7)";
    const nm=shortName(t.target.name);
    ctx.fillText(nm, x+7, y+3);
    if (legendItems.length<10) legendItems.push([col,nm,ok]);
  }
  $("skyLegend").innerHTML = legendItems.map(([c,n,ok])=>
    `<span><i style="background:${c};opacity:${ok?1:.4}"></i>${escapeHtml(n)}</span>`).join("");
}

/* ------------------------------------------------------------ 计划表 */

function renderPlan() {
  const tb=$("planTable").querySelector("tbody");
  const order = DATA.plan.order;
  const byName=Object.fromEntries(DATA.targets.map(t=>[t.target.name,t]));
  let html="";
  // 按 plan entries 输出(时间序), 但行可拖拽 -> 拖拽重排的是“目标顺序”
  // 为支持拖拽, 先按目标聚合排序块, 每个目标内再列条目
  const grouped=new Map();
  for (const e of DATA.plan.entries){
    if (!grouped.has(e.target)) grouped.set(e.target,[]);
    grouped.get(e.target).push(e);
  }
  order.forEach((name,idx)=>{
    const entries=grouped.get(name);
    const t=byName[name]; if(!t) return;
    const color=colorOf(name);
    // 手柄跨满本块实际行数(每个 entry 一行), 不能多占, 否则会侵入下一目标块首行
    const nrows=Math.max(entries?entries.length:0,1);
    const blockOpen=`<tr class="griprow" draggable="true" data-name="${escapeHtml(name)}"
        style="border-top:2px solid ${color}55">
      <td rowspan="${nrows}" class="draghandle" title="拖动调整拍摄顺序">⠿</td>`;
    if (!entries){
      html+=blockOpen+`
        <td colspan="5" class="bad">✗ ${escapeHtml(name)} —— 不可安排</td>
        <td></td></tr>`;
      return;
    }
    let first=true;
    for (const e of entries){
      if (first){
        html+=blockOpen;
      } else {
        html+=`<tr data-name="${escapeHtml(name)}" draggable="false">`;
      }
      if (e.kind==="slew"){
        html+=`<td>${e.start_h}–${e.end_h}</td>
          <td style="color:var(--dim)">◇ ${escapeHtml(e.label)}</td>
          <td></td><td></td><td></td><td></td></tr>`;
      } else if (e.kind==="flip"){
        html+=`<td>${e.start_h}–${e.end_h}</td>
          <td><span class="tag flip">⟲ 过中天翻转</span></td>
          <td></td><td></td><td>${((e.end-e.start)*60).toFixed(0)} min</td><td></td></tr>`;
      } else {
        const sideTag=e.side==="east"?'<span class="tag east">中天前·东</span>'
          :'<span class="tag west">中天后·西</span>';
        html+=`<td>${e.start_h}–${e.end_h}</td>
          <td style="color:${color}">${first?("● "+escapeHtml(name)):"↳ 续拍"}</td>
          <td>${sideTag}</td>
          <td>${e.frames}</td><td>${e.exposure_s}s</td>
          <td>${((e.end-e.start)*60).toFixed(0)} min</td></tr>`;
      }
      first=false;
    }
  });
  tb.innerHTML=html;

  // 汇总
  const p=DATA.plan;
  $("planMeta").innerHTML=`
    <span>暗夜 <b>${p.night_hours.toFixed(2)} h</b></span>
    <span>曝光合计 <b>${p.exposure_hours.toFixed(2)} h</b></span>
    <span>时间利用率 <b>${(p.utilization*100).toFixed(0)}%</b></span>
    <span>已排目标 <b>${p.summary.filter(s=>s.scheduled).length}/${p.summary.length}</b></span>
    <span style="color:var(--dim)">顺序: 拖拽目标块调整, 或点击“恢复自动排序”</span>`;

  attachDragHandlers();
}

/* 拖拽重排: 以目标块为单位 */
function attachDragHandlers(){
  const tb=$("planTable").querySelector("tbody");
  let dragName=null;
  tb.querySelectorAll(".griprow").forEach(row=>{
    row.addEventListener("dragstart",(e)=>{
      dragName=row.dataset.name;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed="move";
    });
    row.addEventListener("dragend",()=>{
      row.classList.remove("dragging");
      tb.querySelectorAll(".dropabove,.dropbelow").forEach(el=>el.classList.remove("dropabove","dropbelow"));
    });
    row.addEventListener("dragover",(e)=>{
      e.preventDefault();
      if (!dragName || dragName===row.dataset.name) return;
      const rect=row.getBoundingClientRect();
      const before=(e.clientY-rect.top)<rect.height/2;
      row.style.borderTop = before ? "2px solid var(--accent)":"";
      row.style.borderBottom = before ? "" : "2px solid var(--accent)";
    });
    row.addEventListener("dragleave",()=>{
      row.style.borderTop=""; row.style.borderBottom="";
    });
    row.addEventListener("drop",(e)=>{
      e.preventDefault();
      row.style.borderTop=""; row.style.borderBottom="";
      if (!dragName || dragName===row.dataset.name) return;
      const rect=row.getBoundingClientRect();
      const before=(e.clientY-rect.top)<rect.height/2;
      const order=DATA.plan.order.filter(n=>n!==dragName);
      let targetIdx=order.indexOf(row.dataset.name);
      if (!before) targetIdx+=1;
      order.splice(targetIdx,0,dragName);
      reorder(order);
    });
  });
}

/* ------------------------------------------------------------ 目标统计/警告 */

function renderTargetStats(){
  for (const tr of $("targetTable").querySelectorAll("tbody tr")){
    const t=DATA.targets.find(x=>x.target.name===tr.dataset.name);
    const cell=tr.querySelector(".f-stat");
    if (!t){ cell.textContent="—"; cell.className="f-stat"; continue; }
    if (!t.windows.length){
      cell.innerHTML=`<span class="stat-no">整夜不可见</span>`;
    } else {
      const sched=DATA.plan.summary.find(s=>s.target===t.target.name);
      const ok=sched && sched.frames_done>=sched.frames_wanted;
      cell.innerHTML=ok
        ? `<span class="stat-ok">${t.total_observable_min.toFixed(0)}min 中天${sched.transit_hhmm}</span>`
        : `<span class="${sched&&sched.scheduled?"":"stat-no"}">${sched.frames_done}/${sched.frames_wanted}张 · 中天${sched.transit_hhmm} · ${t.total_observable_min.toFixed(0)}min</span>`;
    }
  }
}

function renderWarnings(){
  const box=$("warnings");
  const items=[...DATA.warnings.map(w=>({t:w,cls:"warn"})),
    ...DATA.plan.notes.map(n=>({t:`${n.target}: ${n.note}`,cls:"warn"})),
    ...DATA.plan.unscheduled.map(u=>({t:`${u.target}: ${u.reason}`,cls:"bad"}))];
  box.innerHTML=items.map(i=>`<div class="${i.cls}">${i.cls==="bad"?"✗ ":"⚠ "}${escapeHtml(i.t)}</div>`).join("");
}

window.addEventListener("resize",()=>{ if(DATA){drawAltChart();drawSkyChart();} });
window.__planner = { getData: () => DATA };  // 供测试访问
init();
