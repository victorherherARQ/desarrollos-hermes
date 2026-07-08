// ============================================================
//  render.js — SVG sequence renderer
//  Dibuja actores + lifelines + mensajes animados.
//  Expone renderFlow(container, flowSpec, currentIdx)
// ============================================================

const NS = 'http://www.w3.org/2000/svg';
const ACTOR_W   = 116;
const ACTOR_H   = 56;
const ACTOR_GAP = 44;
const TOP_PAD   = 30;
const LEFT_PAD  = 16;
const MESSAGE_GAP = 54;

const COLORS = {
  bg:    '#0a0a0b',
  actorBg:   '#111114',
  actorBgActive: '#1e1e26',
  actorBorder: '#2a2a33',
  lifeline: '#1f1f27',
  lifelineActive: '#3a3a45',
  msg:    '#c9c9d2',
  msgReply: '#6ee7b7',
  msgPending: '#5c5c66',
  label:  '#e7e7ea',
  labelDim: '#8b8b95',
};

/** Crea elemento SVG */
const svgEl = (tag, attrs = {}, children = []) => {
  const el = document.createElementNS(NS, tag);
  for (const k in attrs) {
    el.setAttribute(k, attrs[k]);
  }
  for (const c of children) el.appendChild(c);
  return el;
};

/** Texto con tspan si es multilínea */
const textEl = (text, x, y, opts = {}) => {
  const t = svgEl('text', {
    x, y,
    fill: opts.fill || COLORS.label,
    'font-size': opts.size || 12,
    'font-family': opts.family || 'Inter, sans-serif',
    'text-anchor': opts.anchor || 'start',
    'font-weight': opts.weight || 400,
    'letter-spacing': opts.tracking || '0',
  });
  const lines = String(text).split('\n');
  lines.forEach((line, i) => {
    const ts = svgEl('tspan', {
      x,
      dy: i === 0 ? '0' : '1.2em',
    });
    ts.textContent = line;
    t.appendChild(ts);
  });
  return t;
};

/** Layout: posición X de cada actor */
function actorXMap(actors, renderWidth, actorW = ACTOR_W, actorGap = ACTOR_GAP) {
  const total = actors.length * actorW + (actors.length - 1) * actorGap;
  const startX = LEFT_PAD + Math.max(0, (renderWidth - total) / 2);
  const map = {};
  actors.forEach((a, i) => {
    map[a.id] = startX + i * (actorW + actorGap) + actorW / 2;
  });
  return map;
}

/** Altura total del SVG según número de pasos */
function heightForSteps(n) {
  return TOP_PAD + ACTOR_H + 14 + Math.max(1, n) * MESSAGE_GAP + 60;
}

/** Render inicial del flow con todos los actores y lifelines, mensajes vacíos. */
export function renderFlow(svgEl_, flow, currentIdx = -1, containerWidthHint = 0) {
  // Limpiar
  while (svgEl_.firstChild) svgEl_.removeChild(svgEl_.firstChild);

  // Tomar el ancho del contenedor padre (svgHost) que sí está renderizado por CSS
  // (el SVG en sí no tiene width al inicio). Si falla, fallback a 1100.
  let containerWidth = containerWidthHint || svgEl_.clientWidth || 0;
  if (!containerWidth) {
    const parent = svgEl_.parentElement;
    containerWidth = parent ? (parent.clientWidth - 32) : 1100;
  }
  if (!containerWidth) containerWidth = 1100;
  const height = heightForSteps(flow.steps.length);

  // Ancho natural = N*ACTOR_W + (N-1)*ACTOR_GAP + 2*LEFT_PAD
  const nActors = flow.actors.length;
  let ACTOR_W_USE = ACTOR_W;
  let ACTOR_GAP_USE = ACTOR_GAP;
  let renderWidth = LEFT_PAD * 2 + nActors * ACTOR_W + (nActors - 1) * ACTOR_GAP;

  // Si no caben todos los actores en containerWidth (con margen de -8px),
  // reescalamos a un packing más compacto. RenderWidth final <= containerWidth.
  if (renderWidth - 8 > containerWidth && nActors > 4) {
    const usableWidth = containerWidth - LEFT_PAD * 2 - 8;
    const minActorW = 76;
    const minGap = 24;
    const x = (usableWidth - (nActors - 1) * minGap) / nActors;
    if (x >= minActorW) {
      ACTOR_W_USE = x;
      ACTOR_GAP_USE = minGap;
      renderWidth = usableWidth + 8;
    } else {
      // Aun con minActorW no cabe: limitamos al container y permitimos scroll.
      renderWidth = containerWidth;
      ACTOR_W_USE = Math.min(ACTOR_W, (containerWidth - LEFT_PAD * 2 - (nActors - 1) * ACTOR_GAP) / nActors);
    }
  }

  const xMap = actorXMap(flow.actors, renderWidth, ACTOR_W_USE, ACTOR_GAP_USE);

  // Si el renderWidth es > containerWidth + 8, activamos scroll horizontal.
  // De lo contrario, el SVG escala a 100% del container sin scroll.
  svgEl_.setAttribute('viewBox', `0 0 ${renderWidth} ${height}`);
  svgEl_.setAttribute('preserveAspectRatio', 'xMinYMin meet');
  if (renderWidth > containerWidth + 8) {
    svgEl_.setAttribute('width', renderWidth);
  } else {
    svgEl_.removeAttribute('width');
  }
  svgEl_.setAttribute('height', height);

  // --- Líneas de fondo (lifelines) ---
  const lifelinesGroup = svgEl('g', { class: 'lifelines' });
  flow.actors.forEach((a) => {
    const x = xMap[a.id];
    const line = svgEl('line', {
      x1: x, x2: x,
      y1: TOP_PAD + ACTOR_H + 4,
      y2: height - 20,
      stroke: COLORS.lifeline,
      'stroke-width': 1,
      'stroke-dasharray': '4 5',
    });
    line.setAttribute('data-actor', a.id);
    lifelinesGroup.appendChild(line);
  });
  svgEl_.appendChild(lifelinesGroup);

  // --- Cajas de actor ---
  const actorsGroup = svgEl('g', { class: 'actors' });
  flow.actors.forEach((a) => {
    const x = xMap[a.id] - ACTOR_W / 2;
    const y = TOP_PAD;
    const g = svgEl('g', {
      class: 'actor',
      'data-actor': a.id,
      style: `cursor:pointer`,
    });
    // Fondo
    g.appendChild(svgEl('rect', {
      x, y,
      width: ACTOR_W_USE, height: ACTOR_H,
      rx: 8, ry: 8,
      fill: COLORS.actorBg,
      stroke: a.color,
      'stroke-width': 1.2,
      opacity: 0.95,
    }));
    // Color dot
    g.appendChild(svgEl('circle', {
      cx: x + 14, cy: y + 14, r: 4,
      fill: a.color,
    }));
    // Nombre (centrado en el ancho del actor)
    const nameX = x + ACTOR_W_USE / 2;
    g.appendChild(textEl(a.name, nameX, y + 18, {
      size: Math.min(12, ACTOR_W_USE / 9), weight: 600,
      anchor: 'middle',
    }));
    // Rol
    g.appendChild(textEl(a.role, nameX, y + 36, {
      size: 10.5,
      fill: COLORS.labelDim,
      anchor: 'middle',
    }));
    g.appendChild(textEl(a.id.toUpperCase(), nameX, y + 50, {
      size: 9.5, weight: 700,
      fill: a.color,
      family: 'JetBrains Mono, monospace',
      tracking: '0.1em',
      anchor: 'middle',
    }));
    actorsGroup.appendChild(g);
  });
  svgEl_.appendChild(actorsGroup);

  // --- Mensajes ---
  const messagesGroup = svgEl('g', { class: 'messages' });
  flow.steps.forEach((s, i) => {
    const g = svgEl('g', { class: 'message', 'data-step': i });
    const y = TOP_PAD + ACTOR_H + MESSAGE_GAP * (i + 0.5) + 14;
    const fromX = xMap[s.from];
    const toX   = xMap[s.to];
    messagesGroup.appendChild(svgEl('rect', {
      class: 'msg-bg',
      x: 0, y: y - 14,
      width: renderWidth, height: MESSAGE_GAP - 8,
      fill: 'transparent',
      'data-row': i,
    }));

    if (s.kind === 'self') {
      // Self-loop sobre el actor 'from'
      const w = 40, h = 22;
      g.appendChild(svgEl('path', {
        d: `M ${fromX} ${y - 14}
            q ${w} 0 ${w} ${h}
            l 0 ${h * 0.6}
            M ${fromX + w * 0.15} ${y - 14 + h * 1.6}
            l ${w * 0.15} ${-h * 0.5}
            l ${-w * 0.3} 0 z`,
        fill: 'none',
        stroke: COLORS.msg,
        'stroke-width': 1.6,
        'marker-end': 'none',
      }));
      g.appendChild(textEl(s.label, fromX + w + 10, y + h, {
        size: 11,
        fill: COLORS.msg,
      }));
    } else {
      // Flecha entre from y to
      const isReply = s.kind === 'reply';
      const colour  = isReply ? COLORS.msgReply : COLORS.msg;
      const dash    = isReply ? '4 4' : 'none';
      const arrowId = `arrow-${i}`;
      g.appendChild(svgEl('defs', {}, [
        svgEl('marker', {
          id: arrowId,
          viewBox: '0 0 10 10',
          refX: '9', refY: '5',
          markerWidth: '7', markerHeight: '7',
          orient: 'auto-start-reverse',
        }, [
          svgEl('path', { d: 'M0,0 L10,5 L0,10 z', fill: colour }),
        ]),
      ]));

      // Línea
      const line = svgEl('line', {
        x1: fromX, x2: toX, y1: y, y2: y,
        stroke: colour,
        'stroke-width': 1.5,
        'stroke-dasharray': dash,
        'marker-end': `url(#${arrowId})`,
        'data-line': i,
      });
      g.appendChild(line);

      // Etiqueta encima de la flecha (con halo)
      const labelX = (fromX + toX) / 2;
      const labelText = s.label;
      const dim = labelText.length > 70;
      const t = textEl(labelText, labelX, y - 8, {
        size: dim ? 10.5 : 11.5,
        fill: COLORS.label,
        anchor: 'middle',
        weight: isReply ? 500 : 500,
      });
      g.appendChild(t);
    }

    messagesGroup.appendChild(g);
  });
  svgEl_.appendChild(messagesGroup);

  // --- Aplicar estado actual ---
  applyState(svgEl_, flow, currentIdx, xMap, renderWidth);
}

/** Actualiza el SVG para resaltar el paso currentIdx */
export function applyState(svgEl_, flow, currentIdx, xMapOpt = null) {
  // Recuperamos el ancho del viewBox (que es renderWidth).
  const viewBox = svgEl_.getAttribute('viewBox') || `0 0 ${svgEl_.clientWidth || 1100} 800`;
  const renderWidth = parseFloat(viewBox.split(' ')[2]) || (svgEl_.clientWidth || 1100);
  const xMap = xMapOpt || actorXMap(flow.actors, renderWidth);

  // Activar/desactivar actores
  const involved = new Set();
  flow.steps.slice(0, currentIdx + 1).forEach((s) => {
    involved.add(s.from);
    if (s.to !== s.from) involved.add(s.to);
  });
  // Para el "current step", también se iluminan los del mensaje que se va a representar (currentIdx + 0 → siguiente paso a animar)
  const upcoming = flow.steps[currentIdx + 1];
  const activePair = new Set();
  if (upcoming) {
    involved.delete(upcoming.from);
    if (upcoming.to !== upcoming.from) involved.delete(upcoming.to);
    activePair.add(upcoming.from);
    if (upcoming.to !== upcoming.from) activePair.add(upcoming.to);
  }

  svgEl_.querySelectorAll('[data-actor]').forEach((g) => {
    const id = g.getAttribute('data-actor');
    const isInvolved = involved.has(id);
    const isActive   = activePair.has(id);
    const tagName = g.tagName.toLowerCase();
    // Tanto las cajas de actor (g .actor) como las lifelines (line) tienen data-actor.
    const stroke = (isActive || isInvolved) ? COLORS.lifelineActive : COLORS.lifeline;
    const strokeWidth = isActive ? 1.5 : 1;
    if (tagName === 'line') {
      g.setAttribute('stroke', stroke);
      g.setAttribute('stroke-width', strokeWidth);
      return;
    }
    const rect = g.querySelector('rect');
    if (rect) {
      rect.setAttribute('fill', isActive ? COLORS.actorBgActive : COLORS.actorBg);
      rect.setAttribute('stroke-width', isActive ? 2 : 1.2);
      rect.setAttribute('opacity', isInvolved || isActive ? '1' : '0.55');
    }
  });

  // Resaltar mensaje correspondiente al currentIdx
  const messageNodes = svgEl_.querySelectorAll('.message');
  messageNodes.forEach((node) => {
    const idx = parseInt(node.getAttribute('data-step'), 10);
    const visible = idx <= currentIdx;
    const active = idx === currentIdx || idx === currentIdx + 1;
    node.style.opacity = visible || active ? 1 : 0.15;
    const line = node.querySelector('line');
    if (line) {
      const s = flow.steps[idx];
      const isReply = s.kind === 'reply';
      const targetStroke = (idx === currentIdx) ? (isReply ? '#6ee7b7' : '#7e83ff') :
                           (visible ? (isReply ? COLORS.msgReply : COLORS.msg) : COLORS.msgPending);
      line.setAttribute('stroke', targetStroke);
      line.setAttribute('stroke-width', active ? 2.2 : 1.5);
    }
    // Self-loop is path
    const path = node.querySelector('path[fill=none]');
    if (path && active) path.setAttribute('stroke-width', 2.2);
  });
}

/** Resaltar actor en panel lateral */
export function highlightSideActor(flow, actorId) {
  // (Lógica se delega a app.js para mantener separación)
  document.dispatchEvent(new CustomEvent('actor-focus', { detail: { actorId } }));
}

/** Devuelve ids orden de actores del flow */
export function getFlowActorIds(flow) {
  return flow.actors.map((a) => a.id);
}
