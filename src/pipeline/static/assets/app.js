const graphEl = document.querySelector("#graph");
const statusEl = document.querySelector("#status");
const alertEl = document.querySelector("#alert");
const assetsEl = document.querySelector("#assets");
const processedEl = document.querySelector("#processed");
const promptsEl = document.querySelector("#prompts");
const promptListEl = document.querySelector("#prompt-list");
const promptDialogEl = document.querySelector("#prompt-dialog");
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
  if (!audioCtx) {
    audioCtx = new Ctx();
    audioCtx.onstatechange = flushAnnouncement;
  }
  if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
  return audioCtx;
}

// A page that has had no user gesture yet cannot play audio, which is exactly
// the state a freshly reloaded tab is in — so an already-pending prompt would
// be announced silently. Hold the sound instead and let it out the moment the
// context unblocks. resume() is async, hence the statechange hook above.
let pendingAnnouncement = null;

function announce(sound) {
  const ctx = ensureAudioContext();
  if (ctx && ctx.state === "running") sound();
  else pendingAnnouncement = sound;
}

function flushAnnouncement() {
  const sound = pendingAnnouncement;
  if (!sound || !audioCtx || audioCtx.state !== "running") return;
  pendingAnnouncement = null;
  sound();
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

// White-noise buffer, shaped through a high-pass/band-pass filter with a
// fast decay — reads as a crisp, percussive "tick" rather than a musical
// tone, similar to a Slack-style notification ping.
let noiseBufferCache = null;

function getNoiseBuffer(ctx) {
  const length = ctx.sampleRate * 0.5;
  if (noiseBufferCache && noiseBufferCache.sampleRate === ctx.sampleRate) return noiseBufferCache;
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
  noiseBufferCache = buffer;
  return buffer;
}

function playNoiseBurst({ startTime = 0, duration = 0.05, gain = 0.18, filterType = "highpass", filterFreq = 6500, filterQ = 0.8 } = {}) {
  if (!soundEnabled) return;
  const ctx = ensureAudioContext();
  if (!ctx) return;
  try {
    const now = ctx.currentTime + startTime;
    const source = ctx.createBufferSource();
    source.buffer = getNoiseBuffer(ctx);
    const filter = ctx.createBiquadFilter();
    filter.type = filterType;
    filter.frequency.value = filterFreq;
    filter.Q.value = filterQ;
    const gainNode = ctx.createGain();
    gainNode.gain.setValueAtTime(0.0001, now);
    gainNode.gain.exponentialRampToValueAtTime(gain, now + 0.004);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    source.connect(filter).connect(gainNode).connect(ctx.destination);
    source.start(now);
    source.stop(now + duration + 0.02);
  } catch {}
}

// Bell-like tone: a fundamental plus a few overtone partials, each with its
// own slow decay, layered together. Used for the long pipeline-end chimes so
// they read as a ringing chime rather than a short beep.
const CHIME_PARTIALS = [
  { ratio: 1, amp: 1 },
  { ratio: 2.0, amp: 0.5 },
  { ratio: 3.0, amp: 0.3 },
  { ratio: 4.2, amp: 0.15 },
];
// Slightly inharmonic ratio (1.5x) gives this set a duller, clangier "toll"
// character instead of a clean bell — used for the failure chime.
const TOLL_PARTIALS = [
  { ratio: 1, amp: 1 },
  { ratio: 1.5, amp: 0.45 },
  { ratio: 2.0, amp: 0.25 },
];

function playChimeNote({ freq, startTime = 0, duration = 1.6, gain = 0.15, partials = CHIME_PARTIALS, type = "sine" }) {
  if (!soundEnabled) return;
  const ctx = ensureAudioContext();
  if (!ctx) return;
  const now = ctx.currentTime + startTime;
  partials.forEach(({ ratio, amp }) => {
    try {
      const osc = ctx.createOscillator();
      const gainNode = ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq * ratio;
      const peak = gain * amp;
      gainNode.gain.setValueAtTime(0.0001, now);
      gainNode.gain.exponentialRampToValueAtTime(peak, now + 0.02);
      gainNode.gain.exponentialRampToValueAtTime(0.0001, now + duration);
      osc.connect(gainNode).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + duration + 0.05);
    } catch {}
  });
}

function playChimeSequence(notes) {
  notes.forEach(playChimeNote);
}

const SOUNDS = {
  pipelineStart: () => playSequence([
    { freq: 440, startTime: 0, duration: 0.1 },
    { freq: 660, startTime: 0.09, duration: 0.16 },
  ]),
  // Short burst of high-frequency filtered noise, like a Slack-style
  // notification ping, rather than a musical tone.
  taskStart: () => {
    playNoiseBurst({ startTime: 0, duration: 0.045, gain: 0.2, filterFreq: 7500, filterQ: 0.9 });
    playNoiseBurst({ startTime: 0.04, duration: 0.06, gain: 0.14, filterFreq: 5500, filterQ: 0.9 });
  },
  taskSuccess: () => playTone({ freq: 784, duration: 0.1, gain: 0.13 }),
  // Two harsh, descending square-wave buzzes ("wrong answer" register) plus a
  // filtered noise rasp under the second note, so a single failed stage reads
  // as an unambiguous error rather than a faint blip.
  taskFailure: () => {
    playTone({ freq: 196, duration: 0.16, type: "square", gain: 0.2 });
    playTone({ freq: 138.6, startTime: 0.15, duration: 0.32, type: "square", gain: 0.2 });
    playNoiseBurst({ startTime: 0.15, duration: 0.28, gain: 0.1, filterType: "lowpass", filterFreq: 900, filterQ: 0.7 });
  },
  // Long, bright ascending arpeggio with clean harmonic overtones — each note
  // rings and overlaps the next, ~3s total.
  pipelineSuccess: () => playChimeSequence([
    { freq: 523.25, startTime: 0, duration: 1.6, gain: 0.15 },    // C5
    { freq: 659.25, startTime: 0.18, duration: 1.7, gain: 0.15 }, // E5
    { freq: 783.99, startTime: 0.36, duration: 1.9, gain: 0.15 }, // G5
    { freq: 1046.5, startTime: 0.58, duration: 2.3, gain: 0.16 }, // C6, long tail
  ]),
  // Long, low tolling chime with a dissonant clash and duller overtones —
  // deliberately unsettling rather than bright. The D4/C#4 clash tolls twice
  // (like a klaxon repeating) before the long low tail, both to read as more
  // urgent than a single strike and to guarantee ample time to be heard —
  // ~4.2s total, louder than the plain success chime.
  pipelineFailure: () => playChimeSequence([
    { freq: 293.66, startTime: 0, duration: 1.1, gain: 0.18, partials: TOLL_PARTIALS, type: "triangle" },    // D4
    { freq: 277.18, startTime: 0.16, duration: 1.1, gain: 0.16, partials: TOLL_PARTIALS, type: "triangle" }, // C#4 clashes with D4
    { freq: 293.66, startTime: 0.85, duration: 1.1, gain: 0.18, partials: TOLL_PARTIALS, type: "triangle" }, // D4, second strike
    { freq: 277.18, startTime: 1.01, duration: 1.1, gain: 0.16, partials: TOLL_PARTIALS, type: "triangle" }, // C#4 clashes again
    { freq: 196.0, startTime: 1.6, duration: 2.6, gain: 0.2, partials: TOLL_PARTIALS, type: "triangle" },    // G3, long low tail
  ]),
  // A prompt halts the whole run until it is answered, so this is the one
  // sound that has to carry across a room: a three-times-repeated two-note
  // "ding-dong" that rings for ~3s, distinct from the end-of-run chimes.
  decisionPrompt: () => playChimeSequence([
    { freq: 987.77, startTime: 0, duration: 0.9, gain: 0.17 },    // B5
    { freq: 739.99, startTime: 0.3, duration: 1.1, gain: 0.17 },  // F#5
    { freq: 987.77, startTime: 0.95, duration: 0.9, gain: 0.16 },
    { freq: 739.99, startTime: 1.25, duration: 1.1, gain: 0.16 },
    { freq: 987.77, startTime: 1.9, duration: 1.0, gain: 0.16 },
    { freq: 739.99, startTime: 2.2, duration: 1.6, gain: 0.17 },  // long tail
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

  // Several prompts can arrive in one state update; one chime covers the batch
  // rather than stacking overlapping copies of a 3s sound.
  const hasNewPrompt = [...promptIds].some(id => !previousPromptIds.has(id));

  if (!stateBaselineCaptured) {
    // First render reflects whatever the server already had (e.g. a page
    // reload mid-run) rather than a live transition, so stage and run sounds
    // here would be phantoms. A pending prompt is the exception: it is a live
    // request that is still waiting to be answered, so it still gets announced.
    stateBaselineCaptured = true;
    previousRunning = running;
    previousStageStates = { ...stageStates };
    previousPromptIds = promptIds;
    if (hasNewPrompt) announce(SOUNDS.decisionPrompt);
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

  if (hasNewPrompt) announce(SOUNDS.decisionPrompt);

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
      ["Skip this file", { action: "skip" }],
      ["Cancel run", { action: "cancel" }],
    ];
  }
  if (prompt.prompt_type === "grouping_review") {
    // Re-scan is the normal path: rename the folders (here or in Explorer),
    // then have the pipeline look again. Continue anyway is the fast-forward
    // for folders you meant to leave unnamed.
    return [
      ["Re-scan folders", { action: "rescan" }],
      ["Continue anyway", { action: "continue" }],
    ];
  }
  if (prompt.prompt_type === "unknown_camera") {
    return null; // handled by the camera mapping form
  }
  return [["Done", { done: true }]];
}

function describeList(title, items) {
  const block = document.createElement("div");
  block.className = "prompt-file";
  const heading = document.createElement("strong");
  heading.textContent = title;
  block.appendChild(heading);
  (items || []).forEach(text => {
    const row = document.createElement("div");
    row.textContent = text;
    block.appendChild(row);
  });
  return block;
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

// The dialog is deliberately not dismissible: the run cannot continue until
// the decision is made, so closing it would only hide the thing being waited on.
if (promptDialogEl) {
  promptDialogEl.addEventListener("cancel", event => event.preventDefault());
}

function syncPromptDialog(pendingCount) {
  // The click that answers a held-back prompt is itself the gesture that
  // unblocks audio, so without this the chime would ring just as the user
  // resolves the thing it was announcing.
  if (!pendingCount) pendingAnnouncement = null;
  if (!promptDialogEl) return;
  if (pendingCount && !promptDialogEl.open) {
    promptDialogEl.showModal();
  } else if (!pendingCount && promptDialogEl.open) {
    promptDialogEl.close();
  }
}

function renderPrompts(prompts) {
  if (!promptListEl) return;
  promptListEl.innerHTML = "";
  const pending = (prompts || []).filter(prompt => !prompt.answered);
  pending.forEach(prompt => {
    const card = document.createElement("div");
    card.className = "prompt-card";
    const title = document.createElement("h3");
    title.textContent = prompt.prompt_type.replaceAll("_", " ");
    card.appendChild(title);

    if (prompt.payload && prompt.payload.instructions) {
      const note = document.createElement("p");
      note.className = "prompt-instructions";
      note.textContent = prompt.payload.instructions;
      card.appendChild(note);
    }

    if (prompt.prompt_type === "name_collision") {
      card.appendChild(describeFile("Existing", prompt.payload.existing));
      card.appendChild(describeFile("New file", prompt.payload.candidate));
    } else if (prompt.prompt_type === "grouping_review") {
      const names = prompt.payload.names || [];
      card.appendChild(describeList(`Still unnamed (${names.length})`, names));
    } else if (prompt.payload && prompt.payload.paths) {
      card.appendChild(describeList(
        `${prompt.payload.asset_count ?? prompt.payload.paths.length} file(s)`,
        prompt.payload.paths));
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
  syncPromptDialog(pending.length);
}

function renderState(state) {
  detectAndPlayTransitionSounds(state);
  // A run blocked on a prompt is still running; saying so is the difference
  // between "it is waiting for me" and "it hung".
  statusEl.textContent = state.error
    || (state.waiting_for ? "Waiting for you" : state.running ? "Running" : state.paused ? "Paused" : "Idle");
  document.body.classList.toggle("awaiting-prompt", Boolean(state.waiting_for));
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
