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
