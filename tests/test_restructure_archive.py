"""The restructuring front door: the five steps, the target rules, the guards.

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
                           "day_boundary_time": "04.44.44"}}
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
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    assert opened_folders(fake_grouper) == [worth]
    out = capsys.readouterr().out
    assert "nothing for the grouper to show" in out
    assert empty.name in out                  # said out loud, not dropped


def test_every_marked_folder_showless_is_success_and_opens_nothing(
        tmp_path, config, fake_grouper, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__00.00.00 - __TO_SPLIT__(EMPTY)", images=0)
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
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
        assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
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
# Step 2 -- launching the grouper
# --------------------------------------------------------------------------

def test_dry_run_lists_the_folders_and_opens_nothing(tmp_path, config, fake_grouper,
                                                    capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "2") == 1
    assert "the grouper was not opened" in capsys.readouterr().out
    assert opened_folders(fake_grouper) == []


def test_apply_opens_every_marked_folder_one_at_a_time(tmp_path, config,
                                                       fake_grouper):
    root = make_archive(tmp_path)
    first = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    second = make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
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
        assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    finally:
        tool.grouper.run_grouper = real_run_grouper
    assert opened_folders(fake_grouper) == [first]
    assert "no longer under that name" in capsys.readouterr().out


def test_max_folders_limits_the_batch(tmp_path, config, fake_grouper, capsys):
    root = make_archive(tmp_path)
    first = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    make_event(root, "2026-07-18_(Sat)__09.00.00 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "2", "--apply", "--yes", "--max-folders", "1") == 0
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
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 1
    assert len(opened_folders(fake_grouper)) == 2
    out = capsys.readouterr().out
    assert "exited with code 3" in out
    assert "boom" in out                      # the stderr tail, not just the code
    assert str(second) in "\n".join(str(path) for path in opened_folders(fake_grouper))


def test_a_missing_grouper_stops_step_two(tmp_path, config, capsys):
    config["screenshot_grouping"] = {"python": "", "project_path": ""}
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 2
    assert "not installed" in capsys.readouterr().out


def test_a_grouper_on_the_network_is_refused(tmp_path, config, fake_grouper,
                                             monkeypatch, capsys):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    project = Path(fake_grouper["project_path"])
    monkeypatch.setattr(tool.canonicalise, "drive_is_network",
                        lambda path: Path(path) == project)
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 2
    assert "network location" in capsys.readouterr().out


def test_allow_network_tool_overrides_that(tmp_path, config, fake_grouper,
                                           monkeypatch):
    root = make_archive(tmp_path)
    folder = make_event(root, "2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=1)")
    project = Path(fake_grouper["project_path"])
    monkeypatch.setattr(tool.canonicalise, "drive_is_network",
                        lambda path: Path(path) == project)
    assert run(str(root), "--steps", "2", "--apply", "--yes",
               "--allow-network-tool") == 0
    assert opened_folders(fake_grouper) == [folder]


def test_nothing_to_group_is_success(tmp_path, config, fake_grouper):
    root = make_archive(tmp_path)
    make_event(root, "2026-07-15_(Wed)__08.14.02 - Sopot weekend")
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
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
    assert run(str(root), "--steps", "2", "--apply") == 2
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
# Steps, ordering and exit codes
# --------------------------------------------------------------------------

def test_steps_run_in_their_fixed_order_however_they_are_typed():
    assert tool.selected_steps("3,1") == [1, 3]
    assert tool.selected_steps(None) == [1, 2, 3, 4, 5]
    assert tool.selected_steps("2") == [2]


def test_a_bad_step_number_is_an_error(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    assert run(str(root), "--steps", "9") == 2
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
