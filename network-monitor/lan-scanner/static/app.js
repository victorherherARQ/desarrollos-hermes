// Network Monitor UI
const API = "";  // mismo host

// ============================================================
// Tabs
// ============================================================
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('tab-' + t.dataset.tab).classList.add('active');
  });
});

// ============================================================
// Helpers
// ============================================================
async function fetchJSON(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
  return d.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'medium' });
}

function shortTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
  return d.toLocaleString('es-ES', { timeStyle: 'short' });
}

function bpsToMbps(bps) { return (bps / 1e6).toFixed(1); }

// ============================================================
// Devices table
// ============================================================
let allDevices = [];
let chartSpeedtest = null;

async function loadDevices() {
  allDevices = await fetchJSON('/api/devices');
  renderDevices();
  // Stats
  const online = allDevices.filter(d => d.is_online).length;
  document.getElementById('stats-total').textContent = allDevices.length;
  document.getElementById('stats-online').textContent = online;
  document.getElementById('last-refresh').textContent = new Date().toLocaleTimeString('es-ES');
}

function renderDevices() {
  const filterText = document.getElementById('filter-text').value.toLowerCase();
  const onlyOnline = document.getElementById('filter-online').checked;
  const tbody = document.querySelector('#devices-table tbody');
  tbody.innerHTML = '';
  const filtered = allDevices
    .filter(d => !onlyOnline || d.is_online)
    .filter(d => !filterText ||
      (d.ip || '').includes(filterText) ||
      (d.mac || '').toLowerCase().includes(filterText) ||
      (d.vendor || '').toLowerCase().includes(filterText) ||
      (d.hostname || '').toLowerCase().includes(filterText)
    );
  for (const d of filtered) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="dot ${d.is_online ? 'online' : 'offline'}"></span>${d.is_online ? 'online' : 'offline'}</td>
      <td>${d.ip || '—'}</td>
      <td class="mac">${d.mac}</td>
      <td>${d.vendor || '—'}</td>
      <td>${d.hostname || '—'}</td>
      <td>${shortTime(d.last_seen)}</td>
      <td>${formatTime(d.first_seen)}</td>
      <td>${d.times_seen}</td>
    `;
    tbody.appendChild(tr);
  }
}

document.getElementById('filter-online').addEventListener('change', renderDevices);
document.getElementById('filter-text').addEventListener('input', renderDevices);

// ============================================================
// New devices
// ============================================================
async function loadNewDevices() {
  const list = await fetchJSON('/api/devices/new?hours=24');
  const tbody = document.querySelector('#new-table tbody');
  tbody.innerHTML = '';
  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#6c757d;">No hay dispositivos nuevos en las últimas 24h</td></tr>';
    return;
  }
  for (const d of list) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${d.ip || '—'}</td>
      <td class="mac">${d.mac}</td>
      <td>${d.vendor || '—'}</td>
      <td>${d.hostname || '—'}</td>
      <td>${formatTime(d.first_seen)}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ============================================================
// Speedtest
// ============================================================
async function loadSpeedtest() {
  const list = await fetchJSON('/api/speedtest?days=7');
  if (list.length > 0) {
    const last = list[list.length - 1];
    document.getElementById('sp-dl').textContent = bpsToMbps(last.download_bps);
    document.getElementById('sp-up').textContent = bpsToMbps(last.upload_bps);
    document.getElementById('sp-ping').textContent = last.ping_ms.toFixed(0);
  } else {
    document.getElementById('sp-dl').textContent = '—';
    document.getElementById('sp-up').textContent = '—';
    document.getElementById('sp-ping').textContent = '—';
  }
  renderSpeedtestChart(list);
}

function renderSpeedtestChart(list) {
  const labels = list.map(r => shortTime(r.timestamp));
  const dl = list.map(r => r.download_bps / 1e6);
  const ul = list.map(r => r.upload_bps / 1e6);

  if (chartSpeedtest) chartSpeedtest.destroy();
  const ctx = document.getElementById('chart-speedtest').getContext('2d');
  chartSpeedtest = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: '↓ Descarga (Mbps)', data: dl, borderColor: '#2ecc71', backgroundColor: 'rgba(46,204,113,0.1)', tension: 0.3, fill: true },
        { label: '↑ Subida (Mbps)', data: ul, borderColor: '#3498db', backgroundColor: 'rgba(52,152,219,0.1)', tension: 0.3, fill: true },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top' } },
      scales: { y: { beginAtZero: true, title: { display: true, text: 'Mbps' } } },
    },
  });
}

// ============================================================
// Refresh loop
// ============================================================
async function refreshAll() {
  try { await loadDevices(); } catch (e) { console.error(e); }
  try { await loadNewDevices(); } catch (e) { console.error(e); }
  try { await loadSpeedtest(); } catch (e) { console.error(e); }
}

refreshAll();
setInterval(refreshAll, 30_000);  // cada 30s
