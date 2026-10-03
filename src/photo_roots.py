"""Which photo root a run works on: the one whose INBOX has something in it.

The archive is kept under several roots -- a local disk, a second disk, the
NAS -- listed in config.json as ``photo_roots``, each with the same layout below
it. Any of them can be processed, and processing one is exactly processing it
as ``--base-folder``: its own INBOX, READY, .TMP and archive tree.

Adding a root is adding a line to ``photo_roots``; nothing here names one.
"""

import os
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.core import \
    is_protected, \
    load_config, \
    media_extensions, \
    normalize_suffix, \
    photo_roots, \
    protected_intake_folders

#: An offline network share can stall a lookup for tens of seconds; past this
#: it counts as unreachable.
PROBE_TIMEOUT_S = 5.0


@dataclass
class RootIntake:
    root: Path
    inbox: Path
    #: Media files waiting in the INBOX; None when the root cannot be reached.
    media: int | None
    #: The INBOX is the NAS inbox, which the nas-harvest stage copies into a
    #: local run: never a root to process in place.
    harvested: bool = False

    @property
    def reachable(self) -> bool:
        return self.media is not None


def candidate_roots(config: dict) -> list[Path]:
    """The configured root first, then every other photo root, each once."""
    roots = [Path(config["paths"]["root_folder"])]
    for root in photo_roots(config):
        if root not in roots:
            roots.append(root)
    return roots


def count_inbox_media(config: dict) -> int:
    """How many media files the run on *config*'s root would take in."""
    inbox = Path(config["paths"]["inbox_folder"])
    if not inbox.is_dir():
        return 0
    extensions = media_extensions(config)
    protected = protected_intake_folders(config)
    return sum(
        1
        for path in inbox.rglob("*")
        if normalize_suffix(path.suffix) in extensions
        and not is_protected(path, protected)
        and path.is_file()
    )


def survey_roots(config_path: str | Path | None = None,
                 is_dir: Callable[[Path], bool] = os.path.isdir,
                 timeout: float = PROBE_TIMEOUT_S) -> list[RootIntake]:
    """Every candidate root with its INBOX and what is waiting in it."""
    from src.pipeline_stages.nas_harvest import is_nas_inbox

    base = load_config(config_path)
    configs = {
        root: load_config(config_path, base_folder=root)
        for root in candidate_roots(base)
    }
    probe_pool = ThreadPoolExecutor(max_workers=len(configs))
    probes = {root: probe_pool.submit(is_dir, root) for root in configs}
    done, _ = wait(probes.values(), timeout=timeout)
    # A stalled probe is abandoned, not waited for.
    probe_pool.shutdown(wait=False)
    reachable = [
        root for root, probe in probes.items()
        if probe in done and probe.exception() is None and probe.result()
    ]
    with ThreadPoolExecutor(max_workers=max(len(reachable), 1)) as pool:
        counts = {root: pool.submit(count_inbox_media, configs[root]) for root in reachable}
    return [
        RootIntake(
            root=root,
            inbox=Path(config["paths"]["inbox_folder"]),
            media=counts[root].result() if root in counts else None,
            # Against the configured NAS inbox, not the per-root config's: a
            # run on another root confines ingest paths it was not given.
            harvested=is_nas_inbox(base, config["paths"]["inbox_folder"]),
        )
        for root, config in configs.items()
    ]


def choose_root(intakes: list[RootIntake],
                ask: Callable[[str], str] = input,
                say: Callable[[str], None] = print) -> Path | None:
    """The root to process, asking when more than one INBOX has media.

    With nothing waiting anywhere the configured root -- the first -- is kept.
    None means the user chose not to run.
    """
    for intake in intakes:
        if not intake.reachable:
            say(f"  Photo root not reachable, skipped: {intake.root}")
    for intake in intakes:
        if intake.harvested and intake.media:
            say(f"  {intake.inbox} ({intake.media}) is the NAS inbox: harvested into a "
                "local run, never processed in place")
    waiting = [intake for intake in intakes if intake.media and not intake.harvested]
    if not waiting:
        return intakes[0].root
    if len(waiting) == 1:
        say(f"  Media waiting in {waiting[0].inbox} ({waiting[0].media}) -> root {waiting[0].root}")
        return waiting[0].root

    say("\n  Media is waiting in more than one INBOX. Which one should be processed?")
    for number, intake in enumerate(waiting, start=1):
        say(f"    {number}. {intake.inbox}  ({intake.media} files)")
    while True:
        try:
            answer = ask(f"  Choose 1-{len(waiting)}, or q to quit: ").strip().lower()
        except EOFError:
            return None
        if answer in ("q", "quit"):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(waiting):
            return waiting[int(answer) - 1].root
