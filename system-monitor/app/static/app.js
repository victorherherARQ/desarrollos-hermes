// System Monitor UI
const $ = (id) => document.getElementById(id);
let currentPeriod = 24;
let bigChart;

// ============================================================
// Sparkline helper
// ============================================================
function drawSpark(canvas, data, color = "#58a6ff") {
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!data || data.length < 2) return;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

// ============================================================
// Cards
// ============================================================
function setCard(id, value, sub, sparkId, data, color) {
  $(id).textContent = value;
  $(id + "-sub").textContent = sub || "";
  if (sparkId && data) drawSpark($(sparkId), data, color);
}

async function loadCurrent() {
  try {
    const r = await fetch("/api/current");
    if (!r.ok) return;
    const d = await r.json();
    setCard("m-cpu", d.cpu_percent.toFixed(1) + "%", `${d.cpu_count} cores @ ${d.cpu_freq_mhz.toFixed(0)} MHz`,
            "sp-cpu", null, "#58a6ff");
    setCard("m-ram", d.ram_percent.toFixed(1) + "%", `${d.ram_used_gb} / ${d.ram_total_gb} GB`,
            "sp-ram", null, "#a371f7");
    setCard("m-disk", d.disk_percent.toFixed(1) + "%", `${d.disk_used_gb} / ${d.disk_total_gb} GB`,
            "sp-disk", null, "#f0883e");
    setCard("m-load", d.load1.toFixed(2), `5m: ${d.load5.toFixed(2)}  15m: ${d.load15.toFixed(2)}`,
            "sp-load", null, "#f778ba");
    const temp = d.temp_cpu_c;
    setCard("m-temp", temp == null ? "N/D" : temp.toFixed(1) + " °C",
            temp == null ? "no expuesta en WSL2" : "del sensor CPU",
            "sp-temp", null, "#ff7b72");
    setCard("m-net", `↓ ${(d.net_rx_mb/1024).toFixed(2)} GB`,
            `↑ ${(d.net_tx_mb/1024).toFixed(2)} GB acumulado`,
            "sp-net", null, "#3fb950");

    // Tables
    const procTbody = document.querySelector("#procs tbody");
    procTbody.innerHTML = "";
    (d.top_processes || []).forEach(p => {
      procTbody.innerHTML += `<tr><td>${p.pid}</td><td>${p.name}</td><td>${p.user || "-"}</td><td>${p.cpu_pct.toFixed(1)}</td><td>${p.ram_mb}</td></tr>`;
    });
    const contTbody = document.querySelector("#conts tbody");
    contTbody.innerHTML = "";
    if ((d.containers || []).length === 0) {
      contTbody.innerHTML = `<tr><td colspan="3" style="text-align:center;color:#8b949e">No accesibles</td></tr>`;
    } else {
      d.containers.forEach(c => {
        contTbody.innerHTML += `<tr><td>${c.name}</td><td>${c.cpu_pct}</td><td>${c.ram_mb}</td></tr>`;
      });
    }
  } catch (e) { console.error(e); }
}

// ============================================================
// History big chart
// ============================================================
async function loadHistory() {
  try {
    const r = await fetch(`/api/history?hours=${currentPeriod}`);
    if (!r.ok) return;
    const data = await r.json();
    if (!data.length) return;

    const labels = data.map(s => new Date(s.ts * 1000).toLocaleString());
    const cpu = data.map(s => s.cpu_percent);
    const ram = data.map(s => s.ram_percent);
    const disk = data.map(s => s.disk_percent);
    const temp = data.map(s => s.temp_cpu_c);

    // Update sparklines with real data
    drawSpark($("sp-cpu"), cpu, "#58a6ff");
    drawSpark($("sp-ram"), ram, "#a371f7");
    drawSpark($("sp-disk"), disk, "#f0883e");
    drawSpark($("sp-load"), data.map(s => s.load1), "#f778ba");
    drawSpark($("sp-temp"), temp.filter(v => v != null), "#ff7b72");
    drawSpark($("sp-net"), data.map(s => s.net_rx_mb), "#3fb950");

    drawBigChart(labels, cpu, ram, disk, temp);
    $("period-label").textContent = `${currentPeriod}h`;
    $("report-period").textContent = `${currentPeriod}h`;
  } catch (e) { console.error(e); }
}

function drawBigChart(labels, cpu, ram, disk, temp) {
  const c = $("bigChart");
  const ctx = c.getContext("2d");
  const W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);
  if (labels.length < 2) return;

  const padding = { l: 50, r: 20, t: 20, b: 40 };
  const w = W - padding.l - padding.r;
  const h = H - padding.t - padding.b;

  // grid + Y axis (0-100 for %)
  ctx.strokeStyle = "#30363d";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#8b949e";
  ctx.font = "11px sans-serif";
  for (let v = 0; v <= 100; v += 20) {
    const y = padding.t + h - (v / 100) * h;
    ctx.beginPath();
    ctx.moveTo(padding.l, y);
    ctx.lineTo(W - padding.r, y);
    ctx.stroke();
    ctx.fillText(v + "%", 5, y + 4);
  }
  // X labels (4 ticks)
  const xTicks = 4;
  for (let i = 0; i <= xTicks; i++) {
    const idx = Math.floor((labels.length - 1) * i / xTicks);
    const x = padding.l + (idx / (labels.length - 1)) * w;
    const lbl = labels[idx].split(",")[1]?.trim() || labels[idx];
    ctx.fillText(lbl.slice(0, 10), x - 30, H - 10);
  }

  function line(vals, color, scale = 100) {
    if (vals.every(v => v == null)) return;
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    vals.forEach((v, i) => {
      if (v == null) return;
      const x = padding.l + (i / (vals.length - 1)) * w;
      const y = padding.t + h - (Math.min(v, scale) / scale) * h;
      if (i === 0 || vals[i - 1] == null) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  line(cpu, "#58a6ff");
  line(ram, "#a371f7");
  line(disk, "#f0883e");
  line(temp, "#ff7b72");

  // Legend
  const legend = [
    ["CPU %", "#58a6ff"], ["RAM %", "#a371f7"],
    ["Disco %", "#f0883e"], ["Temp °C", "#ff7b72"]
  ];
  legend.forEach(([lbl, col], i) => {
    ctx.fillStyle = col;
    ctx.fillRect(padding.l + i * 100, 5, 12, 4);
    ctx.fillStyle = "#c9d1d9";
    ctx.fillText(lbl, padding.l + i * 100 + 16, 9);
  });
}

// ============================================================
// Report
// ============================================================
async function loadReport() {
  try {
    const r = await fetch(`/api/report?hours=${currentPeriod}`);
    if (!r.ok) return;
    const d = await r.json();
    if (d.error) { $("report-text").textContent = d.error; return; }
    const lines = [];
    const fmt = (s) => s ? `${s.min} / ${s.avg} / ${s.max}` : "N/D";
    const tag = (val, lo, hi) => val > hi ? "⚠️" : val < lo ? "❄️" : "✅";
    lines.push(`Período:        ${d.period_hours} horas  (${d.sample_count} muestras)`);
    lines.push(`CPU %:          ${fmt(d.cpu_percent)}  min / avg / max`);
    lines.push(`RAM %:          ${fmt(d.ram_percent)}`);
    lines.push(`Disco %:        ${fmt(d.disk_percent)}`);
    lines.push(`Load (1m):      ${fmt(d.load1)}`);
    lines.push(`CPU Temp °C:    ${fmt(d.temp_cpu_c) || "no expuesta (WSL2)"}`);
    lines.push(`Red RX delta:   ${d.net_rx_mb_delta} MB`);
    lines.push(`Red TX delta:   ${d.net_tx_mb_delta} MB`);
    lines.push("");
    lines.push(`Generado:       ${new Date().toISOString()}`);
    $("report-text").textContent = lines.join("\n");
  } catch (e) { console.error(e); }
}

// ============================================================
// Init + auto-refresh
// ============================================================
async function refresh() {
  await Promise.all([loadCurrent(), loadHistory(), loadReport()]);
}

$("period").addEventListener("change", (e) => {
  currentPeriod = parseInt(e.target.value, 10);
  refresh();
});
$("refresh").addEventListener("click", refresh);

refresh();
setInterval(refresh, 30000);
