const graphEl = document.querySelector("#graph");
const statusEl = document.querySelector("#status");
const nowEl = document.querySelector("#now");
const alertEl = document.querySelector("#alert");
const summaryEl = document.querySelector("#summary");
const promptListEl = document.querySelector("#prompt-list");
const promptDialogEl = document.querySelector("#prompt-dialog");
const logsEl = document.querySelector("#logs");
const soundToggleEl = document.querySelector("#sound-toggle");
let graph = [];
// The last state the server pushed, so the once-a-second clock tick can
// recompute elapsed times without waiting for the next websocket frame.
let lastState = {};

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
  // The screenshot-grouping stage blocks the whole pipeline while it pops an
  // external GUI window (the Image Grouper) that needs the user's attention,
  // so it gets its own cue instead of the generic taskStart tick: a shutter-
  // click burst (nod to "image") followed by a bright rising triangle-wave
  // run, longer and more melodic so it doesn't blend into ordinary stage
  // starts.
  imageGrouperLaunch: () => {
    playNoiseBurst({ startTime: 0, duration: 0.03, gain: 0.22, filterType: "bandpass", filterFreq: 3000, filterQ: 1.4 });
    playTone({ freq: 587.33, startTime: 0.05, duration: 0.13, type: "triangle", gain: 0.16 }); // D5
    playTone({ freq: 880.0, startTime: 0.16, duration: 0.16, type: "triangle", gain: 0.16 });   // A5
    playTone({ freq: 1174.66, startTime: 0.3, duration: 0.28, type: "triangle", gain: 0.17 });  // D6, bright landing note
  },
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

// Stage that launches the external Image Grouper GUI — gets its own start
// sound (SOUNDS.imageGrouperLaunch) instead of the generic taskStart tick.
const IMAGE_GROUPER_STAGE_ID = "screenshot-grouping";

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
    if (value === "active") {
      if (stageId === IMAGE_GROUPER_STAGE_ID) SOUNDS.imageGrouperLaunch();
      else SOUNDS.taskStart();
    }
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

// --- Formatting --------------------------------------------------------
// Deliberately mirrors src/utils/progress.py: the same run should read the
// same in the terminal and in the browser.

function formatCount(value) {
  if (value === null || value === undefined) return "";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : String(value);
}

function formatBytes(value) {
  let size = Number(value);
  if (!Number.isFinite(size)) return String(value);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  while (Math.abs(size) >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return index === 0 ? `${size.toFixed(0)} B` : `${size.toFixed(1)} ${units[index]}`;
}

function formatDuration(seconds) {
  const total = Number(seconds);
  if (!Number.isFinite(total) || total < 0) return "";
  if (total < 1) return "<1s";
  if (total < 60) return `${Math.round(total)}s`;
  const minutes = Math.floor(total / 60);
  const secs = Math.floor(total % 60);
  if (minutes < 60) return `${minutes}m ${String(secs).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
}

// A stage still running has no finish time, so its elapsed is measured
// against the wall clock — which is why the page ticks once a second rather
// than only when the server pushes.
function stageElapsed(timing) {
  if (!timing) return null;
  if (timing.duration_seconds !== undefined && timing.duration_seconds !== null) {
    return timing.duration_seconds;
  }
  if (!timing.started_at) return null;
  return Math.max(0, Date.now() / 1000 - timing.started_at);
}

// --- Stage nodes -------------------------------------------------------

// Stages whose detail the user has opened. Kept outside the render so a
// rebuild on every state push does not slam them shut mid-read.
const expandedStages = new Set();

// in/out/err first and always in that order; anything else a stage recorded
// follows. Matches the console banner, so the two are comparable line by line.
const PRIMARY_STAT_KEYS = ["inputs", "outputs", "errors"];
const STAT_LABELS = { inputs: "in", outputs: "out", errors: "err" };
const BYTE_STAT_KEYS = new Set(["bytes", "bytes_read"]);

function statChips(stats) {
  const chips = [];
  PRIMARY_STAT_KEYS.forEach(key => {
    const value = stats[key];
    if (value === undefined || value === null) return;
    if (key === "errors" && !value) return;
    chips.push([STAT_LABELS[key], formatCount(value), key === "errors"]);
  });
  Object.keys(stats)
    .filter(key => !PRIMARY_STAT_KEYS.includes(key))
    .sort()
    .forEach(key => {
      const value = stats[key];
      if (!value) return;
      const shown = BYTE_STAT_KEYS.has(key) ? formatBytes(value) : formatCount(value);
      chips.push([key.replace(/_/g, " "), shown, false]);
    });
  return chips;
}

function renderNodeStats(stats) {
  const box = document.createElement("span");
  box.className = "node-stats";
  statChips(stats).forEach(([label, value, isError]) => {
    const part = document.createElement("span");
    part.className = isError ? "node-stat node-errors" : "node-stat";
    part.textContent = `${label} ${value}`;
    box.appendChild(part);
  });
  return box;
}

function renderNodeProgress(progress) {
  const box = document.createElement("div");
  box.className = "node-progress";
  const track = document.createElement("div");
  track.className = "progress-track";
  const fill = document.createElement("div");
  // A stage that cannot know its total yet gets a barber-pole rather than a
  // bar frozen at zero, which reads as stuck.
  if (progress.fraction === null || progress.fraction === undefined) {
    fill.className = "progress-fill indeterminate";
    fill.style.width = "100%";
  } else {
    fill.className = "progress-fill";
    fill.style.width = `${Math.max(1, Math.round(progress.fraction * 100))}%`;
  }
  track.appendChild(fill);
  const text = document.createElement("div");
  text.className = "progress-text";
  text.textContent = progress.summary || progress.activity || "";
  box.append(track, text);
  return box;
}

function renderNodeDetail(node, stats, notes, timing) {
  const box = document.createElement("div");
  box.className = "node-detail";
  if (node.description) {
    const description = document.createElement("p");
    description.className = "node-description";
    description.textContent = node.description;
    box.appendChild(description);
  }
  (notes || []).forEach(note => {
    const row = document.createElement("p");
    row.className = "node-note";
    row.textContent = note;
    box.appendChild(row);
  });
  const facts = [];
  if (timing && timing.started_at) {
    facts.push(`started ${new Date(timing.started_at * 1000).toLocaleTimeString()}`);
  }
  if (timing && timing.detail) facts.push(timing.detail);
  const chips = statChips(stats || {});
  if (chips.length) {
    facts.push(chips.map(([label, value]) => `${label} ${value}`).join(", "));
  }
  if (facts.length) {
    const row = document.createElement("p");
    row.className = "node-facts";
    row.textContent = facts.join(" · ");
    box.appendChild(row);
  }
  return box;
}

function renderGraph(states, stats = {}, timings = {}, progress = {}, notes = {}) {
  const scroll = graphEl.scrollTop;
  graphEl.innerHTML = "";
  graph.forEach((node, index) => {
    const state = states[node.id] || "pending";
    const nodeStats = stats[node.id] || {};
    const nodeProgress = progress[node.id];
    const timing = timings[node.id];
    // The running stage always shows its detail: it is the one the reader is
    // asking about. Anything else opens on click and stays open.
    const expanded = expandedStages.has(node.id) || state === "active";

    const el = document.createElement("div");
    el.className = `node ${state}${expanded ? " expanded" : ""}`;
    // The description is the tooltip too, so it is reachable without a click.
    if (node.description) el.title = `${node.label} — ${node.description}`;

    const row = document.createElement("div");
    row.className = "node-row";
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
    row.append(icon, number, separator, text);

    if (Object.keys(nodeStats).length) row.appendChild(renderNodeStats(nodeStats));

    const elapsed = stageElapsed(timing);
    if (elapsed !== null) {
      const time = document.createElement("span");
      time.className = state === "active" ? "node-time running" : "node-time";
      time.textContent = formatDuration(elapsed);
      row.appendChild(time);
    }
    el.appendChild(row);

    if (nodeProgress) el.appendChild(renderNodeProgress(nodeProgress));
    if (expanded) {
      el.appendChild(renderNodeDetail(node, nodeStats, notes[node.id], timing));
    }

    el.addEventListener("click", () => {
      if (expandedStages.has(node.id)) expandedStages.delete(node.id);
      else expandedStages.add(node.id);
      renderGraph(states, stats, timings, progress, notes);
    });
    graphEl.appendChild(el);
  });
  graphEl.scrollTop = scroll;
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

// --- Run summary -------------------------------------------------------
// The same groups src/pipeline_stages/show_stats.py logs, so the panel and the
// transcript never disagree about what a run did. Zero rows are dropped: a
// column of zeroes hides the one number that is not zero.

const SUMMARY_GROUPS = [
  ["Came in", [
    ["input_files", "files in the inbox at the start"],
    ["input_files_added_later", "carried in later by harvest/migration"],
    ["input_checksums", "distinct checksums now watched"],
    ["input_bytes", "bytes to process"],
    ["input_folders", "folders they arrived in"],
    ["legacy_unsorted_migrated", "migrated from legacy unsorted"],
    ["uploaded_files_moved", "harvested from Camera Uploads"],
    ["folder_intake_files", "flattened out of subfolders"],
    ["camera_upload_photos", "camera photos separated"],
    ["camera_upload_videos", "videos separated"],
  ]],
  ["Processed", [
    ["assets", "assets with metadata read"],
    ["renamed_assets", "renamed"],
    ["timezone_corrected_assets", "capture times corrected"],
    ["sorted_assets", "moved into event folders"],
    ["event_folders_touched", "event folders written"],
    ["companions_reconciled", "companions placed"],
  ]],
  ["Set aside", [
    ["moved_old_exifs", "stale EXIF sidecars parked"],
    ["empty_files_quarantined", "zero-byte files quarantined"],
    ["rename_skipped_assets", "left with original names"],
    ["raw_only_shots", "RAW-only shots"],
    ["other_image_infographics", "infographics"],
    ["other_image_text_screenshots", "text screenshots"],
  ]],
  ["Needs a look", [
    ["rename_exif_missing", "no EXIF capture time"],
    ["timezone_ambiguous_assets", "readings in a repeated hour"],
    ["companions_left_behind", "companions with no shot"],
    ["companions_reconcile_errors", "folders that failed to reconcile"],
  ]],
  ["Verified", [
    ["safety_inputs_matched", "inputs found again in the output"],
    ["safety_files_scanned", "archive files checksummed"],
    ["safety_bytes_read", "bytes re-read to prove it"],
  ]],
];

const BYTE_COUNTERS = new Set(["input_bytes", "safety_bytes_read"]);
const ATTENTION_GROUP = "Needs a look";

function summaryRow(label, value, className) {
  const row = document.createElement("div");
  row.className = className ? `summary-row ${className}` : "summary-row";
  const key = document.createElement("span");
  key.className = "summary-label";
  key.textContent = label;
  const shown = document.createElement("span");
  shown.className = "summary-value";
  shown.textContent = value;
  row.append(key, shown);
  return row;
}

function renderRunSummary(state) {
  summaryEl.innerHTML = "";
  const counters = state.counters || {};
  const timings = state.stage_timings || {};
  const run = timings.__run__;
  const states = state.stage_states || {};

  const done = Object.values(states).filter(v => v === "complete").length;
  const stageTotal = graph.length || (run && run.stage_count) || 0;
  const runElapsed = run
    ? (run.duration_seconds ?? Math.max(0, Date.now() / 1000 - run.started_at))
    : null;

  const head = document.createElement("div");
  head.className = "summary-head";
  if (stageTotal) head.appendChild(summaryRow("Stages complete", `${done} / ${stageTotal}`));
  if (runElapsed !== null) {
    head.appendChild(summaryRow(
      state.running ? "Running for" : "Run took", formatDuration(runElapsed)));
  }
  const pending = (state.prompts || []).filter(prompt => !prompt.answered).length;
  if (pending) head.appendChild(summaryRow("Decisions waiting", formatCount(pending), "attention"));
  if (head.children.length) summaryEl.appendChild(head);

  SUMMARY_GROUPS.forEach(([heading, rows]) => {
    const present = rows.filter(([key]) => counters[key]);
    if (!present.length) return;
    const title = document.createElement("h2");
    title.className = "summary-heading";
    title.textContent = heading;
    summaryEl.appendChild(title);
    present.forEach(([key, label]) => {
      const value = BYTE_COUNTERS.has(key) ? formatBytes(counters[key]) : formatCount(counters[key]);
      summaryEl.appendChild(
        summaryRow(label, value, heading === ATTENTION_GROUP ? "attention" : ""));
    });
  });

  // Where the wall clock actually went. The single most-asked question about
  // a slow run, and until now the dashboard had no answer at all.
  const slowest = (run && run.slowest) || rankStages(timings);
  const worth = slowest.filter(entry => (entry.duration_seconds || 0) >= 1).slice(0, 5);
  if (worth.length && runElapsed) {
    const title = document.createElement("h2");
    title.className = "summary-heading";
    title.textContent = "Where the time went";
    summaryEl.appendChild(title);
    worth.forEach(entry => {
      const share = Math.round((entry.duration_seconds / runElapsed) * 100);
      summaryEl.appendChild(summaryRow(
        labelFor(entry.stage_id),
        `${formatDuration(entry.duration_seconds)} (${share}%)`));
    });
  }

  if (!summaryEl.children.length) {
    const idle = document.createElement("p");
    idle.className = "summary-idle";
    idle.textContent = "No run yet. Press Run to start the pipeline.";
    summaryEl.appendChild(idle);
  }
}

function rankStages(timings) {
  return Object.entries(timings)
    .filter(([stageId, timing]) => stageId !== "__run__" && timing.duration_seconds)
    .map(([stageId, timing]) => ({ stage_id: stageId, duration_seconds: timing.duration_seconds }))
    .sort((a, b) => b.duration_seconds - a.duration_seconds);
}

function labelFor(stageId) {
  const node = graph.find(candidate => candidate.id === stageId);
  return node ? node.label : stageId;
}

// The one-line answer to "what is it doing right now": which stage, how far
// in, and what that stage is for.
function renderNowLine(state) {
  if (!nowEl) return;
  const states = state.stage_states || {};
  const activeId = Object.keys(states).find(key => states[key] === "active");
  if (!activeId) {
    nowEl.textContent = "";
    return;
  }
  const index = graph.findIndex(node => node.id === activeId);
  const node = graph[index] || {};
  const elapsed = stageElapsed((state.stage_timings || {})[activeId]);
  const progress = (state.stage_progress || {})[activeId];
  const parts = [
    `Stage ${index + 1}/${graph.length || "?"}: ${node.label || activeId}`,
  ];
  if (elapsed !== null) parts.push(formatDuration(elapsed));
  if (progress && progress.summary) parts.push(progress.summary);
  else if (node.description) parts.push(node.description);
  nowEl.textContent = parts.join(" — ");
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

// True while a grouper opened from the review prompt still has windows up.
// Server-driven rather than local, so every tab agrees and a reload does not
// lose it: the run is blocked on the prompt either way.
let grouperRunning = false;

const GROUPER_BUSY_LABEL = "Grouper open…";

function launchGrouper(promptId, button) {
  // The GUI takes as long as the naming takes, so the button only starts it;
  // the server reports back through grouper_running until the last window is
  // closed. This click is a user gesture, so the launch cue can play here.
  SOUNDS.imageGrouperLaunch();
  const label = button.textContent;
  button.disabled = true;
  button.textContent = GROUPER_BUSY_LABEL;
  api(`/api/prompts/${promptId}/regroup`, { method: "POST" })
    .then(payload => { if (payload.state) renderState(payload.state); })
    .catch(error => {
      // A refused launch pushes no new state, so nothing would re-render the
      // button out of its "open" label — put it back by hand.
      button.disabled = false;
      button.textContent = label;
      showError(error);
    });
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
      // Neither is a loser: two exposures inside one second (F9). Offered
      // because no camera here recorded a sub-second, which is the only thing
      // that could have settled it without asking.
      ["Different shots", { action: "siblings" }],
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
      if (prompt.prompt_type === "grouping_review") {
        // The folders in this card are exactly the ones the grouper should be
        // pointed at, so offer it here instead of sending the user to Explorer
        // to find them and start the GUI by hand.
        const count = (prompt.payload.folders || prompt.payload.names || []).length;
        const launch = document.createElement("button");
        launch.className = "primary";
        launch.textContent = grouperRunning
          ? GROUPER_BUSY_LABEL
          : `Open grouper on ${count} folder(s)`;
        launch.disabled = grouperRunning;
        launch.addEventListener("click", () => launchGrouper(prompt.prompt_id, launch));
        row.appendChild(launch);
      }
      actions.forEach(([label, answer]) => {
        const button = document.createElement("button");
        button.textContent = label;
        // Answering while the GUI is still up would let reconciliation run
        // against a tree the user is mid-way through splitting.
        button.disabled = grouperRunning && prompt.prompt_type === "grouping_review";
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
  lastState = state;
  detectAndPlayTransitionSounds(state);
  // A run blocked on a prompt is still running; saying so is the difference
  // between "it is waiting for me" and "it hung".
  statusEl.textContent = state.error
    || (state.waiting_for ? "Waiting for you" : state.running ? "Running" : state.paused ? "Paused" : "Idle");
  document.body.classList.toggle("awaiting-prompt", Boolean(state.waiting_for));
  // Set before renderPrompts: the prompt buttons are rebuilt from it.
  grouperRunning = Boolean(state.grouper_running);
  if (state.error) {
    alertEl.textContent = state.error;
    alertEl.classList.remove("hidden");
  } else {
    alertEl.classList.add("hidden");
  }
  renderPrompts(state.prompts);
  renderGraph(
    state.stage_states || {},
    state.stage_stats || {},
    state.stage_timings || {},
    state.stage_progress || {},
    state.stage_notes || {},
  );
  renderRunSummary(state);
  renderNowLine(state);
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

// A stage that runs for twenty minutes pushes state only when something
// changes, so without this its elapsed time would sit frozen at whatever it
// read when the stage began — the exact appearance of a hang this whole
// change exists to remove. One second is fine: nothing here is expensive.
setInterval(() => {
  if (!lastState.running) return;
  const timings = lastState.stage_timings || {};
  const states = lastState.stage_states || {};
  const activeId = Object.keys(states).find(key => states[key] === "active");
  document.querySelectorAll(".node-time.running").forEach(el => el.remove());
  if (activeId) {
    const elapsed = stageElapsed(timings[activeId]);
    const row = graphEl.children[graph.findIndex(node => node.id === activeId)];
    if (row && elapsed !== null) {
      const time = document.createElement("span");
      time.className = "node-time running";
      time.textContent = formatDuration(elapsed);
      row.querySelector(".node-row").appendChild(time);
    }
  }
  renderRunSummary(lastState);
  renderNowLine(lastState);
}, 1000);

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
