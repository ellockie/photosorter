"""Where the external grouper lives, and how it is invoked.

The GUI that splits a day into named sub-events is a separate project
(``screenshot_grouping.project_path`` in config.json), run out of its own
virtualenv (``screenshot_grouping.python``). Three callers open it:

* ``ScreenshotGroupingStage`` -- during a pipeline run, on the folders that
  run sorted into;
* ``src/server.py`` -- from the dashboard's grouping-review prompt;
* ``tools/restructure_archive.py`` -- over an existing archive, on every
  folder still carrying the ``__TO_SPLIT__`` marker.

What counts as "installed", and the exact command line, therefore has to be
one definition rather than three, the same way the name grammars are
(``ARCHIVE_STANDARD.md``, rule T8).

This is a **leaf module**: it imports nothing from the project, so the
maintenance tool can load it by file path without dragging the whole pipeline
-- exiftool, the dashboard, the converters -- in behind it. Importing
``src.pipeline_stages.screenshot_grouping`` instead would run that package's
``__init__``, which imports every stage.
"""

import subprocess
from pathlib import Path

# The entry point inside the grouper project. Its presence is also what says
# the project path points at the grouper and not at some other folder.
GROUPER_ENTRY_POINT = "main.py"


def grouper_install(settings: dict) -> tuple[Path, Path] | None:
    """``(python_exe, project_path)`` of the external grouper, or None.

    ``settings`` is the ``screenshot_grouping`` block of the config. Both
    halves have to be on disk: a virtualenv without the project, or a project
    path with no ``main.py`` in it, is not an installation.
    """
    python_exe = Path(settings.get("python", ""))
    project_path = Path(settings.get("project_path", ""))
    if not python_exe.is_file() or not (project_path / GROUPER_ENTRY_POINT).is_file():
        return None
    return python_exe, project_path


def grouper_command(python_exe: Path, project_path: Path, folder: Path) -> list[str]:
    """The argument vector that opens the grouper on one folder.

    A list, never a string, and every caller runs it with ``shell=False``: a
    folder name is archive data, and an event somebody labelled with an
    ampersand must reach the GUI as a name rather than as a shell operator.
    """
    return [str(python_exe), str(project_path / GROUPER_ENTRY_POINT), str(folder)]


def stderr_tail(stderr: str | None, limit: int = 5) -> list[str]:
    """The last few non-empty stderr lines, for the failure log.

    The bare exit code says nothing about what went wrong -- the grouper's own
    message (an argparse usage error, a traceback) only reaches its stderr.
    """
    if not stderr:
        return []
    lines = [line.rstrip() for line in stderr.splitlines() if line.strip()]
    return lines[-limit:]


def run_grouper(python_exe: Path, project_path: Path, folder: Path):
    """Open the GUI on one folder, blocking until its window closes.

    Returns the ``CompletedProcess``. Raises ``OSError`` if the interpreter
    could not be started at all; every caller decides for itself whether that
    ends the batch.
    """
    return subprocess.run(
        grouper_command(python_exe, project_path, folder),
        cwd=str(project_path),
        stderr=subprocess.PIPE,
        text=True,
    )
