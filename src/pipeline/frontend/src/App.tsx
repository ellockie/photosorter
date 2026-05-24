import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import "./style.css";

type PipelineNode = {
  id: string;
  label: string;
  dependencies: string[];
};

type PipelineState = {
  running?: boolean;
  paused?: boolean;
  error?: string | null;
  counters?: Record<string, number>;
  stage_states?: Record<string, string>;
  logs?: string[];
  prompts?: unknown[];
};

function renderLogLine(line: string) {
  const parts = line.split(/(<\/?b>)/g);
  let bold = false;
  return parts
    .filter((part) => part !== "")
    .map((part, index) => {
      if (part === "<b>") {
        bold = true;
        return null;
      }
      if (part === "</b>") {
        bold = false;
        return null;
      }
      return bold ? <b key={index}>{part}</b> : <React.Fragment key={index}>{part}</React.Fragment>;
    });
}

function App() {
  const [graph, setGraph] = useState<PipelineNode[]>([]);
  const [state, setState] = useState<PipelineState>({});

  useEffect(() => {
    fetch("/api/pipeline/graph")
      .then((response) => response.json())
      .then((payload) => setGraph(payload.nodes || []));
    fetch("/api/pipeline/state")
      .then((response) => response.json())
      .then(setState);

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/events`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.state) setState(payload.state);
    };
    return () => socket.close();
  }, []);

  const nodes = graph.map((node, index) => ({
    id: node.id,
    data: { label: `${node.label}\n${state.stage_states?.[node.id] || "pending"}` },
    position: { x: 80, y: index * 96 },
    className: state.stage_states?.[node.id] || "pending",
  }));
  const edges = graph.flatMap((node) =>
    node.dependencies.map((dependency) => ({
      id: `${dependency}-${node.id}`,
      source: dependency,
      target: node.id,
    })),
  );

  return (
    <main className="app">
      <header>
        <div>
          <h1>photosorter</h1>
          <p>{state.error || (state.running ? "Running" : "Idle")}</p>
        </div>
        <nav>
          <button onClick={() => fetch("/api/pipeline/start", { method: "POST" })}>Start</button>
          <button onClick={() => fetch("/api/pipeline/pause", { method: "POST" })}>Pause</button>
          <button onClick={() => fetch("/api/pipeline/resume", { method: "POST" })}>Resume</button>
          <button onClick={() => fetch("/api/pipeline/restart", { method: "POST" })}>Restart</button>
        </nav>
      </header>
      {state.error && <section className="alert">{state.error}</section>}
      <section className="layout">
        <div className="graph">
          <ReactFlow nodes={nodes} edges={edges} fitView>
            <Background />
            <Controls />
          </ReactFlow>
        </div>
        <aside>
          <dl>
            <dt>Assets</dt>
            <dd>{state.counters?.assets || state.counters?.input_files || 0}</dd>
            <dt>Processed</dt>
            <dd>{state.counters?.sorted_assets || 0}</dd>
            <dt>Prompts</dt>
            <dd>{state.prompts?.length || 0}</dd>
          </dl>
          <h2>Logs</h2>
          <ol>{(state.logs || []).slice(-80).map((line, index) => <li key={`${index}-${line}`}>{renderLogLine(line)}</li>)}</ol>
        </aside>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
