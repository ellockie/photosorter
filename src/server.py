import asyncio
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
    def __init__(self, config_path=None, base_folder=None):
        self.config_path = config_path
        self.base_folder = base_folder
        self.context = PipelineContext(
            config=load_config(config_path, base_folder),
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
                "stage_stats": {
                    key: dict(value)
                    for key, value in self.context.stage_stats.items()
                },
                # A single large run can log ~700 per-file lines; keep enough
                # history that earlier stages stay visible in the dashboard.
                "logs": self.context.logs[-2000:],
                "logs_total": len(self.context.logs),
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

    def run_fresh(self):
        # One-click "Run": re-running a completed pipeline previously needed two
        # clicks (Restart then Start). This resets to a clean context and starts
        # in a single action. A run already in progress is left untouched.
        with self._lock:
            if self.thread is not None and self.thread.is_alive():
                return
            already_ran = bool(self.context.stage_states)
        if already_ran:
            self.restart()
        self.start()

    def restart(self):
        with self._lock:
            if self.thread is not None and self.thread.is_alive():
                raise RuntimeError("Cannot restart while the pipeline is running")
            self.context = PipelineContext(
                config=load_config(self.config_path, self.base_folder),
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


def create_app(config_path=None, base_folder=None):
    require_fastapi()
    runtime = PipelineRuntime(config_path, base_folder)
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

    @app.post("/api/pipeline/run")
    async def pipeline_run():
        runtime.run_fresh()
        payload = {"event": "pipeline_running", "state": runtime.state()}
        await events.broadcast(payload)
        return payload

    @app.post("/api/pipeline/step")
    async def pipeline_step():
        runtime.step()
        payload = {"event": "pipeline_stepped", "state": runtime.state()}
        await events.broadcast(payload)
        return payload

    @app.post("/api/server/shutdown")
    async def server_shutdown():
        # The dashboard "Stop server" button calls this; it signals uvicorn to
        # exit its serve loop, after which the launcher process returns/ends.
        handler = getattr(app.state, "request_shutdown", None)
        if handler is not None:
            handler()
        return {"event": "server_shutdown"}

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
            # The pipeline runs in a background thread that does not broadcast,
            # so stream the runtime state on a short interval and push whenever
            # it changes (new logs, stage transitions, counters, prompts). This
            # is what keeps the dashboard live while a run is in progress.
            previous = None
            while True:
                state = runtime.state()
                signature = (
                    state["running"],
                    state["paused"],
                    state["error"],
                    # Total count, not window length: once the log window is
                    # full its length stops changing while lines keep arriving.
                    state["logs_total"],
                    tuple(sorted(state["stage_states"].items())),
                    tuple(sorted((k, tuple(sorted(v.items()))) for k, v in state["stage_stats"].items())),
                    tuple(sorted(state["counters"].items())),
                    len([p for p in state["prompts"] if not p["answered"]]),
                )
                if signature != previous:
                    previous = signature
                    await websocket.send_json({"event": "state", "state": state})
                await asyncio.sleep(0.4)
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            events.disconnect(websocket)
        finally:
            events.disconnect(websocket)

    return app


def _server_already_running(url: str) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(url + "api/pipeline/state", timeout=0.5) as response:
            return response.status == 200
    except Exception:
        return False


def _open_browser(url: str) -> None:
    # new=0 asks the browser to reuse an existing window where possible, so a
    # second launch surfaces the dashboard instead of piling up tabs.
    import webbrowser

    try:
        webbrowser.open(url, new=0, autoraise=True)
    except Exception:
        pass


def run_server(config_path=None, host=None, port=None, base_folder=None):
    require_fastapi()
    import uvicorn

    config = load_config(config_path, base_folder)
    dashboard = config.get("dashboard", {})
    resolved_host = host or dashboard.get("host", "127.0.0.1")
    resolved_port = port or dashboard.get("port", 8888)
    url = f"http://{resolved_host}:{resolved_port}/"
    open_browser = dashboard.get("open_browser", True)

    # If a dashboard is already serving this port, reuse it rather than failing
    # to bind a second server: the launcher can be re-run safely.
    if _server_already_running(url):
        print(f"Dashboard already running at {url} - reusing it.")
        if open_browser:
            _open_browser(url)
        return

    # Pass the app object directly: the "module:factory" string form cannot
    # forward config_path/base_folder to create_app.
    app = create_app(config_path, base_folder)
    server = uvicorn.Server(uvicorn.Config(app, host=resolved_host, port=resolved_port))
    # The "Stop server" button reaches this to end the serve loop.
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)

    if open_browser:
        # Open once the server is accepting connections.
        threading.Timer(1.0, _open_browser, args=(url,)).start()

    print(f"Dashboard at {url} (Ctrl+C or the Stop server button to quit).")
    server.run()
