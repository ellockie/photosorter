const state = {
  graph: [],
  prompts: new Map(),
  activePrompt: null,
};

const graphEl = document.querySelector("#graph");
const statusLine = document.querySelector("#statusLine");
const processedCount = document.querySelector("#processedCount");
const assetCount = document.querySelector("#assetCount");
const runState = document.querySelector("#runState");
const logsEl = document.querySelector("#logs");
const criticalAlert = document.querySelector("#criticalAlert");
const promptDialog = document.querySelector("#promptDialog");
const promptForm = document.querySelector("#promptForm");
const promptTitle = document.querySelector("#promptTitle");
const promptBody = document.querySelector("#promptBody");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function post(path, body = {}) {
  return api(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function loadGraph() {
  const graph = await api("/api/pipeline/graph");
  state.graph = graph.nodes || [];
  renderGraph({});
}

function renderGraph(stageStates) {
  graphEl.innerHTML = "";
  const width = Math.max(760, state.graph.length * 170);
  graphEl.setAttribute("viewBox", `0 0 ${width} 520`);

  state.graph.forEach((node, index) => {
    const x = 40 + index * 165;
    const y = 220;
    if (index > 0) {
      const line = svg("line", {
        class: "edge",
        x1: x - 65,
        y1: y + 30,
        x2: x,
        y2: y + 30,
      });
      graphEl.appendChild(line);
    }

    const group = svg("g", {
      class: `node ${stageStates[node.id] || "pending"}`,
      transform: `translate(${x}, ${y})`,
    });
    group.appendChild(svg("rect", {
      width: 132,
      height: 62,
      rx: 7,
    }));
    const text = svg("text", {
      x: 12,
      y: 28,
    });
    text.textContent = node.label;
    group.appendChild(text);
    const status = svg("text", {
      x: 12,
      y: 48,
    });
    status.textContent = stageStates[node.id] || "pending";
    group.appendChild(status);
    graphEl.appendChild(group);
  });
}

function svg(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  return el;
}

function renderState(payload) {
  const pipeline = payload.state || payload;
  const counters = pipeline.counters || {};
  const states = pipeline.stage_states || {};
  statusLine.textContent = pipeline.error || (pipeline.running ? "Running" : "Idle");
  processedCount.textContent = counters.sorted_assets || counters.rename_candidates || 0;
  assetCount.textContent = counters.assets || counters.input_files || 0;
  runState.textContent = pipeline.paused ? "paused" : (pipeline.running ? "running" : "idle");
  renderGraph(states);
  renderLogs(pipeline.logs || []);
  renderPrompts(pipeline.prompts || []);
  renderCritical(pipeline.error);
}

function renderLogs(logs) {
  logsEl.innerHTML = "";
  logs.slice(-80).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    logsEl.appendChild(li);
  });
}

function renderCritical(error) {
  if (!error || !error.includes("Safety")) {
    criticalAlert.classList.add("hidden");
    criticalAlert.textContent = "";
    return;
  }
  criticalAlert.textContent = error;
  criticalAlert.classList.remove("hidden");
}

function renderPrompts(prompts) {
  prompts.filter((prompt) => !prompt.answered).forEach((prompt) => {
    state.prompts.set(prompt.prompt_id, prompt);
  });
  if (!state.activePrompt && state.prompts.size) {
    const prompt = state.prompts.values().next().value;
    openPrompt(prompt);
  }
}

function openPrompt(prompt) {
  state.activePrompt = prompt;
  promptBody.innerHTML = "";
  if (prompt.prompt_type === "name_collision") {
    promptTitle.textContent = "Resolve Collision";
    addText(`Existing: ${prompt.payload.existing.path}`);
    addText(`Candidate: ${prompt.payload.candidate.path}`);
    addSelect("action", [
      ["rename_candidate", "Rename candidate"],
      ["keep_existing", "Keep existing"],
      ["keep_candidate", "Keep candidate"],
      ["cancel", "Cancel run"],
    ]);
  } else if (prompt.prompt_type === "raw_conversion") {
    promptTitle.textContent = "RAW Conversion";
    addText(`Workspace: ${prompt.payload.workspace}`);
    addText(`Assets: ${prompt.payload.asset_count}`);
    addSelect("action", [["continue", "Continue"]]);
  } else {
    promptTitle.textContent = "Unknown Camera";
    addText("Assign a shorthand symbol.");
    addInput("camera_model", "Camera model");
    addInput("symbol", "Symbol");
  }
  promptDialog.showModal();
}

function addText(text) {
  const p = document.createElement("p");
  p.textContent = text;
  promptBody.appendChild(p);
}

function addInput(name, labelText) {
  const label = document.createElement("label");
  label.className = "field";
  label.textContent = labelText;
  const input = document.createElement("input");
  input.name = name;
  input.required = true;
  label.appendChild(input);
  promptBody.appendChild(label);
}

function addSelect(name, options) {
  const label = document.createElement("label");
  label.className = "field";
  label.textContent = "Action";
  const select = document.createElement("select");
  select.name = name;
  options.forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    select.appendChild(option);
  });
  label.appendChild(select);
  promptBody.appendChild(label);
}

promptForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(promptForm);
  const answer = Object.fromEntries(formData.entries());
  const prompt = state.activePrompt;
  await post(`/api/prompts/${prompt.prompt_id}/answer`, answer);
  state.prompts.delete(prompt.prompt_id);
  state.activePrompt = null;
  promptDialog.close();
});

document.querySelector("#cancelPromptBtn").addEventListener("click", () => {
  state.activePrompt = null;
  promptDialog.close();
});

document.querySelector("#startBtn").addEventListener("click", () => post("/api/pipeline/start"));
document.querySelector("#pauseBtn").addEventListener("click", () => post("/api/pipeline/pause"));
document.querySelector("#resumeBtn").addEventListener("click", () => post("/api/pipeline/resume"));
document.querySelector("#stepBtn").addEventListener("click", () => post("/api/pipeline/step"));

function connectEvents() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/events`);
  socket.addEventListener("message", (event) => renderState(JSON.parse(event.data)));
  socket.addEventListener("close", () => setTimeout(connectEvents, 1200));
}

loadGraph()
  .then(() => api("/api/pipeline/state"))
  .then(renderState)
  .then(connectEvents)
  .catch((error) => {
    criticalAlert.textContent = error.message;
    criticalAlert.classList.remove("hidden");
  });
