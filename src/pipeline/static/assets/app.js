const graphEl = document.querySelector("#graph");
const statusEl = document.querySelector("#status");
const alertEl = document.querySelector("#alert");
const assetsEl = document.querySelector("#assets");
const processedEl = document.querySelector("#processed");
const promptsEl = document.querySelector("#prompts");
const promptListEl = document.querySelector("#prompt-list");
const logsEl = document.querySelector("#logs");
const soundToggleEl = document.querySelector("#sound-toggle");
let graph = [];

// --- Sound effects -----------------------------------------------------
// Small synthesized tones (Web Audio API) rather than shipped audio files,
// so no binary assets need to live in the repo.

const SOUND_ENABLED_KEY = "photosorter.soundEnabled";
let soundEnabled = localStorage.getItem(SOUND_ENABLED_KEY) !== "off";
let audioCtx = null;

function ensureAudioContext() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  if (!audioCtx) audioCtx = new Ctx();
  if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
  return audioCtx;
}

// Browsers require a user gesture before audio can play; prime the context
// on the first click/keypress so later, event-driven sounds are unblocked.
function primeAudioOnce() {
  ensureAudioContext();
  document.removeEventListener("pointerdown", primeAudioOnce);
  document.removeEventListener("keydown", primeAudioOnce);
}
document.addEventListener("pointerdown", primeAudioOnce, { once: true });
document.addEventListener("keydown", primeAudioOnce, { once: true });

function playTone({ freq, duration = 0.14, type = "sine", startTime = 0, gain = 0.16 }) {
  if (!soundEnabled) return;
  const ctx = ensureAudioContext();
  if (!ctx) return;
  try {
    const osc = ctx.createOscillator();
    const gainNode = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    const now = ctx.currentTime + startTime;
    gainNode.gain.setValueAtTime(0.0001, now);
    gainNode.gain.exponentialRampToValueAtTime(gain, now + 0.012);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    osc.connect(gainNode).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + duration + 0.03);
  } catch {}
}

function playSequence(notes) {
  notes.forEach(playTone);
}

const SOUNDS = {
  pipelineStart: () => playSequence([
    { freq: 440, startTime: 0, duration: 0.1 },
    { freq: 660, startTime: 0.09, duration: 0.16 },
  ]),
  taskStart: () => playTone({ freq: 523, duration: 0.07, gain: 0.1 }),
  taskSuccess: () => playTone({ freq: 784, duration: 0.1, gain: 0.13 }),
  taskFailure: () => playTone({ freq: 220, duration: 0.22, type: "square", gain: 0.15 }),
  pipelineSuccess: () => playSequence([
    { freq: 523, startTime: 0, duration: 0.12 },
    { freq: 659, startTime: 0.11, duration: 0.12 },
    { freq: 784, startTime: 0.22, duration: 0.24 },
  ]),
  pipelineFailure: () => playSequence([
    { freq: 392, startTime: 0, duration: 0.16, type: "sawtooth" },
    { freq: 262, startTime: 0.15, duration: 0.3, type: "sawtooth" },
  ]),
  decisionPrompt: () => playSequence([
    { freq: 880, startTime: 0, duration: 0.09, type: "triangle", gain: 0.15 },
    { freq: 880, startTime: 0.16, duration: 0.09, type: "triangle", gain: 0.15 },
  ]),
};

function setSoundEnabled(enabled) {
  soundEnabled = enabled;
  localStorage.setItem(SOUND_ENABLED_KEY, enabled ? "on" : "off");
  if (soundToggleEl) {
    soundToggleEl.textContent = enabled ? "\u{1F50A} Sound" : "\u{1F507} Sound";
    soundToggleEl.setAttribute("aria-pressed", String(!enabled));
  }
}

if (soundToggleEl) {
  setSoundEnabled(soundEnabled);
  soundToggleEl.addEventListener("click", () => setSoundEnabled(!soundEnabled));
}

// Diffing state used to detect transitions between renderState() calls.
let stateBaselineCaptured = false;
let previousRunning = false;
let previousStageStates = {};
let previousPromptIds = new Set();

function detectAndPlayTransitionSounds(state) {
  const running = Boolean(state.running);
  const stageStates = state.stage_states || {};
  const promptIds = new Set((state.prompts || []).filter(p => !p.answered).map(p => p.prompt_id));

  if (!stateBaselineCaptured) {
    // First render reflects whatever the server already had (e.g. a page
    // reload mid-run) rather than a live transition, so establish a
    // baseline silently instead of firing sounds for pre-existing state.
    stateBaselineCaptured = true;
    previousRunning = running;
    previousStageStates = { ...stageStates };
    previousPromptIds = promptIds;
    return;
  }

  if (running && !previousRunning) {
    SOUNDS.pipelineStart();
  } else if (!running && previousRunning) {
    if (state.error) SOUNDS.pipelineFailure();
    else SOUNDS.pipelineSuccess();
  }

  Object.entries(stageStates).forEach(([stageId, value]) => {
    const previous = previousStageStates[stageId];
    if (value === previous) return;
    if (value === "active") SOUNDS.taskStart();
    else if (value === "complete") SOUNDS.taskSuccess();
    else if (value === "failed") SOUNDS.taskFailure();
  });

  promptIds.forEach(id => {
    if (!previousPromptIds.has(id)) SOUNDS.decisionPrompt();
  });

  previousRunning = running;
  previousStageStates = { ...stageStates };
  previousPromptIds = promptIds;
}

async function api(path, options) {
  const r = await fetch(path, options);
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch {}
    throw new Error(detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

async function load() {
  graph = (await api("/api/pipeline/graph")).nodes || [];
  renderGraph({});
  renderState(await api("/api/pipeline/state"));
  connect();
}

const STATE_ICON = {
  pending: "○",   // ○  not started
  active: "▶",    // ▶  in progress
  paused: "⏸",    // ⏸  paused
  complete: "✔",  // ✔  succeeded
  failed: "✖",    // ✖  failed
  skipped: "–",   // –  skipped
};

function renderNodeStats(stats) {
  const box = document.createElement("span");
  box.className = "node-stats";
  const parts = [
    ["in", stats.inputs, "node-stat"],
    ["out", stats.outputs, "node-stat"],
    ["err", stats.errors, "node-stat node-errors"],
  ];
  parts.forEach(([label, value, className]) => {
    if (value === undefined || (label === "err" && !value)) return;
    const part = document.createElement("span");
    part.className = className;
    part.textContent = `${label} ${value}`;
    box.appendChild(part);
  });
  return box;
}

function renderGraph(states, stats = {}) {
  graphEl.innerHTML = "";
  graph.forEach((node, index) => {
    const state = states[node.id] || "pending";
    const el = document.createElement("div");
    el.className = `node ${state}`;
    const icon = document.createElement("span");
    icon.className = "node-icon";
    icon.textContent = STATE_ICON[state] || STATE_ICON.pending;
    const number = document.createElement("span");
    number.className = "node-number";
    number.textContent = String(index + 1).padStart(2, "0");
    const separator = document.createElement("span");
    separator.className = "node-sep";
    separator.textContent = "·";
    const text = document.createElement("span");
    text.className = "node-text";
    text.textContent = node.label;
    el.append(icon, number, separator, text);
    const nodeStats = stats[node.id];
    if (nodeStats && Object.values(nodeStats).some(value => value !== undefined)) {
      el.appendChild(renderNodeStats(nodeStats));
    }
    graphEl.appendChild(el);
  });
}

function renderStageLog(parent, line) {
  const stageId = line.slice("Stage: ".length);
  // Number by the stage's position in the pipeline graph, so it stays stable
  // even when older log lines scroll out of the retained window.
  const index = graph.findIndex(node => node.id === stageId);
  const number = document.createElement("span");
  number.className = "stage-number";
  number.textContent = index >= 0 ? String(index + 1).padStart(2, "0") : "--";
  const label = document.createElement("span");
  label.textContent = "Stage: ";
  const name = document.createElement("strong");
  name.textContent = stageId;
  parent.className = "log-line stage-log";
  parent.append(number, label, name);
}

function showError(error) {
  alertEl.textContent = error.message;
  alertEl.classList.remove("hidden");
}

function answerPrompt(promptId, answer) {
  return api(`/api/prompts/${promptId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(answer),
  }).then(payload => {
    if (payload.state) renderState(payload.state);
  }).catch(showError);
}

function describeFile(title, info) {
  const block = document.createElement("div");
  block.className = "prompt-file";
  const heading = document.createElement("strong");
  heading.textContent = title;
  block.appendChild(heading);
  if (!info) return block;
  const lines = [
    info.path,
    `size: ${info.size} bytes`,
    `modified: ${new Date(info.modified_at * 1000).toLocaleString()}`,
    `md5: ${info.md5}`,
  ];
  lines.forEach(text => {
    const row = document.createElement("div");
    row.textContent = text;
    block.appendChild(row);
  });
  return block;
}

function promptActions(prompt) {
  if (prompt.prompt_type === "name_collision") {
    return [
      ["Keep existing", { action: "keep_existing" }],
      ["Keep new file", { action: "keep_candidate" }],
      ["Rename new file", { action: "rename_candidate" }],
      ["Cancel run", { action: "cancel" }],
    ];
  }
  if (prompt.prompt_type === "unknown_camera") {
    return null; // handled by the camera mapping form
  }
  return [["Done", { done: true }]];
}

function renderCameraForm(card, prompt) {
  const form = document.createElement("form");
  const input = document.createElement("input");
  input.placeholder = "Camera symbol, e.g. C6D";
  input.required = true;
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "Save mapping";
  form.append(input, submit);
  form.addEventListener("submit", event => {
    event.preventDefault();
    answerPrompt(prompt.prompt_id, {
      camera_model: prompt.payload.camera_model,
      symbol: input.value.trim(),
    });
  });
  card.appendChild(form);
}

function renderPrompts(prompts) {
  if (!promptListEl) return;
  promptListEl.innerHTML = "";
  (prompts || []).filter(prompt => !prompt.answered).forEach(prompt => {
    const card = document.createElement("div");
    card.className = "prompt-card";
    const title = document.createElement("h3");
    title.textContent = prompt.prompt_type.replaceAll("_", " ");
    card.appendChild(title);

    if (prompt.prompt_type === "name_collision") {
      card.appendChild(describeFile("Existing", prompt.payload.existing));
      card.appendChild(describeFile("New file", prompt.payload.candidate));
    } else if (prompt.prompt_type === "unknown_camera") {
      const model = document.createElement("div");
      model.textContent = `Camera model: ${prompt.payload.camera_model}`;
      card.appendChild(model);
    } else {
      const detail = document.createElement("div");
      detail.textContent = JSON.stringify(prompt.payload);
      card.appendChild(detail);
    }

    const actions = promptActions(prompt);
    if (actions === null) {
      renderCameraForm(card, prompt);
    } else {
      const row = document.createElement("div");
      row.className = "prompt-actions";
      actions.forEach(([label, answer]) => {
        const button = document.createElement("button");
        button.textContent = label;
        button.addEventListener("click", () => answerPrompt(prompt.prompt_id, answer));
        row.appendChild(button);
      });
      card.appendChild(row);
    }
    promptListEl.appendChild(card);
  });
}

function renderState(state) {
  detectAndPlayTransitionSounds(state);
  statusEl.textContent = state.error || (state.running ? "Running" : state.paused ? "Paused" : "Idle");
  if (state.error) {
    alertEl.textContent = state.error;
    alertEl.classList.remove("hidden");
  } else {
    alertEl.classList.add("hidden");
  }
  assetsEl.textContent = state.counters?.other_images_classification_pending ?? state.counters?.assets ?? state.counters?.input_files ?? 0;
  processedEl.textContent = state.counters?.other_images_classification_processed ?? state.counters?.sorted_assets ?? 0;
  promptsEl.textContent = (state.prompts || []).filter(prompt => !prompt.answered).length;
  renderPrompts(state.prompts);
  renderGraph(state.stage_states || {}, state.stage_stats || {});
  logsEl.innerHTML = "";
  // Stage outcome is shown by the node icons, so drop the bare status lines.
  const STATUS_LINES = new Set(["Completed.", "Failed.", "Paused."]);
  (state.logs || []).filter(line => !STATUS_LINES.has(String(line).trim())).forEach(line => {
    const row = document.createElement("div");
    if (String(line).startsWith("Stage: ")) {
      renderStageLog(row, String(line));
    } else {
      row.className = "log-line";
      row.textContent = line;
    }
    logsEl.appendChild(row);
  });
  logsEl.parentElement.scrollTop = logsEl.parentElement.scrollHeight;
}

let serverStopped = false;

function connect() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws/events`);
  socket.onmessage = e => {
    const payload = JSON.parse(e.data);
    if (payload.state) renderState(payload.state);
  };
  socket.onclose = () => { if (!serverStopped) setTimeout(connect, 1200); };
}

document.querySelectorAll("button[data-action]").forEach(button =>
  button.addEventListener("click", () =>
    api(`/api/pipeline/${button.dataset.action}`, { method: "POST" })
      .then(payload => { if (payload.state) renderState(payload.state); })
      .catch(showError)));

const stopServerEl = document.querySelector("#stop-server");
if (stopServerEl) {
  stopServerEl.addEventListener("click", async () => {
    serverStopped = true;
    try { await api("/api/server/shutdown", { method: "POST" }); } catch {}
    statusEl.textContent = "Server stopped - you can close this tab.";
  });
}

load().catch(showError);
