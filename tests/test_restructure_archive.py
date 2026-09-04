"""The restructuring front door: the eight steps, the target rules, the guards.

Every test here passes an explicit target under ``tmp_path``. The tool's
default target is the real archive (``c:\\__PHOTOS\\2026``) and step 1 renames
with bare ``os.rename``, so it is not covered by the ``src.core`` sandbox guard
in conftest: a test that omitted the target would restructure the live archive.

The grouper is faked with the running interpreter and a ``main.py`` that
appends the folder it was handed to a log, so the launch path is exercised for
real -- argument vector, working directory, exit code -- without a GUI.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL_PATH = Path(__file__).resolve().parent.parent / "tools" / "restructure_archive.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("restructure_archive", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def make_archive(tmp_path, *, year="2026", ingest=True):
    """A root holding one year tree, and the out-of-scope entries beside it."""
    root = tmp_path / "__PHOTOS_BACKUP"
    month = root / year / "07. July"
    month.mkdir(parents=True)
    if ingest:
        inbox = root / "____INGEST_PIPELINE" / "INBOX"
        inbox.mkdir(parents=True)
        (inbox / "2026-07-19__21.29.04.jpg").write_bytes(b"x")
    return root


def make_event(root, name, year="2026", images=1):
    folder = root / year / "07. July" / name
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(images):
        (folder / ("2026-07-15_(Wed)_08.14.0%d__f1.7.jpg" % index)).write_bytes(b"x")
    return folder


@pytest.fixture
def fake_grouper(tmp_path):
    """An installation the tool will accept, that records what it was opened on.

    ``sys.executable`` stands in for the grouper's virtualenv, so the launch is
    a real subprocess: if the argument vector or the working directory were
    wrong, the log would come back wrong or empty.
    """
    project = tmp_path / "grouper-project"
    project.mkdir()
    log = tmp_path / "opened.log"
    (project / "main.py").write_text(
        "import sys\n"
        "open(%r, 'a', encoding='utf-8').write(sys.argv[1] + '\\n')\n"
        % str(log),
        encoding="utf-8")
    return {"python": sys.executable, "project_path": str(project),
            "max_folders": 0, "_log": log}


def opened_folders(fake_grouper):
    log = fake_grouper["_log"]
    if not log.is_file():
        return []
    return [Path(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def config(monkeypatch, fake_grouper):
    """Point the tool's config reader at the fake grouper, not config.json."""
    settings = {"screenshot_grouping": fake_grouper,
                "paths": {"root_folder": "c:\\__PHOTOS"},
                "retry": {"attempts": 1, "delay_seconds": 0},
                # Step 1 needs these to count a folder's media and date it from
                # its earliest file; without them every folder looks empty.
                "extensions": {"lossy_images": [".jpg", ".jpeg"],
                               "other_images": [".png"],
                               "raw_images": [".cr2"],
                               "videos": [".mp4", ".mov"],
                               "sidecars": ["._exif"]},
                "legacy": {"date_folder_suffix": " - 1. ######",
                           "day_boundary_time": "04.44.44"},
                # Existing reconciliation tests isolate matching/moving. Tests
                # for the new ExifTool repair explicitly enable this pass.
                "raw_sidecar_generation": {"enabled": False}}
    monkeypatch.setattr(tool.canonicalise, "_config", lambda: settings)
    return settings


def run(*argv):
    return tool.main(list(argv))


# --------------------------------------------------------------------------
# Target resolution
# --------------------------------------------------------------------------

def test_a_target_that_is_not_an_archive_is_refused(tmp_path, config, capsys):
    plain = tmp_path / "holiday snaps"
    plain.mkdir()
    assert run(str(plain), "--apply", "--yes") == 2
    assert "does not look like an archive" in capsys.readouterr().out


def test_force_target_overrides_the_archive_check(tmp_path, config):
    plain = tmp_path / "holiday snaps"
    plain.mkdir()
    assert run(str(plain), "--force-target", "--steps", "1") == 0


def test_a_missing_target_is_an_error(tmp_path, config, capsys):
    assert run(str(tmp_path / "nowhere"), "--steps", "1") == 2
    assert "not a folder" in capsys.readouterr().out


def make_junction(link, target):
    """A Windows junction, or None where one cannot be made.

    Junctions need no elevation, unlike symlinks, which is why they are the
    reparse point a share is realistically booby-trapped with.
    """
    if os.name != "nt":
        return None
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True)
    return link if result.returncode == 0 else None


def test_a_junction_target_is_refused(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    link = make_junction(tmp_path / "link", root)
    if link is None:
        pytest.skip("junctions cannot be created here")
    # The trap this closes: a junction is not a symlink on Windows, so both
    # Path.is_symlink() and os.path.islink() say False for one.
    assert not Path(link).is_symlink()
    assert not os.path.islink(str(link))
    assert tool.path_is_reparse_point(Path(link))
    assert run(str(link), "--steps", "1", "--apply", "--yes") == 2
    assert "reparse point" in capsys.readouterr().out


def test_a_folder_inside_a_year_tree_is_an_archive(tmp_path, config):
    root = make_archive(tmp_path)
    assert tool.looks_like_an_archive(root / "2026" / "07. July")


def test_an_archive_root_is_restricted_to_its_year_trees(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    (root / "2019").mkdir()
    trees = tool.scan_roots(root, lambda key, message: None)
    assert [path.name for path in trees] == ["2019", "2026"]
    # The ingest pipeline holds files still in flight (ARCHIVE_STANDARD P1).
    assert all("INGEST" not in str(path) for path in trees)


def test_a_year_folder_is_its_own_only_tree(tmp_path, config):
    root = make_archive(tmp_path)
    assert tool.scan_roots(root / "2026", lambda key, message: None) == [root / "2026"]


def test_explicit_year_descends_into_an_explicitly_named_root(tmp_path, config):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed) - 1. ######")
    parser_args = tool.build_parser().parse_args([str(root), "--year", "2026"])
    parser_args.year_given = True
    target, error = tool.resolve_run_target(parser_args, lambda key, message: None)
    assert error is None
    assert target == root / "2026"


def test_default_year_does_not_redirect_a_named_target(tmp_path, config):
    root = make_archive(tmp_path)
    parser_args = tool.build_parser().parse_args([str(root)])
    parser_args.year_given = False
    target, error = tool.resolve_run_target(parser_args, lambda key, message: None)
    assert error is None
    assert target == root


# --------------------------------------------------------------------------
# Finding the folders to group
# --------------------------------------------------------------------------

def make_run(root, config_settings, **overrides):
    argv = [str(root)] + list(overrides.pop("argv", []))
    args = tool.build_parser().parse_args(argv)
    args.year_given = False
    for key, value in overrides.items():
        setattr(args, key, value)
    if args.max_folders is None:
        args.max_folders = 0
    trees = tool.scan_roots(root, lambda key, message: None)
    return tool.Run(args, root, trees, colour=False)


def test_marked_folders_are_found_oldest_day_first(tmp_path, config):
    root = make_archive(tmp_path)
    later = make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    earlier = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    make_event(root, "2026-07-16_(Thu)__10.00.00 - Sopot weekend")
    assert tool.find_to_split_folders(make_run(root, config)) == [earlier, later]


def test_nested_marked_folders_are_found_too(tmp_path, config):
    root = make_archive(tmp_path)
    parent = make_event(root, "2026-07-15_(Wed)__08.14.02 - Sopot weekend")
    child = parent / "2026-07-15_(Wed)__09.00.00 - __TO_SPLIT__(i=1)"
    child.mkdir()
    assert tool.find_to_split_folders(make_run(root, config)) == [child]


def test_the_ingest_pipeline_is_never_scanned(tmp_path, config):
    root = make_archive(tmp_path)
    stray = root / "____INGEST_PIPELINE" / "2026-07-15_(Wed) - __TO_SPLIT__(i=1)"
    stray.mkdir(parents=True)
    assert tool.find_to_split_folders(make_run(root, config)) == []


def test_list_to_split_prints_and_stops(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--list-to-split") == 1
    out = capsys.readouterr().out
    assert str(folder) in out
    assert "1 folder(s) carry" in out


# --------------------------------------------------------------------------
# Is there a point in opening this folder at all?
# --------------------------------------------------------------------------

def test_top_level_media_counts_only_the_top_level(tmp_path, config):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)", images=2)
    (folder / "clip.mp4").write_bytes(b"x")
    # Neither of these is in front of the reviewer.
    (folder / "__RAW").mkdir()
    (folder / "__RAW" / "orig.cr2").write_bytes(b"x")
    (folder / "shot._exif").write_text("", encoding="utf-8")
    settings = make_run(root, config).grouping_settings
    assert tool.top_level_media(folder, settings) == (2, 1)


def test_a_folder_emptied_into_subfolders_is_not_worth_opening(tmp_path, config):
    """The video-only day: named "(v=3)" from the subtree, showing nothing."""
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(v=3)", images=0)
    videos = folder / "__VIDEOS"
    videos.mkdir()
    for index in range(3):
        (videos / ("clip_%d.mp4" % index)).write_bytes(b"x")
    run_object = make_run(root, config)
    counted, passed_over = tool.partition_groupable([folder], run_object)
    assert counted == []
    assert [path for path, _reason in passed_over] == [folder]
    assert "top level" in passed_over[0][1]


def test_a_top_level_video_is_worth_opening(tmp_path, config):
    """The grouper's grid is "every image and video", so v-only is real work."""
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(v=2)", images=0)
    for index in range(2):
        (folder / ("clip_%d.mp4" % index)).write_bytes(b"x")
    counted, passed_over = tool.partition_groupable([folder], make_run(root, config))
    assert counted == [(folder, 0, 2)]
    assert passed_over == []


def test_an_empty_marked_folder_is_not_worth_opening(tmp_path, config):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__00.00.00 - __TO_SPLIT__(EMPTY)",
                        images=0)
    counted, passed_over = tool.partition_groupable([folder], make_run(root, config))
    assert counted == []
    assert len(passed_over) == 1


def test_sidecars_alone_are_not_worth_opening(tmp_path, config):
    """A day whose photos left without their sidecars: "._exif" is not media."""
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__06.19.06 - __TO_SPLIT__(e=2)",
                        images=0)
    for index in range(2):
        (folder / ("shot_%d.jpg._exif" % index)).write_text("", encoding="utf-8")
    counted, passed_over = tool.partition_groupable([folder], make_run(root, config))
    assert counted == []
    assert len(passed_over) == 1


def test_open_all_overrides_the_check(tmp_path, config):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__00.00.00 - __TO_SPLIT__(EMPTY)",
                        images=0)
    run_object = make_run(root, config, argv=["--open-all"])
    counted, passed_over = tool.partition_groupable([folder], run_object)
    assert counted == [(folder, 0, 0)]
    assert passed_over == []


def test_showless_folders_are_never_opened(tmp_path, config, fake_grouper, capsys):
    root = make_archive(tmp_path)
    worth = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    empty = make_event(root, "2026-07-18_(Sat)__00.00.00 - __TO_SPLIT__(EMPTY)",
                       images=0)
    assert run(str(root), "--steps", "3", "--apply", "--yes") == 0
    assert opened_folders(fake_grouper) == [worth]
    out = capsys.readouterr().out
    assert "nothing for the grouper to show" in out
    assert empty.name in out                  # said out loud, not dropped


def test_every_marked_folder_showless_is_success_and_opens_nothing(
        tmp_path, config, fake_grouper, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__00.00.00 - __TO_SPLIT__(EMPTY)", images=0)
    assert run(str(root), "--steps", "3", "--apply", "--yes") == 0
    assert opened_folders(fake_grouper) == []
    assert "all 1 marked folder(s) have an empty top level" in capsys.readouterr().out


def test_a_folder_an_earlier_window_emptied_is_skipped(tmp_path, config,
                                                       fake_grouper, capsys):
    """Splitting a day moves its files down; the batch must notice mid-run."""
    root = make_archive(tmp_path)
    first = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    second = make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    real_run_grouper = tool.grouper.run_grouper

    def empty_the_second(python_exe, project_path, folder):
        if folder == first:
            sub = second / "2026-07-18_(Sat)__09.00.00 - Pier"
            sub.mkdir()
            for path in [p for p in second.iterdir() if p.is_file()]:
                path.rename(sub / path.name)
        return real_run_grouper(python_exe, project_path, folder)

    tool.grouper.run_grouper = empty_the_second
    try:
        assert run(str(root), "--steps", "3", "--apply", "--yes") == 0
    finally:
        tool.grouper.run_grouper = real_run_grouper
    assert opened_folders(fake_grouper) == [first]
    assert "nothing left at its top level" in capsys.readouterr().out


def test_list_to_split_separates_the_two(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    worth = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    make_event(root, "2026-07-18_(Sat)__00.00.00 - __TO_SPLIT__(EMPTY)", images=0)
    assert run(str(root), "--list-to-split") == 1
    out = capsys.readouterr().out
    assert ("%s  [i=1 v=0]" % worth) in out
    assert "2 folder(s) carry the __TO_SPLIT__ marker; 1 worth opening." in out


# --------------------------------------------------------------------------
# Step 3 -- launching the grouper
# --------------------------------------------------------------------------

def test_dry_run_lists_the_folders_and_opens_nothing(tmp_path, config, fake_grouper,
                                                    capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "3") == 1
    assert "the grouper was not opened" in capsys.readouterr().out
    assert opened_folders(fake_grouper) == []


def test_apply_opens_every_marked_folder_one_at_a_time(tmp_path, config,
                                                       fake_grouper):
    root = make_archive(tmp_path)
    first = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    second = make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "3", "--apply", "--yes") == 0
    assert opened_folders(fake_grouper) == [first, second]


def test_a_folder_an_earlier_window_renamed_is_skipped(tmp_path, config,
                                                       fake_grouper, capsys):
    root = make_archive(tmp_path)
    first = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    second = make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    # What the GUI does to a day it splits: the folder is gone by the time the
    # batch reaches it.
    (root / "grouper-stand-in").mkdir()

    real_run_grouper = tool.grouper.run_grouper

    def rename_the_second(python_exe, project_path, folder):
        if folder == first:
            second.rename(second.with_name("2026-07-18_(Sat)__09.00.00 - Pier"))
        return real_run_grouper(python_exe, project_path, folder)

    tool.grouper.run_grouper = rename_the_second
    try:
        assert run(str(root), "--steps", "3", "--apply", "--yes") == 0
    finally:
        tool.grouper.run_grouper = real_run_grouper
    assert opened_folders(fake_grouper) == [first]
    assert "no longer under that name" in capsys.readouterr().out


def test_max_folders_limits_the_batch(tmp_path, config, fake_grouper, capsys):
    root = make_archive(tmp_path)
    first = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "3", "--apply", "--yes", "--max-folders", "1") == 0
    assert opened_folders(fake_grouper) == [first]
    assert "limiting this run" in capsys.readouterr().out


def test_a_grouper_that_fails_does_not_end_the_batch(tmp_path, config,
                                                     fake_grouper, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    second = make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    Path(fake_grouper["project_path"], "main.py").write_text(
        "import sys\n"
        "open(%r, 'a', encoding='utf-8').write(sys.argv[1] + '\\n')\n"
        "sys.stderr.write('boom\\n')\n"
        "sys.exit(3)\n" % str(fake_grouper["_log"]),
        encoding="utf-8")
    assert run(str(root), "--steps", "3", "--apply", "--yes") == 1
    assert len(opened_folders(fake_grouper)) == 2
    out = capsys.readouterr().out
    assert "exited with code 3" in out
    assert "boom" in out                      # the stderr tail, not just the code
    assert str(second) in "\n".join(str(path) for path in opened_folders(fake_grouper))


def test_a_missing_grouper_stops_the_grouping_step(tmp_path, config, capsys):
    config["screenshot_grouping"] = {"python": "", "project_path": ""}
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "3", "--apply", "--yes") == 2
    assert "not installed" in capsys.readouterr().out


def test_a_grouper_on_the_network_is_refused(tmp_path, config, fake_grouper,
                                             monkeypatch, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    project = Path(fake_grouper["project_path"])
    monkeypatch.setattr(tool.canonicalise, "drive_is_network",
                        lambda path: Path(path) == project)
    assert run(str(root), "--steps", "3", "--apply", "--yes") == 2
    assert "network location" in capsys.readouterr().out


def test_allow_network_tool_overrides_that(tmp_path, config, fake_grouper,
                                           monkeypatch):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    project = Path(fake_grouper["project_path"])
    monkeypatch.setattr(tool.canonicalise, "drive_is_network",
                        lambda path: Path(path) == project)
    assert run(str(root), "--steps", "3", "--apply", "--yes",
               "--allow-network-tool") == 0
    assert opened_folders(fake_grouper) == [folder]


def test_nothing_to_group_is_success(tmp_path, config, fake_grouper):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - Sopot weekend")
    assert run(str(root), "--steps", "3", "--apply", "--yes") == 0
    assert opened_folders(fake_grouper) == []


# --------------------------------------------------------------------------
# Confirmation
# --------------------------------------------------------------------------

def test_applying_with_no_terminal_and_no_yes_is_refused(tmp_path, config,
                                                         fake_grouper, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    # pytest captures stdin, so isatty() is already False: this is the
    # unattended case, and without --yes it must not proceed.
    assert run(str(root), "--steps", "3", "--apply") == 2
    assert "No terminal to confirm at" in capsys.readouterr().out
    assert opened_folders(fake_grouper) == []


def test_a_network_target_is_confirmed_before_anything_is_applied(
        tmp_path, config, monkeypatch, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed) - 1. ######")
    monkeypatch.setattr(tool.canonicalise, "drive_is_network", lambda path: True)
    monkeypatch.setattr(tool.canonicalise, "resolve_target",
                        lambda target, keep, report: target)
    assert run(str(root), "--steps", "1", "--apply") == 2
    assert "Not confirmed" in capsys.readouterr().out
    # The legacy placeholder is still there: step 1 never ran.
    assert (root / "2026" / "07. July" / "2026-07-15_(Wed) - 1. ######").is_dir()


def test_only_the_confirmation_word_is_a_yes(tmp_path, config, monkeypatch):
    root = make_archive(tmp_path)
    run_object = make_run(root, config)
    monkeypatch.setattr(tool.sys, "stdin", type("Tty", (), {"isatty": lambda self: True})())
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert run_object.confirm("really?") is False
    monkeypatch.setattr("builtins.input", lambda prompt: "  APPLY  ")
    assert run_object.confirm("really?") is True


# --------------------------------------------------------------------------
# Steps 2 and 4 -- reuniting companions and sidecars
# --------------------------------------------------------------------------

RAW_STEM = "2026-07-15_(Wed)__08.14.02"


def build_stranded(root, year="2026"):
    """Two defects the reconcile step exists for, in one month folder.

    * a RAW whose representative the grouper moved into a sibling sub-event,
      left behind in the original event folder's ``__RAW``;
    * a RAW's sidecar in the dated folder's own ``__EXIF``, one level above
      where X10 puts it.
    """
    month = root / year / "07. July"
    event = month / f"{RAW_STEM} - __TO_SPLIT__(i=1)"
    (event / "__RAW").mkdir(parents=True)
    (event / "__EXIF").mkdir(parents=True)
    (event / f"{RAW_STEM}__f1.7__SG23U.jpg").write_bytes(b"jpg")
    (event / "__RAW" / f"{RAW_STEM}__RAW__f1.7__SG23U.CR2").write_bytes(b"raw")
    (event / "__EXIF" / f"{RAW_STEM}__RAW__f1.7__SG23U.CR2._exif").write_bytes(b"e")

    moved_stem = "2026-07-16_(Thu)__10.00.00"
    orphan_event = month / f"{moved_stem} - __TO_SPLIT__(i=0)"
    (orphan_event / "__RAW").mkdir(parents=True)
    (orphan_event / "__RAW" / f"{moved_stem}__RAW__f2.8__6D.CR2").write_bytes(b"raw")
    sub_event = month / f"{moved_stem} - Pier walk"
    sub_event.mkdir(parents=True)
    (sub_event / f"{moved_stem}__f2.8__6D.jpg").write_bytes(b"jpg")
    return event, orphan_event, sub_event


def test_a_stranded_companion_follows_its_representative(tmp_path, config):
    root = make_archive(tmp_path)
    _event, orphan_event, sub_event = build_stranded(root)
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    landed = sub_event / "__RAW" / "2026-07-16_(Thu)__10.00.00__RAW__f2.8__6D.CR2"
    assert landed.is_file()
    assert not (orphan_event / "__RAW").exists()          # emptied and pruned
    assert orphan_event.is_dir()                          # T1: never deleted


def test_a_sidecar_moves_down_beside_its_subject(tmp_path, config):
    root = make_archive(tmp_path)
    event, _orphan, _sub = build_stranded(root)
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    name = f"{RAW_STEM}__RAW__f1.7__SG23U.CR2._exif"
    assert (event / "__RAW" / "__EXIF" / name).is_file()  # X10
    assert not (event / "__EXIF" / name).exists()


def test_reconcile_dry_run_writes_nothing(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    event, orphan_event, sub_event = build_stranded(root)
    before = sorted(str(path) for path in root.rglob("*"))
    assert run(str(root), "--steps", "2") == 1
    assert sorted(str(path) for path in root.rglob("*")) == before
    out = capsys.readouterr().out
    assert "2 file(s) to move" in out
    assert "Nothing was changed" in out


def test_reconcile_is_idempotent(tmp_path, config):
    root = make_archive(tmp_path)
    build_stranded(root)
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    settled = sorted(str(path) for path in root.rglob("*"))
    # Second run: nothing left to do, and nothing pending either.
    assert run(str(root), "--steps", "2") == 0
    assert sorted(str(path) for path in root.rglob("*")) == settled


def make_raw_without_sidecar(root):
    day = make_event(root, "2026-07-15_(Wed)__08.14.02 - RAW only", images=0)
    raw_dir = day / "__RAW"
    raw_dir.mkdir()
    raw = raw_dir / f"{RAW_STEM}__RAW__f1.7__SG23U.CR2"
    raw.write_bytes(b"raw")
    return raw


def test_restructure_generates_and_places_a_missing_raw_sidecar(
        tmp_path, config, monkeypatch, capsys):
    root = make_archive(tmp_path)
    raw = make_raw_without_sidecar(root)
    config["raw_sidecar_generation"]["enabled"] = True

    def fake_generate(targets, _exiftool, log):
        assert targets == [raw]
        temporary = Path(str(raw) + "._exif")
        temporary.write_bytes(b"exiftool output")
        return tool.exif_sidecars.GenerationReport(
            requested=1, created=[temporary])

    monkeypatch.setattr(
        tool.exif_sidecars, "generate_adjacent_sidecars", fake_generate)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    sidecar = raw.parent / "__EXIF" / f"{raw.name}._exif"
    assert sidecar.read_bytes() == b"exiftool output"
    assert not Path(str(raw) + "._exif").exists()
    out = capsys.readouterr().out
    assert "Generated and placed 1/1 RAW sidecar" in out
    assert "has no sidecar" not in out


def test_raw_sidecar_generation_is_only_planned_in_a_dry_run(
        tmp_path, config, monkeypatch, capsys):
    root = make_archive(tmp_path)
    raw = make_raw_without_sidecar(root)
    config["raw_sidecar_generation"]["enabled"] = True
    monkeypatch.setattr(
        tool.exif_sidecars, "generate_adjacent_sidecars",
        lambda *_args, **_kwargs: pytest.fail("dry run must not invoke ExifTool"))

    assert run(str(root), "--steps", "2") == 1

    assert not (raw.parent / "__EXIF").exists()
    out = capsys.readouterr().out
    assert "1 RAW sidecar(s) to generate" in out
    assert "has no sidecar" not in out


def test_a_raw_exiftool_failure_is_reported_and_the_raw_is_left_untouched(
        tmp_path, config, monkeypatch, capsys):
    root = make_archive(tmp_path)
    raw = make_raw_without_sidecar(root)
    config["raw_sidecar_generation"]["enabled"] = True
    monkeypatch.setattr(
        tool.exif_sidecars, "generate_adjacent_sidecars",
        lambda *_args, **_kwargs: tool.exif_sidecars.GenerationReport(
            requested=1, missing=[raw], errors=1))

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 1

    assert raw.is_file()
    assert not (raw.parent / "__EXIF").exists()
    out = capsys.readouterr().out
    assert str(raw) in out
    assert "has no sidecar" in out


def test_reconcile_never_descends_into_the_ingest_pipeline(tmp_path, config):
    root = make_archive(tmp_path)
    stray = root / "____INGEST_PIPELINE" / "2026-07-15_(Wed)__08.14.02 - Day"
    (stray / "__EXIF").mkdir(parents=True)
    (stray / "shot.jpg").write_bytes(b"jpg")
    sidecar = stray / "__EXIF" / "shot.jpg._exif"
    sidecar.write_bytes(b"e")
    build_stranded(root)
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    assert sidecar.is_file()                              # untouched, P1/§0


def test_dated_folders_skips_month_and_taxonomy_folders(tmp_path, config):
    root = make_archive(tmp_path)
    event, orphan_event, sub_event = build_stranded(root)
    found = tool.dated_folders(make_run(root, config))
    assert set(found) == {event, orphan_event, sub_event}


def test_reconcile_runs_before_and_after_grouping(tmp_path, config, fake_grouper):
    """Steps 2 and 4 are the same engine, on either side of the GUI."""
    numbers = [number for number, _title, _action, _repeats in tool.STEPS]
    titles = {number: title for number, title, _a, _r in tool.STEPS}
    repeats = {number: repeated for number, _t, _a, repeated in tool.STEPS}
    assert numbers == [1, 2, 3, 4, 5, 6, 7, 8]
    assert "companions" in titles[2].lower()
    assert "companions" in titles[4].lower()
    assert TO_SPLIT_IN_TITLE in titles[3]
    # 4 repeats 2 and 5 repeats 1, which is what a dry run skips.
    assert repeats[4] == 2 and repeats[5] == 1
    assert repeats[1] is None and repeats[2] is None and repeats[3] is None


TO_SPLIT_IN_TITLE = "__TO_SPLIT__"


def test_the_engine_is_the_pipelines_own(tmp_path, config):
    """T8: one implementation, loaded rather than restated."""
    from src.pipeline_stages import companion_matching

    assert tool.matching.reconcile_folder.__doc__ == \
        companion_matching.reconcile_folder.__doc__
    assert tool.matching.place_companions.__doc__ == \
        companion_matching.place_companions.__doc__


# --------------------------------------------------------------------------
# A dry run does not call the same tool twice
# --------------------------------------------------------------------------

def test_a_dry_run_skips_the_repeat_passes(tmp_path, config, capsys):
    """Nothing changed between them, so the second would repeat the first."""
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed) - 1. ######")

    assert run(str(root)) == 1

    out = capsys.readouterr().out
    assert "STEP 4" in out and "STEP 5" in out
    assert out.count("skipped, a dry run leaves nothing") == 2
    assert "step 2 already reported it" in out
    assert "step 1 already reported it" in out


def test_an_applied_run_still_makes_both_passes(tmp_path, config, fake_grouper,
                                                capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed) - 1. ######")

    assert run(str(root), "--apply", "--yes") == 0

    out = capsys.readouterr().out
    assert "skipped, a dry run leaves nothing" not in out
    assert "Canonicalising (again)" in out
    assert "Reconciling (again)" in out


def test_a_repeat_asked_for_on_its_own_still_runs(tmp_path, config, capsys):
    """--steps 5 means step 5, dry run or not: nothing came before it."""
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed) - 1. ######")

    assert run(str(root), "--steps", "5") == 1

    out = capsys.readouterr().out
    assert "Canonicalising (again)" in out
    assert "skipped, a dry run leaves nothing" not in out


# --------------------------------------------------------------------------
# Non-compliant folders, gathered and shown at the end
# --------------------------------------------------------------------------

def test_non_compliant_folders_are_reported_at_the_end(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - Lens tests")
    junk = root / "2026" / "07. July" / "Random Junk Folder"
    junk.mkdir()

    assert run(str(root), "--steps", "2") in (0, 1)

    out = capsys.readouterr().out
    assert "NON-COMPLIANT FOLDERS  (1)" in out
    assert str(junk) in out
    # After the summary, which is the whole point of gathering them.
    assert out.index("SUMMARY") < out.index("NON-COMPLIANT FOLDERS")


def test_nothing_to_report_prints_no_section(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - Lens tests")

    assert run(str(root), "--steps", "2") in (0, 1)

    assert "NON-COMPLIANT" not in capsys.readouterr().out


def test_a_legacy_container_with_no_equivalent_is_reported(tmp_path, config,
                                                           capsys):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Lens tests")
    unsupported = event / "##   UNSUPPORTED EXTENSIONS   ##"
    unsupported.mkdir()
    (unsupported / "weird.xyz").write_bytes(b"x")

    assert run(str(root), "--steps", "2") in (0, 1)

    out = capsys.readouterr().out
    assert "NON-COMPLIANT FOLDERS" in out
    assert "no modern equivalent" in out
    assert (unsupported / "weird.xyz").is_file()


def test_legacy_containers_migrate_through_the_tool(tmp_path, config):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Lens tests")
    legacy = event / "##   RAWs   ##"
    legacy.mkdir()
    (legacy / "2026-07-15_(Wed)__08.14.02__RAW__f1.7.CR2").write_bytes(b"raw")

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    assert (event / "__RAW" / "2026-07-15_(Wed)__08.14.02__RAW__f1.7.CR2").is_file()
    assert not legacy.exists()


# --------------------------------------------------------------------------
# Legacy __VIDEOS migration (ARCHIVE_STANDARD.md S5/V1/V4/V8)
# --------------------------------------------------------------------------

VIDEO_NAME = "2026-07-15_(Wed)__10.11.12__fNA__T---__LNA__I---s__NOID.mp4"


def test_legacy_videos_move_up_with_sidecars_and_previews_then_park_the_folder(
        tmp_path, config):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Videos", images=0)
    legacy = event / "__Videos"              # historical casing is accepted
    legacy_exif = legacy / "__EXIF"
    legacy_previews = legacy / "__PREVIEWS"
    legacy_exif.mkdir(parents=True)
    legacy_previews.mkdir()
    (legacy / VIDEO_NAME).write_bytes(b"video")
    (legacy_exif / f"{VIDEO_NAME}._exif").write_text(
        "Date/Time Original              : 2026:07:15 10:11:12\n",
        encoding="iso-8859-1")
    (legacy_previews / f"{VIDEO_NAME}.lrv").write_bytes(b"preview")

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    assert (event / VIDEO_NAME).read_bytes() == b"video"
    assert (event / "__EXIF" / f"{VIDEO_NAME}._exif").is_file()
    assert (event / "__PREVIEWS" / f"{VIDEO_NAME}.lrv").is_file()
    assert (event.parent / "__EMPTY_SUBFOLDERS" / "__Videos").is_dir()
    assert not legacy.exists()


def test_an_unstamped_legacy_video_is_named_from_intrinsic_metadata(
        tmp_path, config, monkeypatch):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Videos", images=0)
    legacy = event / "__VIDEOS"
    legacy.mkdir()
    video = legacy / "MVI_0042.MOV"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        tool.exif_sidecars, "read_metadata_text",
        lambda *_args: (
            "[QuickTime]\n"
            "Create Date                     : 2026:07:15 10:11:12\n"
            "Camera Model Name               : Mystery Camera\n"))

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    renamed = event / VIDEO_NAME.replace(".mp4", ".mov")
    assert renamed.read_bytes() == b"video"
    assert (event / "__EXIF" / f"{renamed.name}._exif").is_file()
    assert (event.parent / "__EMPTY_SUBFOLDERS" / "__VIDEOS").is_dir()


def test_an_unstamped_video_uses_and_renames_a_sidecar_already_in_event_exif(
        tmp_path, config, monkeypatch):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Videos", images=0)
    legacy = event / "__VIDEOS"
    event_exif = event / "__EXIF"
    legacy.mkdir()
    event_exif.mkdir()
    video = legacy / "MVI_0042.MOV"
    video.write_bytes(b"video")
    old_sidecar = event_exif / "MVI_0042.MOV._exif"
    old_sidecar.write_text(
        "Create Date                     : 2026:07:15 10:11:12\n",
        encoding="iso-8859-1")
    monkeypatch.setattr(
        tool.exif_sidecars, "read_metadata_text",
        lambda *_args: pytest.fail("the existing sidecar has the timestamp"))

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    renamed = event / VIDEO_NAME.replace(".mp4", ".mov")
    assert renamed.is_file()
    assert not old_sidecar.exists()
    assert (event_exif / f"{renamed.name}._exif").is_file()
    assert (event.parent / "__EMPTY_SUBFOLDERS" / "__VIDEOS").is_dir()


def test_filesystem_time_does_not_date_a_video_and_its_companions_follow(
        tmp_path, config, monkeypatch, capsys):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Videos", images=0)
    legacy = event / "__VIDEOS"
    legacy.mkdir()
    video = legacy / "VID_unknown.MP4"
    video.write_bytes(b"video")
    preview = legacy / "VID_unknown.LRV"
    preview.write_bytes(b"preview")
    monkeypatch.setattr(
        tool.exif_sidecars, "read_metadata_text",
        lambda *_args: "File Modification Date/Time     : 2026:07:15 10:11:12\n")

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    review = event / "__VIDEOS_TO_RENAME"
    tagged = review / "__TO_RENAME__VID_unknown.MP4"
    assert tagged.read_bytes() == b"video"
    assert (review / "__PREVIEWS" / f"{tagged.name}.lrv").read_bytes() == b"preview"
    assert (review / "__EXIF" / f"{tagged.name}._exif").is_file()
    assert (event.parent / "__EMPTY_SUBFOLDERS" / "__VIDEOS").is_dir()
    assert "no intrinsic capture time" in capsys.readouterr().out


def test_an_already_empty_legacy_video_folder_is_parked_at_month_level(
        tmp_path, config):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Videos", images=0)
    legacy = event / "__Videos"
    (legacy / "an empty nested folder").mkdir(parents=True)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    parked = event.parent / "__EMPTY_SUBFOLDERS" / "__Videos"
    assert (parked / "an empty nested folder").is_dir()
    assert not legacy.exists()


def test_an_exiftool_failure_never_means_a_video_is_undatable(
        tmp_path, config, monkeypatch):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Videos", images=0)
    legacy = event / "__VIDEOS"
    legacy.mkdir()
    video = legacy / "unknown.mov"
    video.write_bytes(b"video")

    def unavailable(*_args):
        raise FileNotFoundError("ExifTool missing")

    monkeypatch.setattr(tool.exif_sidecars, "read_metadata_text", unavailable)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 1
    assert video.is_file()
    assert not (event / "__VIDEOS_TO_RENAME").exists()
    assert not (event.parent / "__EMPTY_SUBFOLDERS").exists()


def test_legacy_video_migration_dry_run_reads_metadata_but_writes_nothing(
        tmp_path, config, monkeypatch, capsys):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Videos", images=0)
    legacy = event / "__VIDEOS"
    legacy.mkdir()
    video = legacy / "MVI_0042.MOV"
    video.write_bytes(b"video")
    inspected = []

    def metadata(target, _exiftool):
        inspected.append(target)
        return "Create Date                     : 2026:07:15 10:11:12\n"

    monkeypatch.setattr(tool.exif_sidecars, "read_metadata_text", metadata)

    assert run(str(root), "--steps", "2") == 1

    assert inspected == [video]
    assert video.is_file()
    assert not (event / VIDEO_NAME.replace(".mp4", ".mov")).exists()
    assert not (event / "__EXIF").exists()
    assert not (event.parent / "__EMPTY_SUBFOLDERS").exists()
    assert "Nothing was changed" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Month-level parking (ARCHIVE_STANDARD.md H1-H6)
# --------------------------------------------------------------------------

def test_nested_parking_is_hoisted_to_the_month_and_its_shell_removed(
        tmp_path, config):
    root = make_archive(tmp_path)
    event = make_event(
        root, "2026-07-15_(Wed)__08.14.02 - ____GROUP____(d=1)", images=0)
    nested = event / "__EMPTY_SUBFOLDERS"
    parked = nested / "2026-07-15_(Wed)__09.00.00 - __TO_SPLIT__(EMPTY)"
    parked.mkdir(parents=True)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    month_parking = event.parent / "__EMPTY_SUBFOLDERS"
    assert (month_parking / parked.name).is_dir()
    assert not nested.exists()


def test_parking_hoist_is_recursive_and_flattens_every_area_into_the_month(
        tmp_path, config):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Group", images=0)
    outer = event / "__EMPTY_SUBFOLDERS"
    parked_day = outer / "2026-07-15_(Wed)__09.00.00 - old empty day"
    inner = parked_day / "__EMPTY_SUBFOLDERS"
    deepest = inner / "2026-07-15_(Wed)__10.00.00 - old empty sub-event"
    deepest.mkdir(parents=True)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    month_parking = event.parent / "__EMPTY_SUBFOLDERS"
    assert (month_parking / parked_day.name).is_dir()
    assert (month_parking / deepest.name).is_dir()
    assert not outer.exists()
    assert not (month_parking / parked_day.name / "__EMPTY_SUBFOLDERS").exists()


def test_parking_hoist_versions_a_name_collision_instead_of_overwriting(
        tmp_path, config):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Group", images=0)
    name = "2026-07-15_(Wed)__09.00.00 - __TO_SPLIT__(EMPTY)"
    existing = event.parent / "__EMPTY_SUBFOLDERS" / name
    incoming = event / "__EMPTY_SUBFOLDERS" / name
    existing.mkdir(parents=True)
    incoming.mkdir(parents=True)
    (existing / "keep.txt").write_text("existing", encoding="utf-8")

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    month_parking = event.parent / "__EMPTY_SUBFOLDERS"
    assert (month_parking / name / "keep.txt").read_text(encoding="utf-8") == "existing"
    assert (month_parking / f"{name}_2").is_dir()


def test_parking_hoist_dry_run_reports_but_changes_nothing(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    event = make_event(root, "2026-07-15_(Wed)__08.14.02 - Group", images=0)
    nested = event / "__EMPTY_SUBFOLDERS"
    parked = nested / "2026-07-15_(Wed)__09.00.00 - __TO_SPLIT__(EMPTY)"
    parked.mkdir(parents=True)

    assert run(str(root), "--steps", "2") == 1

    assert parked.is_dir()
    assert not (event.parent / "__EMPTY_SUBFOLDERS").exists()
    out = capsys.readouterr().out
    assert "Nested parking areas" in out
    assert "empty parking shell" in out


def test_parked_dated_folders_never_reenter_the_grouper(tmp_path, config):
    root = make_archive(tmp_path)
    parked = (root / "2026" / "07. July" / "__EMPTY_SUBFOLDERS" /
              "2026-07-15_(Wed)__09.00.00 - __TO_SPLIT__(i=1)")
    parked.mkdir(parents=True)
    (parked / "2026-07-15_(Wed)__09.00.00__f1.7.jpg").write_bytes(b"x")

    run_state = tool.Run(
        type("Args", (), {
            "apply": False, "quiet": False, "yes": True,
            "allow_network_tool": False, "max_folders": 0,
            "open_all": False,
        })(),
        root, [root / "2026"], False)

    assert tool.find_to_split_folders(run_state) == []


# --------------------------------------------------------------------------
# Steps, ordering and exit codes
# --------------------------------------------------------------------------

def test_steps_run_in_their_fixed_order_however_they_are_typed():
    assert tool.selected_steps("3,1") == [1, 3]
    assert tool.selected_steps(None) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert tool.selected_steps("2") == [2]


def test_a_bad_step_number_is_an_error(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    assert run(str(root), "--steps", "99") == 2
    assert "Bad --steps" in capsys.readouterr().out


def test_step_one_canonicalises_and_step_three_runs_again(tmp_path, config,
                                                          fake_grouper):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed) - 1. ######")
    assert run(str(root), "--steps", "1,3", "--apply", "--yes") == 0
    july = root / "2026" / "07. July"
    names = sorted(path.name for path in july.iterdir() if path.is_dir())
    assert names == ["2026-07-15_(Wed)__08.14.00 - __TO_SPLIT__(i=1_e=0)"]


def test_the_whole_run_end_to_end(tmp_path, config, fake_grouper, capsys):
    """1 renames the placeholder, 2 opens what 1 marked, 3 tidies after it."""
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed) - 1. ######")
    assert run(str(root), "--apply", "--yes") == 0
    assert [path.name for path in opened_folders(fake_grouper)] == [
        "2026-07-15_(Wed)__08.14.00 - __TO_SPLIT__(i=1_e=0)"]
    out = capsys.readouterr().out
    assert "NOT IMPLEMENTED" in out           # steps 4 and 5
    assert "SUMMARY" in out


def test_a_dry_run_changes_nothing(tmp_path, config, fake_grouper):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed) - 1. ######")
    before = sorted(str(path) for path in root.rglob("*"))
    assert run(str(root)) == 1
    assert sorted(str(path) for path in root.rglob("*")) == before
    assert folder.is_dir()
    assert opened_folders(fake_grouper) == []


# --------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------

def test_an_applied_run_journals_what_it_did(tmp_path, config, fake_grouper):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    journal = tmp_path / "journal.jsonl"
    assert run(str(root), "--apply", "--yes", "--journal", str(journal)) == 0
    records = [json.loads(line) for line in
               journal.read_text(encoding="utf-8").splitlines()]
    events = [record["event"] for record in records]
    assert events[0] == "run_started"
    assert events[-1] == "run_finished"
    assert "group_opened" in events and "group_closed" in events
    assert all("at" in record for record in records)


def test_a_dry_run_writes_no_journal(tmp_path, config):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    assert run(str(root)) == 1
    assert list(root.rglob("_restructure_journal_*.jsonl")) == []


def test_an_unwritable_journal_does_not_end_the_run(tmp_path, config, fake_grouper):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    unwritable = tmp_path / "no such folder" / "journal.jsonl"
    assert run(str(root), "--apply", "--yes", "--journal", str(unwritable)) == 0
    assert opened_folders(fake_grouper) != []


# --------------------------------------------------------------------------
# Step 6 -- mark and time the groups (ARCHIVE_STANDARD.md section 3)
# --------------------------------------------------------------------------

def make_group(root, name, children, year="2026", month="07. July"):
    """A dated parent folder holding dated children, each with stamped shots.

    ``children`` maps a child folder name to the stamps its files carry, so a
    test states exactly what the span it expects should be computed from.
    """
    parent = root / year / month / name
    parent.mkdir(parents=True, exist_ok=True)
    for child_name, file_stamps in children.items():
        child = parent / child_name
        child.mkdir(parents=True, exist_ok=True)
        for stamp in file_stamps:
            (child / ("%s__f1.7__SG23U.jpg" % stamp)).write_bytes(b"x")
    return parent


def month_entries(folder):
    """What the month folder holds, so a rename can be read off it."""
    return sorted(path.name for path in folder.parent.iterdir())


def test_a_parent_of_dated_folders_is_marked_timed_and_spanned(tmp_path, config):
    """C1, C5, C6: the marker, the start off the earliest file, the end off the last."""
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed) - Sopot weekend", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
        "2026-07-16_(Thu)__09.10.44": ["2026-07-16_(Thu)__19.02.44"],
    })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-15_(Wed)__08.14.02#16__19.02.44 - ____GROUP____(d=2) - Sopot weekend"]


def test_a_single_day_group_still_states_both_ends(tmp_path, config):
    """C9: a day split into sub-events is the same shape as a fortnight."""
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-18_(Sat) - pier", {
        "2026-07-18_(Sat)__11.03.27": ["2026-07-18_(Sat)__11.03.27"],
        "2026-07-18_(Sat)__14.31.09": ["2026-07-18_(Sat)__22.14.09"],
    })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-18_(Sat)__11.03.27#18__22.14.09 - ____GROUP____(d=2) - pier"]


def test_a_leaf_folder_is_left_alone(tmp_path, config):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__08.14.02 - Lens tests")
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(folder) == ["2026-07-15_(Wed)__08.14.02 - Lens tests"]


def test_a_dry_run_changes_nothing_and_reports_pending(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed) - Sopot weekend", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    assert run(str(root), "--steps", "6") == 1
    assert month_entries(group) == ["2026-07-15_(Wed) - Sopot weekend"]
    assert "Nothing was changed" in capsys.readouterr().out


def test_the_legacy_marker_is_converted_and_the_description_kept(tmp_path, config):
    """C15: the pre-v0.9 spelling is read once and written back as the new one."""
    root = make_archive(tmp_path)
    group = make_group(
        root, "2026-07-15_(Wed)__08.14.02#16 - __CONTAINER__(d=1) - Malbork trip", {
            "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
            "2026-07-16_(Thu)__09.10.44": ["2026-07-16_(Thu)__17.40.11"],
        })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-15_(Wed)__08.14.02#16__17.40.11 - ____GROUP____(d=2) - Malbork trip"]


def test_a_stale_count_and_a_stale_span_are_both_rebuilt(tmp_path, config):
    """C11: the stamps belong to the tool, and it corrects them where they lie."""
    root = make_archive(tmp_path)
    group = make_group(
        root, "2026-07-15_(Wed)__08.14.02#20__23.59.59 - ____GROUP____(d=9) - Sopot", {
            "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
            "2026-07-16_(Thu)__09.10.44": ["2026-07-16_(Thu)__19.02.44"],
        })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-15_(Wed)__08.14.02#16__19.02.44 - ____GROUP____(d=2) - Sopot"]


def test_a_folder_that_lost_its_children_loses_the_marker_and_the_span(
        tmp_path, config):
    """C2: adding or removing the last dated child flips the marker."""
    root = make_archive(tmp_path)
    group = make_group(
        root, "2026-07-15_(Wed)__08.14.02#16__19.02.44 - ____GROUP____(d=2) - Sopot",
        {})
    (group / "2026-07-15_(Wed)__08.14.02__f1.7__SG23U.jpg").write_bytes(b"x")
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == ["2026-07-15_(Wed)__08.14.02 - Sopot"]


def test_a_nested_group_spans_everything_beneath_it(tmp_path, config):
    """C6 over a nest: the outer end comes off the inner span, not the child's date."""
    root = make_archive(tmp_path)
    outer = make_group(root, "2026-07-15_(Wed) - Norway", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    inner = outer / "2026-07-16_(Thu)__09.10.44 - the fjords"
    first = inner / "2026-07-16_(Thu)__09.10.44"
    last = inner / "2026-07-18_(Sat)__06.55.02"
    first.mkdir(parents=True)
    last.mkdir(parents=True)
    (first / "2026-07-16_(Thu)__09.10.44__f1.7__SG23U.jpg").write_bytes(b"x")
    (last / "2026-07-18_(Sat)__20.11.19__f1.7__SG23U.jpg").write_bytes(b"x")

    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(outer) == [
        "2026-07-15_(Wed)__08.14.02#18__20.11.19 - ____GROUP____(d=2) - Norway"]
    renamed = outer.parent / month_entries(outer)[0]
    assert sorted(path.name for path in renamed.iterdir()) == [
        "2026-07-15_(Wed)__08.14.02",
        "2026-07-16_(Thu)__09.10.44#18__20.11.19 - ____GROUP____(d=2) - the fjords",
    ]


def test_media_inside_a_group_is_reported_and_never_moved(tmp_path, config, capsys):
    """C3 is reported; C4, which would move it down, is open question 5."""
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed) - Sopot", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    loose = "2026-07-15_(Wed)__12.00.00__f1.7__SG23U.jpg"
    (group / loose).write_bytes(b"x")
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert "open question 5" in capsys.readouterr().out
    renamed = group.parent / month_entries(group)[0]
    assert (renamed / loose).is_file()               # still exactly where it was


def test_a_taxonomy_subfolder_inside_a_group_is_reported(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed) - Sopot", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    (group / "__RAW").mkdir()
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert "__RAW" in capsys.readouterr().out


def test_a_parking_area_inside_a_group_is_allowed(tmp_path, config, capsys):
    """H2: a group is a level dated folders sit on, so a parking area may too.

    It holds the sub-events that group has emptied, beside the ones it still
    has -- which is the whole of the sibling rule.
    """
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed) - Sopot", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    parking = group / "__EMPTY_SUBFOLDERS"
    parking.mkdir()
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    out = capsys.readouterr().out
    assert "neither a dated folder" not in out
    assert "H2/H6" not in out
    renamed = group.parent / month_entries(group)[0]
    assert (renamed / "__EMPTY_SUBFOLDERS").is_dir()      # left exactly where it was


def test_a_group_whose_earliest_file_predates_its_date_is_reported_not_moved(
        tmp_path, config, capsys):
    """C12 / open question 6: the month-folder move is nobody's to make yet."""
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - Sopot", {
        "2026-07-15_(Wed)__08.14.02": ["2026-06-30_(Tue)__08.14.02"],
    })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert "open question 6" in capsys.readouterr().out
    assert group.is_dir()                            # untouched, still where it was


def test_a_group_with_no_stamped_file_anywhere_is_reported_not_guessed_at(
        tmp_path, config, capsys):
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - Sopot", {
        "2026-07-15_(Wed)__08.14.02": [],
    })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert "no file under it carries a capture stamp" in capsys.readouterr().out
    assert group.is_dir()


def test_a_split_day_with_nothing_left_at_its_top_level_becomes_a_group(
        tmp_path, config):
    """The ordinary case: the grouper split the day, so the parent is a group now.

    The counts go with the marker -- "(i=79)" is what the day held before it
    was split, not a name -- and the folder comes out unnamed, which is exactly
    what it is.
    """
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=2)", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
        "2026-07-15_(Wed)__14.31.09": ["2026-07-15_(Wed)__16.20.31"],
    })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-15_(Wed)__08.14.02#15__16.20.31 - ____GROUP____(d=2)"]


def test_a_half_split_day_keeps_its_marker_and_is_reported(tmp_path, config, capsys):
    """A day with children AND shots of its own is both things at once.

    Taking ``__TO_SPLIT__`` off would strand the loose media -- step 3 finds
    folders by that marker -- and moving it down into a child is C4, open
    question 5. So the folder is left exactly as it is and reported.
    """
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=3)", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    (group / "2026-07-15_(Wed)__12.00.00__f1.7__SG23U.jpg").write_bytes(b"x")
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=3)"]      # untouched
    out = capsys.readouterr().out
    assert "__TO_SPLIT__" in out and "open question 5" in out


def test_a_name_a_person_wrote_survives_becoming_a_group(tmp_path, config):
    """T7: the label is the same claim as a description, written before C1 existed."""
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - 1. Sopot weekend", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-15_(Wed)__08.14.02#15__08.14.02 - ____GROUP____(d=1) - Sopot weekend"]


def test_the_legacy_placeholder_is_not_mistaken_for_a_name(tmp_path, config):
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - 1. ######", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    assert run(str(root), "--steps", "6", "--apply", "--yes") == 0
    assert month_entries(group) == [
        "2026-07-15_(Wed)__08.14.02#15__08.14.02 - ____GROUP____(d=1)"]


# --------------------------------------------------------------------------
# H2 -- a parking area is a sibling of what it parks, at whatever level
# --------------------------------------------------------------------------

def test_a_parking_area_inside_a_group_is_left_where_it_is(tmp_path, config):
    """H2: a group holds dated children, so it is a level a parking area sits on.

    This is the case that separates the sibling rule from a month-level one:
    hoisting here would carry a sub-event out of the group it was emptied from
    and drop it among the month's own days, where nothing says where it came
    from.
    """
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - ____GROUP____(d=1)", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    parked = group / "__EMPTY_SUBFOLDERS" / "2026-07-16_(Thu)__00.00.00 - __TO_SPLIT__(EMPTY)"
    parked.mkdir(parents=True)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    assert parked.is_dir()                                   # untouched
    assert not (group.parent / "__EMPTY_SUBFOLDERS").exists()  # nothing at month level


def test_a_parking_area_inside_a_leaf_day_is_hoisted_one_level(tmp_path, config):
    """H6: a leaf dated folder holds one event's files, and a parked folder is not one.

    The legacy-container migration used to put a shell here. It belongs beside
    the day, not inside it.
    """
    root = make_archive(tmp_path)
    day = make_event(root, "2026-07-15_(Wed)__08.14.02 - Lens tests", images=1)
    nested = day / "__EMPTY_SUBFOLDERS"
    (nested / "##   EXIFs   ##").mkdir(parents=True)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    assert not nested.exists()
    assert (day.parent / "__EMPTY_SUBFOLDERS" / "##   EXIFs   ##").is_dir()


def test_a_parking_area_inside_a_leaf_day_inside_a_group_stops_at_the_group(
        tmp_path, config):
    """The two rules together: hoist out of the leaf, but no further than the group."""
    root = make_archive(tmp_path)
    group = make_group(root, "2026-07-15_(Wed)__08.14.02 - ____GROUP____(d=1)", {
        "2026-07-15_(Wed)__08.14.02": ["2026-07-15_(Wed)__08.14.02"],
    })
    day = group / "2026-07-15_(Wed)__08.14.02"
    nested = day / "__EMPTY_SUBFOLDERS"
    (nested / "##   EXIFs   ##").mkdir(parents=True)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    assert not nested.exists()
    assert (group / "__EMPTY_SUBFOLDERS" / "##   EXIFs   ##").is_dir()
    assert not (group.parent / "__EMPTY_SUBFOLDERS").exists()


def test_a_parking_area_above_its_level_is_left_alone(tmp_path, config):
    """H7: one under a year folder is reported, never pushed down into a month.

    Which month each folder in it belongs to is a different question, and
    hoisting is not the pass that answers it.
    """
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - Lens tests")
    year_parking = root / "2026" / "__EMPTY_SUBFOLDERS"
    parked = year_parking / "2026-07-19_(Sun)__00.00.00 - __TO_SPLIT__(EMPTY)"
    parked.mkdir(parents=True)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    assert parked.is_dir()
