import threading
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineMode, \
    PipelinePaused, \
    load_config, \
    save_config
from src.stages import build_default_orchestrator


try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    FastAPI = None
    HTTPException = None
    WebSocket = None
    WebSocketDisconnect = None
    FileResponse = None
    StaticFiles = None


class WebDependencyError(RuntimeError):
    pass


class EventHub:
    def __init__(self):
        self._clients = set()
        self._lock = threading.RLock()

    async def connect(self, websocket):
        await websocket.accept()
        with self._lock:
            self._clients.add(websocket)

    def disconnect(self, websocket):
        with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, payload: dict):
        disconnected = []
        with self._lock:
            clients = list(self._clients)
        for websocket in clients:
            try:
                await websocket.send_json(payload)
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)


class PipelineRuntime:
    def __init__(self, config_path=None):
        self.config_path = config_path
        self.context = PipelineContext(
            config=load_config(config_path),
            mode=PipelineMode.UI,
        )
        self.orchestrator = build_default_orchestrator(PipelineMode.UI)
        self.thread = None
        self.error = None
        self.paused = False
        self._lock = threading.RLock()

    def state(self) -> dict:
        with self._lock:
            return {
                "running": self.thread is not None and self.thread.is_alive(),
                "paused": self.paused,
                "error": str(self.error) if self.error else None,
                "counters": dict(self.context.counters),
                "stage_states": {
                    key: value.value
                    for key, value in self.context.stage_states.items()
                },
                "logs": self.context.logs[-200:],
                "prompts": [
                    {
                        "prompt_id": prompt.prompt_id,
                        "prompt_type": prompt.prompt_type,
                        "payload": prompt.payload,
                        "stage_id": prompt.stage_id,
                        "answered": prompt.answered,
                    }
                    for prompt in self.context.prompt_queue
                ],
            }

    def start(self):
        with self._lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.error = None
            self.paused = False
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self):
        try:
            self.orchestrator.run(self.context)
        except PipelinePaused as error:
            self.paused = True
            self.error = error
        except Exception as error:
            self.error = error

    def pause(self):
        with self._lock:
            self.paused = True

    def resume(self):
        with self._lock:
            self.paused = False

    def step(self):
        self.start()

    def restart(self):
        with self._lock:
            if self.thread is not None and self.thread.is_alive():
                raise RuntimeError("Cannot restart while the pipeline is running")
            self.context = PipelineContext(
                config=load_config(self.config_path),
                mode=PipelineMode.UI,
            )
            self.orchestrator = build_default_orchestrator(PipelineMode.UI)
            self.thread = None
            self.error = None
            self.paused = False

    def answer_prompt(self, prompt_id: str, answer: dict):
        self.context.answer_prompt(prompt_id, answer)
        if answer.get("camera_model") is not None and answer.get("symbol") is not None:
            self.context.config.setdefault("camera_symbols", {})[answer["camera_model"]] = answer["symbol"]
            save_config(self.context.config, self.config_path)


def require_fastapi():
    if FastAPI is None:
        raise WebDependencyError(
            "FastAPI dependencies are not installed. Run Poetry install before launching the dashboard."
        )


def create_app(config_path=None):
    require_fastapi()
    runtime = PipelineRuntime(config_path)
    events = EventHub()
    app = FastAPI(title="photosorter dashboard")
    static_dir = Path(__file__).resolve().parent / "pipeline" / "static"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index():
        index_path = static_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Dashboard static files are missing")
        return FileResponse(index_path)

    @app.get("/api/pipeline/state")
    def pipeline_state():
        return runtime.state()

    @app.get("/api/pipeline/graph")
    def pipeline_graph():
        return runtime.orchestrator.graph()

    @app.post("/api/pipeline/start")
    async def pipeline_start():
        runtime.start()
        payload = {"event": "pipeline_started", "state": runtime.state()}
        await events.broadcast(payload)
        return payload

    @app.post("/api/pipeline/pause")
    async def pipeline_pause():
        runtime.pause()
        payload = {"event": "pipeline_paused", "state": runtime.state()}
        await events.broadcast(payload)
        return payload

    @app.post("/api/pipeline/resume")
    async def pipeline_resume():
        runtime.resume()
        payload = {"event": "pipeline_resumed", "state": runtime.state()}
        await events.broadcast(payload)
        return payload

    @app.post("/api/pipeline/restart")
    async def pipeline_restart():
        try:
            runtime.restart()
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error))
        payload = {"event": "pipeline_restarted", "state": runtime.state()}
        await events.broadcast(payload)
        return payload

    @app.post("/api/pipeline/step")
    async def pipeline_step():
        runtime.step()
        payload = {"event": "pipeline_stepped", "state": runtime.state()}
        await events.broadcast(payload)
        return payload

    @app.get("/api/config")
    def get_config():
        return runtime.context.config

    @app.put("/api/config")
    async def put_config(config: dict):
        runtime.context.config = config
        save_config(config, config_path)
        payload = {"event": "config_saved"}
        await events.broadcast(payload)
        return payload

    @app.post("/api/prompts/{prompt_id}/answer")
    async def answer_prompt(prompt_id: str, answer: dict):
        runtime.answer_prompt(prompt_id, answer)
        payload = {
            "event": "prompt_answered",
            "prompt_id": prompt_id,
            "state": runtime.state(),
        }
        await events.broadcast(payload)
        return payload

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket):
        await events.connect(websocket)
        try:
            await websocket.send_json({"event": "state", "state": runtime.state()})
            while True:
                message = await websocket.receive_json()
                if message.get("type") == "ping":
                    await websocket.send_json({"event": "pong"})
        except WebSocketDisconnect:
            events.disconnect(websocket)

    return app


def run_server(config_path=None, host=None, port=None):
    require_fastapi()
    import uvicorn

    config = load_config(config_path)
    dashboard = config.get("dashboard", {})
    uvicorn.run(
        "src.server:create_app",
        factory=True,
        host=host or dashboard.get("host", "127.0.0.1"),
        port=port or dashboard.get("port", 8888),
    )
