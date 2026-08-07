// app.template.js — oauth-flow-html skill
// Wires up play/pause/reset controls + step navigation.
(function () {
  "use strict";
  const render = window.__flowRender;
  if (!render) { console.error("[oauth-flow-html] render missing"); return; }

  const steps = render.data.steps;
  const total = steps.length;
  let current = -1;
  let playing = false;
  let timer = null;

  const btnPlay = document.getElementById("btn-play");
  const btnPause = document.getElementById("btn-pause");
  const btnReset = document.getElementById("btn-reset");
  const btnPrev = document.getElementById("prev-step");
  const btnNext = document.getElementById("next-step");
  const speedInput = document.getElementById("speed");
  const speedValue = document.getElementById("speed-value");

  function durationFor(stepIdx) {
    const base = (steps[stepIdx].duration_ms || 1200);
    const speed = parseFloat(speedInput.value);
    return base / speed;
  }

  function showStep(idx) {
    current = Math.max(-1, Math.min(total - 1, idx));
    if (current < 0) render.reset();
    else render.setActive(current);
    btnPrev.disabled = current <= -1;
    btnNext.disabled = current >= total - 1;
    if (playing) scheduleNext();
  }

  function scheduleNext() {
    clearTimeout(timer);
    if (!playing || current >= total - 1) { stop(); return; }
    timer = setTimeout(() => showStep(current + 1), durationFor(current));
  }

  function play() {
    if (current >= total - 1) showStep(-1);
    playing = true;
    btnPlay.disabled = true; btnPause.disabled = false;
    if (current === -1) showStep(0);
    else scheduleNext();
  }
  function stop() {
    playing = false;
    btnPlay.disabled = false; btnPause.disabled = true;
    clearTimeout(timer);
  }
  function reset() { stop(); showStep(-1); }

  btnPlay.addEventListener("click", play);
  btnPause.addEventListener("click", stop);
  btnReset.addEventListener("click", reset);
  btnPrev.addEventListener("click", () => showStep(current - 1));
  btnNext.addEventListener("click", () => showStep(current + 1));
  speedInput.addEventListener("input", () => {
    speedValue.textContent = parseFloat(speedInput.value).toFixed(2) + "×";
    if (playing) scheduleNext();
  });

  // Click on any step group to jump to it
  render.stepNodes.forEach((node, i) => {
    node.group.addEventListener("click", () => { stop(); showStep(i); });
  });

  // initialize
  render.reset();
  btnPause.disabled = true;
})();