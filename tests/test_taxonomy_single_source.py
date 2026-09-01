"""The taxonomy has exactly one definition, and it matches ARCHIVE_STANDARD.md.

Rule T8: a convention defined twice drifts, and half the pipeline ends up writing
names the other half cannot parse. The taxonomy was previously spelled out both
in ``taxonomy.py`` and as a literal inside ``core.py``'s ``default_config()``,
with nothing holding the two equal — these tests are what holds them now.
"""

import ast
import re
from pathlib import Path

from src.core import default_config
from src.pipeline_stages.taxonomy import \
    DEFAULT_TAXONOMY, \
    LEGACY_TAXONOMY, \
    taxonomy_dir_names, \
    taxonomy_folder

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDARD = REPO_ROOT / "ARCHIVE_STANDARD.md"


def _standard_block() -> str:
    text = STANDARD.read_text(encoding="utf-8")
    return re.search(r"```yaml\n(.*?)```", text, re.S).group(1)


def _standard_list(key: str) -> set[str]:
    """The folder names under one key of the section 8 subfolders block.

    Hand-parsed rather than via PyYAML: the project has no YAML dependency and
    this is a flat list of quoted strings.
    """
    block = _standard_block()
    section = re.search(
        rf"^  {key}:.*?\n((?:    - \"[^\"]+\".*\n)+)", block, re.M)
    assert section, f"section 8 has no subfolders.{key} list"
    return set(re.findall(r'- "([^"]+)"', section.group(1)))


def test_default_config_does_not_restate_the_taxonomy():
    # The whole point: one definition. A "taxonomy" block in the defaults would
    # be a second list to keep in step, and save_config() would bake a stale
    # copy of it into every config.json it writes.
    assert "taxonomy" not in default_config()


def test_taxonomy_folder_resolves_without_any_config():
    # With no block in the defaults, every lookup must still answer from
    # DEFAULT_TAXONOMY rather than raising.
    config = default_config()
    for key, name in DEFAULT_TAXONOMY.items():
        assert taxonomy_folder(config, key) == name


def test_config_may_still_override_one_key():
    assert taxonomy_folder({"taxonomy": {"raw": "__ORIGINALS"}}, "raw") == "__ORIGINALS"
    # ...without disturbing its neighbours.
    assert taxonomy_folder({"taxonomy": {"raw": "__ORIGINALS"}}, "exif") == "__EXIF"


def test_code_matches_the_standard():
    # Every name the code carries must be documented; nothing is "disputed"
    # any more, so the two lists match exactly.
    documented = (_standard_list("tool_written")
                  | _standard_list("hand_curated")
                  )
    assert set(DEFAULT_TAXONOMY.values()) == documented


def test_legacy_names_match_the_standard():
    assert set(LEGACY_TAXONOMY.values()) == _standard_list("legacy")


def test_retired_video_folders_are_read_but_never_written():
    # S5. __VIDEOS / __EXTRACTED_VIDEOS are gone from the set anything writes...
    written = set(DEFAULT_TAXONOMY.values())
    assert "__VIDEOS" not in written
    assert "__EXTRACTED_VIDEOS" not in written
    # ...but a folder from an older archive is still recognised, so it is not
    # reported as malformed and its companions can still be reunited.
    recognised = taxonomy_dir_names({})
    assert {"__VIDEOS", "__EXTRACTED_VIDEOS"} <= recognised
    assert {"__VIDEOS_TO_RENAME", "__VIDEOS_EXTRACTED"} <= recognised


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids() of the string constants that are docstrings, not values."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                found.add(id(first.value))
    return found


def test_no_stage_hardcodes_a_taxonomy_folder_name():
    """S4: names come from taxonomy.py, never from a literal in a stage.

    Parsed rather than grepped, so prose in a docstring or comment does not
    read as code — it is a *value* in the source that must not be a second copy.
    """
    names = set(DEFAULT_TAXONOMY.values()) | set(LEGACY_TAXONOMY.values())
    offenders = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path.name == "taxonomy.py" or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            # "sortHDRfiles (cleaner).py" is Python 2 and does not parse. It is
            # standalone legacy, imported by nothing, and predates the taxonomy.
            continue
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value in names and id(node) not in docstrings):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {node.value}")
    assert not offenders, "taxonomy folder names hardcoded outside taxonomy.py:\n" + \
        "\n".join(offenders)


def test_month_folders_have_one_definition():
    """P3/T8: the month names lived in constants.py and legacy.py both.

    constants.py cannot import from src.pipeline_stages (that package's
    __init__ imports every stage, and legacy.py imports constants.py back), and
    legacy.py should not pay constants.py's PHOTO_BASE_FOLDER assertion just to
    spell "05. May" — so the definition sits in its own leaf module and both
    import it.
    """
    from src.constants import months
    from src.constants.constants import MONTH_FOLDERS as via_constants
    from src.pipeline_stages.legacy import MONTH_FOLDERS as via_legacy

    assert via_constants is months.MONTH_FOLDERS
    assert via_legacy is months.MONTH_FOLDERS
    assert months.MONTH_FOLDERS["05"] == "05. May"

    # Only the leaf module spells the names out.
    sources = [
        path for path in (REPO_ROOT / "src").rglob("*.py")
        if "__pycache__" not in path.parts
        and "01. January" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert [path.name for path in sources] == ["months.py"]
