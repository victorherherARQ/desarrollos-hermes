// ============================================================
//  app.js — orquestador: estado, tabs, controles, panel lateral
// ============================================================
import { FLOWS } from './flows.js';
import { renderFlow, applyState, getFlowActorIds } from './render.js';

// ---------- Estado ----------
const state = {
  flowId: 'A',
  step: -1,                  // -1 = ningún paso mostrado
  playing: false,
  timer: null,
  speed: 1,
};

// ---------- Helpers DOM ----------
const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));

function setSpeed(val) {
  state.speed = val;
  $('#speedVal').textContent = `${val.toFixed(2)}\u00d7`;
  // Si estamos reproduciendo, recalculamos el delay del próximo tick.
  if (state.playing && state.timer) {
    clearTimeout(state.timer);
    state.timer = setTimeout(tick, msForStep());
  }
}
function msForStep() {
  return Math.max(200, 1700 / state.speed);
}

// ---------- Cambio de flujo ----------
function setFlow(id) {
  state.flowId = id;
  state.step = -1;
  state.playing = false;
  if (state.timer) { clearTimeout(state.timer); state.timer = null; }
  $('#btnPlay').lastElementChild.textContent = 'Play';

  // UI tabs
  $$('.tab').forEach((b) => {
    const on = b.dataset.flow === id;
    b.setAttribute('aria-selected', String(on));
  });

  const flow = FLOWS[id];
  $('#flowTitle').textContent = flow.title;
  $('#flowMeta').textContent = flow.meta;

  // Pasamos el ancho del svgHost como hint al renderer, porque en el primer
  // render del DOMContentLoaded el SVG todavía no tiene clientWidth propio.
  const svgHost = $('#svgHost');
  const hint = svgHost.clientWidth || svgHost.offsetWidth || 0;
  renderFlow($('#sequence'), flow, -1, hint);
  renderLegend(flow);
  renderSideActors(flow);
  renderStep(flow, -1);

  $('#barFill').style.width = '0%';
}

// ---------- Legend ----------
function renderLegend(flow) {
  $('#legend').innerHTML = flow.actors.map((a) => `
    <span class="legend-item">
      <span class="legend-dot" style="background:${a.color}"></span>
      <span>${a.name}</span>
    </span>
  `).join('') + `
    <span class="legend-item">
      <span class="legend-dot" style="background:#6ee7b7"></span>
      <span style="color:var(--text-mute)">respuesta</span>
    </span>
    <span class="legend-item">
      <span class="legend-dot" style="background:#c9c9d2"></span>
      <span style="color:var(--text-mute)">petici\u00f3n</span>
    </span>
    <span class="legend-item">
      <span class="legend-dot" style="background:#7e83ff"></span>
      <span style="color:var(--text-mute)">paso activo</span>
    </span>
  `;
}

// ---------- Side panel ----------
function renderSideActors(flow) {
  $('#actorsList').innerHTML = flow.actors.map((a) => `
    <li class="actor-row" data-actor="${a.id}">
      <span class="actor-swatch" style="background:${a.color}"></span>
      <span class="actor-name">${a.name}</span>
      <span class="actor-role">${a.role}</span>
    </li>
  `).join('');
  $('#actorsList').querySelectorAll('.actor-row').forEach((row) => {
    row.addEventListener('click', () => focusActor(row.dataset.actor));
  });
}

function focusActor(actorId) {
  $$('#actorsList .actor-row').forEach((row) => {
    row.classList.toggle('active', row.dataset.actor === actorId);
  });
}

document.addEventListener('actor-focus', (e) => {
  focusActor(e.detail.actorId);
});

function renderStep(flow, idx) {
  // idx = -1 (sin pasos mostrados), 0..n (último paso mostrado)
  const total = flow.steps.length;

  // Step idx = currentIdx = "el ÚLTIMO paso mostrado"
  // El "paso actual" de la animación conceptualmente es idx+1 (próximo a animar).
  // Para mostrar card con "paso en pantalla" usamos idx+1 cuando reproduciendo activo,
  // pero preferimos mostrar el paso con idx = currentIdx+1 = "siguiente a animar".
  const upcoming = flow.steps[idx + 1];
  const card = upcoming || flow.steps[total - 1];
  const displayStep = idx + 2;  // humana: 1-based

  $('#stepIdx').textContent = upcoming ? displayStep : total;
  $('#stepTotal').textContent = total;
  if (!card) {
    $('#stepTitle').textContent = '\u2014';
    $('#stepDesc').innerHTML = 'Pulsa <strong>Play</strong> para iniciar la animaci\u00f3n.';
    $('#stepTags').innerHTML = '';
    $('#codeBlock').textContent = '// Selecciona un flujo y pulsa Play.';
    $('#jwtCard').hidden = true;
    return;
  }

  $('#stepTitle').textContent = card.label;
  $('#stepDesc').textContent = card.desc;

  // Tags
  const tags = [`${card.from}\u2192${card.to}`];
  tags.push(card.kind === 'sync' ? 'sync' : (card.kind === 'reply' ? 'respuesta' : 'self'));
  if (card.claims) tags.push('JWT con claims');
  if (card.code) tags.push(...Object.keys(card.code).map((k) => `code:${k}`));
  $('#stepTags').innerHTML = tags.map((t) => `<span class="tag">${t}</span>`).join('');

  // Código: mostramos por defecto bash si está, si no el primer lenguaje disponible
  const codeLangs = card.code ? Object.keys(card.code) : [];
  if (codeLangs.length === 0) {
    $('#codeBlock').textContent = '// Sin c\u00f3digo para este paso.';
    $$('#codeTabs').forEach((c) => c.innerHTML = '');
  } else {
    showCodeBlock(card, codeLangs[0]);
  }

  // JWT
  if (card.claims) {
    $('#jwtCard').hidden = false;
    $('#jwtBlock').textContent = JSON.stringify(card.claims, null, 2);
  } else {
    $('#jwtCard').hidden = true;
  }

  // Actor highlight
  const focused = new Set([card.from]);
  if (card.to !== card.from) focused.add(card.to);
  $$('#actorsList .actor-row').forEach((row) => {
    row.classList.toggle('active', focused.has(row.dataset.actor));
  });
}

function showCodeBlock(card, lang) {
  const container = $('#codeTabs');
  // Si los tabs ya renderizados no se corresponden con los lenguajes de este step,
  // los regeneramos. Mantenemos el step actual en closure con dataset del container.
  const langs = Object.keys(card.code);
  const same = container._langs && container._langs.length === langs.length
    && container._langs.every((l, i) => l === langs[i]);
  if (!same) {
    container._langs = langs;
    container._currentCard = card;
    container.innerHTML = '';
    langs.forEach((l) => {
      const b = document.createElement('button');
      b.className = 'code-tab';
      b.dataset.lang = l;
      b.textContent = l;
      b.addEventListener('click', () => showCodeBlock(container._currentCard, l));
      container.appendChild(b);
    });
  } else {
    container._currentCard = card;  // refresca por si cambió el step
  }
  $$('#codeTabs .code-tab').forEach((t) =>
    t.setAttribute('aria-selected', String(t.dataset.lang === lang))
  );
  $('#codeBlock').textContent = card.code[lang];
}

// ---------- Playback ----------
function tick() {
  const flow = FLOWS[state.flowId];
  if (state.step < flow.steps.length - 1) {
    state.step++;
    renderStep(flow, state.step);
    applyState($('#sequence'), flow, state.step);

    $('#barFill').style.width = `${((state.step + 1) / flow.steps.length) * 100}%`;

    if (state.playing) {
      state.timer = setTimeout(tick, msForStep());
    }
  } else {
    stop();
  }
}
function play() {
  const flow = FLOWS[state.flowId];
  if (state.step >= flow.steps.length - 1) {
    // Restart
    state.step = -1;
  }
  state.playing = true;
  $('#btnPlay').lastElementChild.textContent = 'Pause';
  tick();
}
function stop() {
  state.playing = false;
  if (state.timer) { clearTimeout(state.timer); state.timer = null; }
  $('#btnPlay').lastElementChild.textContent = 'Play';
}
function stepOnce() {
  const flow = FLOWS[state.flowId];
  if (state.step >= flow.steps.length - 1) return;
  stop();
  tick();
}
function reset() {
  stop();
  const flow = FLOWS[state.flowId];
  state.step = -1;
  renderStep(flow, -1);
  applyState($('#sequence'), flow, -1);
  $('#barFill').style.width = '0%';
}

// ---------- Init ----------
function init() {
  // Tabs
  $$('.tab').forEach((b) =>
    b.addEventListener('click', () => {
      $$('.tab').forEach((x) => x.setAttribute('aria-selected', 'false'));
      b.setAttribute('aria-selected', 'true');
      setFlow(b.dataset.flow);
    })
  );

  // Controles
  $('#btnPlay').addEventListener('click', () => {
    if (state.playing) stop();
    else play();
  });
  $('#btnStep').addEventListener('click', stepOnce);
  $('#btnReset').addEventListener('click', reset);
  $('#speed').addEventListener('input', (e) => setSpeed(parseFloat(e.target.value)));

  // Resize
  const ro = new ResizeObserver(() => {
    setFlow(state.flowId);
  });
  ro.observe($('#svgHost'));

  setSpeed(1);
  setFlow(state.flowId); // por defecto A
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
