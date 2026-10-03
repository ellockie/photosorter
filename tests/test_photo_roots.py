"""Photo roots: a run works on the root whose INBOX has media, asking when several do."""

import json
import threading
from pathlib import Path

from src.core import load_config, normalize_config_paths, save_config
from src.photo_roots import RootIntake, choose_root, survey_roots

INBOX = Path("____INGEST_PIPELINE") / "INBOX"


def make_roots(tmp_path, names=("c", "d", "nas")):
    roots = [tmp_path / name for name in names]
    for root in roots:
        (root / INBOX).mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "paths": {
            "root_folder": str(roots[0]),
            "working_folder": str(roots[0] / INBOX.parent),
            "inbox_folder": str(roots[0] / INBOX),
            "ready_folder": str(roots[0] / INBOX.parent / "READY"),
            "temp_folder": str(roots[0] / INBOX.parent / ".TMP"),
            "camera_uploads": str(tmp_path / "uploads"),
        },
        "photo_roots": [str(root) + "\\" for root in roots],
    }))
    return roots, config_path


def drop(root, *names):
    for name in names:
        path = root / INBOX / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


def answers(*replies):
    queue = list(replies)
    return lambda _prompt: queue.pop(0)


class TestSurvey:
    def test_every_root_is_surveyed_at_its_own_inbox(self, tmp_path):
        (c, d, nas), config_path = make_roots(tmp_path)
        drop(d, "a.jpg", "sub/b.CR2", "clip.mp4")

        intakes = survey_roots(config_path)

        assert [(i.root, i.inbox, i.media) for i in intakes] == [
            (c, c / INBOX, 0),
            (d, d / INBOX, 3),
            (nas, nas / INBOX, 0),
        ]

    def test_only_media_counts(self, tmp_path):
        (c, _d, _nas), config_path = make_roots(tmp_path)
        drop(c, "notes.txt", "a.jpg._exif", "desktop.ini")

        assert survey_roots(config_path)[0].media == 0

    def test_dont_move_is_not_intake(self, tmp_path):
        (c, _d, _nas), config_path = make_roots(tmp_path)
        drop(c, "__DONT_MOVE/a.jpg")

        assert survey_roots(config_path)[0].media == 0

    def test_a_root_that_is_not_there_is_unreachable(self, tmp_path):
        (c, d, _nas), config_path = make_roots(tmp_path)
        gone = tmp_path / "gone"
        data = json.loads(config_path.read_text())
        data["photo_roots"].append(str(gone))
        config_path.write_text(json.dumps(data))

        intakes = survey_roots(config_path)

        assert intakes[-1].root == gone and not intakes[-1].reachable

    def test_a_stalled_root_counts_as_unreachable(self, tmp_path):
        (c, d, nas), config_path = make_roots(tmp_path)
        release = threading.Event()

        def stall_on_nas(path):
            if Path(path) == nas:
                release.wait(5)
            return Path(path).is_dir()

        try:
            intakes = survey_roots(config_path, is_dir=stall_on_nas, timeout=0.2)
        finally:
            release.set()

        assert [i.reachable for i in intakes] == [True, True, False]

    def test_without_photo_roots_the_configured_root_is_the_only_one(self, tmp_path):
        (c, _d, _nas), config_path = make_roots(tmp_path)
        data = json.loads(config_path.read_text())
        del data["photo_roots"]
        config_path.write_text(json.dumps(data))

        assert [i.root for i in survey_roots(config_path)] == [c]


class TestTheNasInboxIsNeverARoot:
    """Its files are harvested into a local run, never processed on the NAS."""

    def test_the_survey_marks_the_root_whose_inbox_is_the_nas_inbox(self, tmp_path):
        (c, d, nas), config_path = make_roots(tmp_path)
        data = json.loads(config_path.read_text())
        data["paths"]["ingest"] = {"nas_inbox": str(nas / INBOX)}
        config_path.write_text(json.dumps(data))

        assert [i.harvested for i in survey_roots(config_path)] == [False, False, True]

    def test_media_only_in_the_nas_inbox_keeps_the_configured_root(self):
        c, nas = Path("/c"), Path("/nas")
        said = []
        intakes = [RootIntake(c, c / INBOX, 0), RootIntake(nas, nas / INBOX, 2, harvested=True)]

        assert choose_root(intakes, ask=answers(), say=said.append) == c
        assert any("NAS inbox" in line for line in said)

    def test_it_is_not_offered_when_other_inboxes_have_media(self):
        c, d, nas = Path("/c"), Path("/d"), Path("/nas")
        intakes = [RootIntake(c, c / INBOX, 1), RootIntake(d, d / INBOX, 0),
                   RootIntake(nas, nas / INBOX, 5, harvested=True)]

        assert choose_root(intakes, ask=answers(), say=lambda _: None) == c


class TestChoose:
    C, D, NAS = Path("/c"), Path("/d"), Path("/nas")

    def intakes(self, c=0, d=0, nas=0):
        return [RootIntake(root, root / INBOX, media)
                for root, media in ((self.C, c), (self.D, d), (self.NAS, nas))]

    def test_nothing_waiting_keeps_the_configured_root(self):
        assert choose_root(self.intakes(), ask=answers(), say=lambda _: None) == self.C

    def test_media_in_one_inbox_picks_its_root(self):
        assert choose_root(self.intakes(d=4), ask=answers(), say=lambda _: None) == self.D

    def test_media_in_several_asks_which(self):
        said = []

        root = choose_root(self.intakes(c=1, nas=2), ask=answers("7", "x", "2"), say=said.append)

        assert root == self.NAS
        assert any(str(self.C / INBOX) in line for line in said)
        assert not any(str(self.D / INBOX) in line for line in said)

    def test_quitting_runs_nothing(self):
        assert choose_root(self.intakes(c=1, d=1), ask=answers("q"), say=lambda _: None) is None

    def test_no_console_runs_nothing(self):
        def closed(_prompt):
            raise EOFError

        assert choose_root(self.intakes(c=1, d=1), ask=closed, say=lambda _: None) is None

    def test_an_unreachable_root_is_reported_and_passed_over(self):
        said = []
        intakes = self.intakes(d=1)
        intakes[2].media = None

        assert choose_root(intakes, ask=answers(), say=said.append) == self.D
        assert any(str(self.NAS) in line for line in said)


class TestEveryRootIsTreatedAlike:
    def test_a_photo_root_keeps_its_declared_ingest_paths(self, tmp_path):
        uploads = r"c:\Users\someone\Dropbox\Camera Uploads"
        config = {
            "paths": {"root_folder": r"c:\__PHOTOS", "camera_uploads": uploads},
            "photo_roots": [r"c:\__PHOTOS", r"d:\___PHOTOS"],
        }

        paths = normalize_config_paths(
            json.loads(json.dumps(config)), base_folder=r"d:\___PHOTOS",
            declared_config=config,
        )["paths"]

        assert paths["camera_uploads"] == uploads
        assert Path(paths["inbox_folder"]) == Path(r"d:\___PHOTOS") / INBOX

    def test_a_root_outside_photo_roots_is_still_confined(self, tmp_path):
        uploads = r"c:\Users\someone\Dropbox\Camera Uploads"
        config = {
            "paths": {"root_folder": r"c:\__PHOTOS", "camera_uploads": uploads},
            "photo_roots": [r"c:\__PHOTOS", r"d:\___PHOTOS"],
        }

        paths = normalize_config_paths(
            json.loads(json.dumps(config)), base_folder=str(tmp_path / "SCRATCH"),
            declared_config=config,
        )["paths"]

        assert "Dropbox" not in paths["camera_uploads"]

    def test_saving_a_run_on_another_root_keeps_the_usual_root(self, tmp_path):
        (c, d, _nas), config_path = make_roots(tmp_path)
        config = load_config(config_path, base_folder=d)

        save_config(config, config_path, persisted_root=str(c))

        saved = json.loads(config_path.read_text())
        assert saved["paths"]["root_folder"] == str(c)
        assert load_config(config_path)["paths"]["inbox_folder"] == str(c / INBOX)
