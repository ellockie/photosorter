import json

import pytest

from src.server import WebDependencyError, create_app

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


@pytest.fixture
def client(tmp_path):
    config = {
        "paths": {
            "root_folder": str(tmp_path / "PHOTOS"),
        },
        "dashboard": {"open_browser": False},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    app = create_app(config_path=str(config_path))
    return TestClient(app)


def test_create_app_exposes_fastapi_contract(tmp_path):
    try:
        app = create_app()
    except WebDependencyError:
        pytest.fail("FastAPI must be installed in the test environment")

    routes = {
        route.path
        for route in app.routes
    }
    assert "/api/pipeline/state" in routes
    assert "/api/pipeline/graph" in routes
    assert "/api/pipeline/restart" in routes
    assert "/api/pipeline/run" in routes
    assert "/api/server/shutdown" in routes
    assert "/api/config" in routes


def test_state_endpoint_payload_schema(client):
    response = client.get("/api/pipeline/state")
    assert response.status_code == 200
    state = response.json()
    for key in ("running", "paused", "waiting_for", "error", "counters", "stage_states", "logs", "prompts"):
        assert key in state
    assert state["running"] is False
    # No stage is blocked on a prompt on a fresh runtime.
    assert state["waiting_for"] is None
    assert isinstance(state["counters"], dict)
    assert isinstance(state["prompts"], list)


def test_graph_endpoint_returns_default_dag(client):
    response = client.get("/api/pipeline/graph")
    assert response.status_code == 200
    nodes = response.json()["nodes"]
    node_ids = [node["id"] for node in nodes]
    assert "initialization" in node_ids
    assert "safety-validation" in node_ids
    for node in nodes:
        assert set(node) >= {"id", "label", "dependencies", "headless"}


def test_pause_resume_and_restart_controls(client):
    assert client.post("/api/pipeline/pause").json()["state"]["paused"] is True
    assert client.post("/api/pipeline/resume").json()["state"]["paused"] is False
    response = client.post("/api/pipeline/restart")
    assert response.status_code == 200
    assert response.json()["event"] == "pipeline_restarted"


def test_run_endpoint_starts_pipeline_in_one_call(client):
    response = client.post("/api/pipeline/run")
    assert response.status_code == 200
    assert response.json()["event"] == "pipeline_running"


def test_server_shutdown_endpoint_invokes_handler():
    app = create_app()
    triggered = {"called": False}
    app.state.request_shutdown = lambda: triggered.__setitem__("called", True)
    response = TestClient(app).post("/api/server/shutdown")
    assert response.status_code == 200
    assert response.json()["event"] == "server_shutdown"
    assert triggered["called"] is True


def test_config_roundtrip_persists_to_file(client, tmp_path):
    config = client.get("/api/config").json()
    assert config["paths"]["root_folder"].startswith(str(tmp_path))

    config["camera_symbols"]["Test Camera"] = "TSTC"
    response = client.put("/api/config", json=config)
    assert response.status_code == 200

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["camera_symbols"]["Test Camera"] == "TSTC"


def test_prompt_answer_route_and_camera_mapping_persistence(client, tmp_path):
    response = client.post(
        "/api/prompts/abc123/answer",
        json={"camera_model": "Canon EOS Test", "symbol": "CTST"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["event"] == "prompt_answered"
    assert payload["prompt_id"] == "abc123"

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["camera_symbols"]["Canon EOS Test"] == "CTST"


def test_websocket_streams_state_events(client):
    # The socket streams runtime state; the first frame is the current state.
    with client.websocket_connect("/ws/events") as websocket:
        message = websocket.receive_json()
        assert message["event"] == "state"
        assert "stage_states" in message["state"]


def grouper_prompt(client, folders):
    """Raise a grouping-review prompt on the running app's context."""
    runtime = _runtime(client)
    return runtime.context.create_prompt(
        "grouping_review",
        {"round": 1,
         "folders": [str(folder) for folder in folders],
         "names": [folder.name for folder in folders]},
        "grouping-review",
    )


def _runtime(client):
    # The runtime is a closure inside create_app; the routes hold the only
    # reference, so reach it through one of them.
    for route in client.app.routes:
        closure = getattr(getattr(route, "endpoint", None), "__closure__", None) or ()
        for cell in closure:
            if type(cell.cell_contents).__name__ == "PipelineRuntime":
                return cell.cell_contents
    raise AssertionError("PipelineRuntime not reachable from the app routes")


def install_grouper(client, tmp_path):
    python = tmp_path / "venv" / "python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    project = tmp_path / "grouper-project"
    project.mkdir(exist_ok=True)
    (project / "main.py").write_text("", encoding="utf-8")
    _runtime(client).context.config["screenshot_grouping"] = {
        "enabled": True, "python": str(python), "project_path": str(project),
    }
    return python, project


def test_regroup_opens_the_grouper_on_the_prompt_folders(client, tmp_path, monkeypatch):
    import subprocess

    python, project = install_grouper(client, tmp_path)
    folder = tmp_path / "PHOTOS" / "2026-07-18_(Sat) - __TO_SPLIT__(i=3)"
    folder.mkdir(parents=True)
    prompt = grouper_prompt(client, [folder])

    calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kwargs: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    response = client.post(f"/api/prompts/{prompt.prompt_id}/regroup")
    assert response.status_code == 200
    payload = response.json()
    assert payload["event"] == "grouper_launched"
    assert payload["folders"] == [str(folder)]

    _runtime(client).grouper_thread.join(timeout=5)
    assert calls == [[str(python), str(project / "main.py"), str(folder)]]
    # The prompt is still pending: the user answers Re-scan themselves.
    assert prompt.answered is False


def test_regroup_rejects_unknown_and_non_review_prompts(client, tmp_path):
    install_grouper(client, tmp_path)
    assert client.post("/api/prompts/nope/regroup").status_code == 404

    other = _runtime(client).context.create_prompt("unknown_camera", {}, "stamps")
    assert client.post(f"/api/prompts/{other.prompt_id}/regroup").status_code == 409


def test_regroup_reports_folders_that_are_already_renamed(client, tmp_path):
    install_grouper(client, tmp_path)
    gone = tmp_path / "PHOTOS" / "2026-07-18_(Sat) - __TO_SPLIT__(i=3)"
    prompt = grouper_prompt(client, [gone])

    response = client.post(f"/api/prompts/{prompt.prompt_id}/regroup")
    assert response.status_code == 409
    assert "Re-scan" in response.json()["detail"]


def test_regroup_without_the_grouper_installed_is_refused(client, tmp_path):
    folder = tmp_path / "PHOTOS" / "2026-07-18_(Sat) - __TO_SPLIT__(i=3)"
    folder.mkdir(parents=True)
    prompt = grouper_prompt(client, [folder])

    response = client.post(f"/api/prompts/{prompt.prompt_id}/regroup")
    assert response.status_code == 409
    assert "not installed" in response.json()["detail"]


def test_state_reports_whether_the_grouper_is_open(client):
    assert client.get("/api/pipeline/state").json()["grouper_running"] is False


def test_regroup_refuses_a_second_launch_while_the_grouper_is_open(client, tmp_path, monkeypatch):
    import subprocess
    import threading

    install_grouper(client, tmp_path)
    folder = tmp_path / "PHOTOS" / "2026-07-18_(Sat) - __TO_SPLIT__(i=3)"
    folder.mkdir(parents=True)
    prompt = grouper_prompt(client, [folder])

    close_the_window = threading.Event()
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kwargs: close_the_window.wait(5) and None
        or subprocess.CompletedProcess(cmd, 0))

    assert client.post(f"/api/prompts/{prompt.prompt_id}/regroup").status_code == 200
    assert client.get("/api/pipeline/state").json()["grouper_running"] is True

    second = client.post(f"/api/prompts/{prompt.prompt_id}/regroup")
    assert second.status_code == 409
    assert "already open" in second.json()["detail"]

    close_the_window.set()
    _runtime(client).grouper_thread.join(timeout=5)
    assert client.get("/api/pipeline/state").json()["grouper_running"] is False
