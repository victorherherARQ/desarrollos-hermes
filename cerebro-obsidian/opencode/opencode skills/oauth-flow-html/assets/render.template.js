// render.template.js — oauth-flow-html skill
// Renders an OAuth/OIDC flow as an animated SVG sequence diagram.
// Reads window.__FLOWS__ = { title, actors:[{id,label,type}], steps:[{n,from,to,label,detail,duration_ms}] }

(function () {
  "use strict";

  const data = window.__FLOWS__;
  if (!data || !Array.isArray(data.steps) || !Array.isArray(data.actors)) {
    console.error("[oauth-flow-html] __FLOWS__ invalid:", data);
    return;
  }

  const actorsEl = document.getElementById("actors");
  const canvas = document.getElementById("canvas");
  const stepTitle = document.getElementById("step-title");
  const stepLabel = document.getElementById("step-label");
  const stepDetail = document.getElementById("step-detail");
  const stepCounter = document.getElementById("step-counter");

  // ---------- layout constants ----------
  const ACTOR_W = 160;
  const ROW_H = 80;
  const PADDING = 40;
  const NS = "http://www.w3.org/2000/svg";

  // Build actor positions
  const actorIndex = Object.fromEntries(data.actors.map((a, i) => [a.id, i]));
  const totalW = data.actors.length * ACTOR_W;
  const totalH = data.steps.length * ROW_H + PADDING * 2;
  canvas.setAttribute("viewBox", `0 0 ${totalW} ${totalH}`);
  canvas.setAttribute("width", totalW);
  canvas.setAttribute("height", totalH);

  // ---------- render actor pills on top ----------
  actorsEl.style.gridTemplateColumns = `repeat(${data.actors.length}, 1fr)`;
  actorsEl.innerHTML = "";
  data.actors.forEach((a) => {
    const div = document.createElement("div");
    div.className = `actor ${a.type || "internal"}`;
    div.dataset.actorId = a.id;
    div.innerHTML = `<div class="pill">${escapeHtml(a.label)}</div><div class="type">${escapeHtml(a.type || "")}</div>`;
    actorsEl.appendChild(div);
  });

  // ---------- lifelines (vertical dashed lines under each actor) ----------
  data.actors.forEach((a, i) => {
    const x = i * ACTOR_W + ACTOR_W / 2;
    const line = svg("line", {
      x1: x, y1: 0, x2: x, y2: totalH,
      stroke: "var(--line)", "stroke-width": 1, "stroke-dasharray": "4 4",
    });
    canvas.appendChild(line);
  });

  // ---------- step arrows + labels ----------
  const stepNodes = data.steps.map((step, idx) => {
    const fromIdx = actorIndex[step.from];
    const toIdx = actorIndex[step.to];
    if (fromIdx === undefined || toIdx === undefined) {
      console.warn("[oauth-flow-html] step", step.n, "references unknown actor");
      return null;
    }
    const y = idx * ROW_H + PADDING;
    const x1 = fromIdx * ACTOR_W + ACTOR_W / 2;
    const x2 = toIdx * ACTOR_W + ACTOR_W / 2;
    const dir = x1 < x2 ? 1 : -1;
    const isSelf = step.from === step.to;

    const group = svg("g", { class: "step-group", "data-step": String(idx) });
    group.style.cursor = "pointer";

    let line, arrow;
    if (isSelf) {
      // self-loop on right side of lifeline
      line = svg("path", {
        d: `M ${x1} ${y - 10} h 30 v 20 h -30`,
        class: "step-line",
      });
      arrow = svg("polygon", {
        points: `${x1},${y + 10} ${x1 - 6},${y + 6} ${x1 - 6},${y + 14}`,
        class: "step-arrow",
      });
    } else {
      line = svg("line", { x1, y1: y, x2: x2 - dir * 8, y2: y, class: "step-line" });
      arrow = svg("polygon", {
        points: `${x2},${y} ${x2 - dir * 10},${y - 5} ${x2 - dir * 10},${y + 5}`,
        class: "step-arrow",
      });
    }
    group.appendChild(line);
    group.appendChild(arrow);

    // pulse circle at destination
    const pulse = svg("circle", { cx: x2, cy: y, r: 6, class: "step-pulse" });
    group.appendChild(pulse);

    // step label box (centered between from and to)
    const labelX = isSelf ? x1 + 40 : Math.min(x1, x2) + Math.abs(x2 - x1) / 2;
    const labelText = String(step.n) + ". " + (step.label || "");
    const charW = 7;
    const boxW = Math.min(labelText.length * charW + 16, totalW - 20);
    const box = svg("rect", {
      x: labelX - boxW / 2, y: y - 14, width: boxW, height: 20, rx: 4,
      class: "step-label-box",
    });
    const text = svg("text", {
      x: labelX, y: y, "text-anchor": "middle",
      class: "step-label-text",
    });
    text.textContent = labelText;
    group.appendChild(box);
    group.appendChild(text);

    canvas.appendChild(group);
    return { group, line, arrow, pulse, step };
  }).filter(Boolean);

  // ---------- helpers ----------
  function svg(name, attrs) {
    const el = document.createElementNS(NS, name);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ---------- public API for app.js ----------
  window.__flowRender = {
    data,
    stepNodes,
    setActive(stepIdx) {
      stepNodes.forEach((node, i) => {
        const active = i <= stepIdx;
        node.line.classList.toggle("active", active);
        node.arrow.classList.toggle("active", active);
        node.pulse.classList.toggle("active", i === stepIdx);
      });
      const s = data.steps[stepIdx];
      if (!s) return;
      stepTitle.textContent = `Paso ${s.n}`;
      stepLabel.textContent = s.label || "";
      const detail = s.detail || (s.payload ? JSON.stringify(s.payload, null, 2) : "");
      stepDetail.querySelector("code").textContent = detail;
      stepCounter.textContent = `${stepIdx + 1} / ${data.steps.length}`;
    },
    reset() {
      stepNodes.forEach((n) => {
        n.line.classList.remove("active");
        n.arrow.classList.remove("active");
        n.pulse.classList.remove("active");
      });
      stepTitle.textContent = "Paso";
      stepLabel.textContent = "";
      stepDetail.querySelector("code").textContent = "";
      stepCounter.textContent = `0 / ${data.steps.length}`;
    },
  };
})();