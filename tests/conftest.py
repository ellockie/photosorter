"""Session-wide guard: no test may touch the real photo archive.

`default_config()` returns ABSOLUTE real paths — `c:\\__PHOTOS` and the Dropbox
Camera Uploads folder. A test that builds a context from it and runs stages is
not testing anything in isolation: it performs a real ingest, harvesting the
user's photos out of Dropbox and sorting them into the live archive. That has
happened. It must not be possible again.

Two layers, both autouse and session-wide:

1. `PHOTO_BASE_FOLDER` is pointed at a throwaway directory before any test
   imports run, and the hardcoded Camera Uploads paths are patched to sit under
   it, so even a bare `default_config()` is harmless.
2. Every file-mutating primitive in `src.core` refuses to operate outside that
   sandbox, so a path that slips through layer 1 raises instead of moving a
   photo.

Tests that legitimately need a real absolute path (there are none today) would
have to opt out explicitly, which is the point: it should be a visible choice.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Claimed before any test runs, and before anything calls default_config().
_SANDBOX = Path(tempfile.mkdtemp(prefix="photosorter_tests_"))

os.environ["PHOTO_BASE_FOLDER"] = str(_SANDBOX / "__PHOTOS")


def _is_inside_sandbox(path) -> bool:
    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError):
        return False
    if resolved.is_relative_to(_SANDBOX):
        return True
    # pytest's own tmp_path trees are fine: they are per-test scratch space.
    return resolved.is_relative_to(Path(tempfile.gettempdir()).resolve())


class RealArchiveAccess(AssertionError):
    """A test tried to move, rename or delete something outside the sandbox."""


@pytest.fixture(autouse=True, scope="session")
def _sandbox_paths():
    yield
    shutil.rmtree(_SANDBOX, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_real_archive_writes(monkeypatch):
    """Make the file primitives refuse anything outside the sandbox."""
    from src import core

    def guard(name, original, path_arg_count):
        def wrapper(*args, **kwargs):
            for value in args[:path_arg_count]:
                if not _is_inside_sandbox(value):
                    raise RealArchiveAccess(
                        f"{name}() refused: {value!r} is outside the test sandbox. "
                        "Build the config from tmp_path instead of default_config()."
                    )
            return original(*args, **kwargs)
        return wrapper

    for name, path_arg_count in (
        ("safe_move", 2),
        ("safe_rename", 2),
        ("safe_delete", 1),
    ):
        original = getattr(core, name)
        monkeypatch.setattr(core, name, guard(name, original, path_arg_count))

    # Stages import these by name at module import time, so patch the copies
    # they already hold too.
    import importlib
    import pkgutil

    import src.pipeline_stages as stages_package

    for module_info in pkgutil.iter_modules(stages_package.__path__):
        module = importlib.import_module(f"src.pipeline_stages.{module_info.name}")
        for name in ("safe_move", "safe_rename", "safe_delete"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, getattr(core, name))
    yield


@pytest.fixture
def sandbox_root() -> Path:
    """The session sandbox, for tests that want the re-rooted default config."""
    return _SANDBOX
