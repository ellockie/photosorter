import pytest

from src.server import WebDependencyError, create_app


def test_create_app_exposes_fastapi_contract():
    try:
        app = create_app()
    except WebDependencyError:
        pytest.skip("FastAPI dependencies are not installed")

    routes = {
        route.path
        for route in app.routes
    }
    assert "/api/pipeline/state" in routes
    assert "/api/pipeline/graph" in routes
    assert "/api/pipeline/restart" in routes
    assert "/api/config" in routes
