import asyncio
import threading
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineMode, \
    PipelinePaused, \
    load_config, \
    save_config
from src.pipeline_stages.screenshot_grouping import \
    grouper_install, \
    launch_grouper
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
        # The grouper GUI opened from a grouping-review prompt, if any: it
        # cannot run on the pipeline thread, which is parked in await_prompt
        # waiting for that very prompt to be answered.
        self.grouper_thread = None
        self.error = None
        self.paused = False
        self._lock = threading.RLock()

    def state(self) -> dict:
        with self._lock:
            return {
                "running": self.thread is not None and self.thread.is_alive(),
                "paused": self.paused,
                # The prompt a stage is blocked on, if any. A run waiting on the
                # user is still "running" — this is what lets the dashboard say
                # so instead of looking stalled.
                "waiting_for": self.context.waiting_prompt_id,
                # A grouper window opened from the review prompt is blocking
                # the user, not the server: the dashboard uses this to keep the
                # prompt's own buttons out of reach until it is closed.
                "grouper_running": self._grouper_busy(),
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
            self.context.clear_abort()
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
        # A run blocked on a prompt would otherwise wait forever by design, so
        # Pause is the escape hatch: it releases the wait and the stage ends as
        # paused. Everything already done on disk stays done.
        with self._lock:
            self.paused = True
        self.context.request_abort()

    def resume(self):
        with self._lock:
            self.paused = False
        self.context.clear_abort()

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

    def _grouper_busy(self) -> bool:
        thread = self.grouper_thread
        return thread is not None and thread.is_alive()

    def pending_prompt(self, prompt_id: str):
        """The unanswered prompt with this id, or None."""
        with self._lock:
            for prompt in self.context.prompt_queue:
                if prompt.prompt_id == prompt_id and not prompt.answered:
                    return prompt
        return None

    def open_grouper(self, prompt_id: str) -> list[str]:
        """Re-open the grouper GUI on the folders a grouping-review prompt lists.

        The review prompt exists precisely because those folders still need
        naming, and the grouper is the tool for it — so offer it there rather
        than making the user find the folders in Explorer and start the GUI by
        hand. It runs on its own thread: the pipeline thread is blocked in
        `await_prompt`, and the dashboard has to keep streaming while the
        windows are open.

        The folders come from the payload the server itself wrote when it
        raised the prompt, never from the request, so this cannot be pointed at
        an arbitrary path. Returns the folders it is opening.
        """
        prompt = self.pending_prompt(prompt_id)
        if prompt is None:
            raise LookupError(f"No pending prompt {prompt_id}")
        if prompt.prompt_type != "grouping_review":
            raise ValueError(f"A {prompt.prompt_type} prompt has no folders to group")
        with self._lock:
            if self._grouper_busy():
                raise RuntimeError("The grouper is already open")
            install = grouper_install(self.context.config.get("screenshot_grouping", {}))
            if install is None:
                raise RuntimeError(
                    "The screenshot grouper is not installed on this machine "
                    "(check screenshot_grouping.python and .project_path)"
                )
            # A folder renamed since the prompt was raised is already done;
            # what is left under the recorded name is exactly what still needs
            # the GUI.
            folders = [Path(path) for path in prompt.payload.get("folders", [])]
            folders = [folder for folder in folders if folder.is_dir()]
            if not folders:
                raise RuntimeError(
                    "None of those folders are still on disk under that name - "
                    "press Re-scan"
                )
            self.grouper_thread = threading.Thread(
                target=self._run_grouper,
                args=(folders, *install),
                daemon=True,
            )
            self.grouper_thread.start()
        return [str(folder) for folder in folders]

    def _run_grouper(self, folders, python_exe, project_path):
        self.context.log(
            f"Re-opening the grouper on {len(folders)} folder(s) from the review"
        )
        for folder in folders:
            # An earlier window in this same batch may have renamed this one
            # (the grouper splits a day into new folders and removes the old).
            if not folder.is_dir():
                self.context.log(f"Skipping {folder.name}: no longer under that name")
                continue
            launch_grouper(self.context, folder, python_exe, project_path)
        self.context.log("Grouper closed - press Re-scan when the folders are named")

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

    @app.middleware("http")
    async def no_cache_headers(request, call_next):
        # This is a single-user local dev dashboard whose static files change
        # frequently; browsers otherwise cache index.html/app.js/app.css
        # across plain reloads and silently keep serving stale UI.
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

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

    @app.post("/api/prompts/{prompt_id}/regroup")
    async def regroup_prompt(prompt_id: str):
        try:
            folders = runtime.open_grouper(prompt_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error))
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=409, detail=str(error))
        payload = {
            "event": "grouper_launched",
            "prompt_id": prompt_id,
            "folders": folders,
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
                    state["waiting_for"],
                    state["grouper_running"],
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
