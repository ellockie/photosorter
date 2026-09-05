"""T8 -- one definition per rule, held by a test rather than by good intentions.

ARCHIVE_STANDARD.md section 7 lists what this repo has consolidated and what it
has deliberately left duplicated. Two of those entries cannot be enforced by
the import graph alone, so they are enforced here:

1. **The file checksum.** Four copies of "MD5 a file in chunks" agreed on the
   algorithm and disagreed on the chunk size. ``src/utils/checksums.py`` is the
   one implementation; ``core.file_md5``, ``companion_matching.default_checksum``
   and ``legacy_videos._default_checksum`` are names for it.

2. **The leading-stamp grammar.** ``grouping_names`` spells out the same three
   fragments ``stamps`` defines, on purpose: it imports nothing from the project
   so a maintenance tool can load it by file path, and importing ``stamps``
   would pull the package ``__init__`` in behind it. That exception is accepted
   -- but an exception nobody is testing is just drift with a docstring, so the
   two spellings are compared character for character here.
"""

import ast
import inspect
import sys
from pathlib import Path

import pytest

from src.pipeline_stages import grouping_names, stamps
from src.utils import checksums


# --------------------------------------------------------------------------
# 1. The checksum
# --------------------------------------------------------------------------

def test_every_pipeline_checksum_name_is_the_one_function():
    """Same object, not merely same behaviour -- an alias cannot drift."""
    from src.core import file_md5
    from src.pipeline_stages.companion_matching import default_checksum
    from src.pipeline_stages.legacy_videos import _default_checksum

    assert file_md5 is checksums.file_md5
    assert default_checksum is checksums.file_md5
    assert _default_checksum is checksums.file_md5


def test_the_legacy_cli_reads_the_same_source_file():
    """``common/common.py`` runs with ``src`` on sys.path, so it spells the
    module ``utils.checksums`` where the pipeline spells it
    ``src.utils.checksums``. Two module objects, one file on disk -- the same
    arrangement ``constants.py`` has with ``months.py``, and all T8 asks for.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    try:
        from common.common import file_md5 as legacy_file_md5
    finally:
        sys.path.pop(0)

    assert (Path(inspect.getsourcefile(legacy_file_md5)).resolve()
            == Path(inspect.getsourcefile(checksums.file_md5)).resolve())


def test_no_module_hashes_a_file_of_its_own():
    """No ``hashlib.md5()`` anywhere but the one module (and this test)."""
    root = Path(__file__).resolve().parents[1]
    allowed = {(root / "src" / "utils" / "checksums.py").resolve()}
    offenders = []
    for path in list((root / "src").rglob("*.py")) + list((root / "tools").rglob("*.py")):
        if "__pycache__" in path.parts or path.resolve() in allowed:
            continue
        if "hashlib.md5(" in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], (
        "these hash a file themselves instead of calling utils.checksums."
        "file_md5 (T8): " + ", ".join(offenders)
    )


def test_the_checksum_still_matches_hashlib(tmp_path):
    """The consolidation kept the digest, not just the call sites."""
    import hashlib

    payload = b"the quick brown fox" * 1000
    target = tmp_path / "probe.bin"
    target.write_bytes(payload)

    expected = hashlib.md5(payload).hexdigest()
    assert checksums.file_md5(target) == expected
    # The chunk size the caller passes must not change the answer -- that is
    # what made four copies with three chunk sizes survivable, and it is the
    # property to keep now that they are one.
    assert checksums.file_md5(target, 7) == expected
    assert checksums.file_md5(str(target), len(payload) * 4) == expected


# --------------------------------------------------------------------------
# 2. The leading-stamp grammar
# --------------------------------------------------------------------------

PATTERN_PAIRS = [
    ("_DATE_PATTERN", "DATE_PATTERN"),
    ("_DATE_TIME_SEPARATOR_PATTERN", "DATE_TIME_SEPARATOR_PATTERN"),
    ("_STAMP_CAPTURE_PATTERN", "STAMP_CAPTURE_PATTERN"),
]


@pytest.mark.parametrize("local_name, stamps_name", PATTERN_PAIRS)
def test_grouping_names_spells_the_stamp_fragments_identically(local_name, stamps_name):
    assert getattr(grouping_names, local_name) == getattr(stamps, stamps_name), (
        f"grouping_names.{local_name} has drifted from stamps.{stamps_name}. "
        "The duplication is deliberate (T8, accepted exception) -- the drift "
        "is not."
    )


def test_the_compiled_leading_stamp_regexes_are_equal():
    assert (grouping_names._LEADING_STAMP_RE.pattern
            == stamps.LEADING_STAMP_RE.pattern)


@pytest.mark.parametrize("name", [
    "2026-08-20_(Thu)__09.14.02 - Norway",
    "2026-08-20 (Thu) 09.14.02",
    "2026-08-20__09.14.02",
    "2026-08-20_(Thu)__09.14.02#16.20.31 - ____GROUP____(d=3)",
    "not a folder",
    "08. August",
])
def test_both_leading_stamp_regexes_read_a_name_the_same_way(name):
    ours = grouping_names._LEADING_STAMP_RE.match(name)
    theirs = stamps.LEADING_STAMP_RE.match(name)
    assert (ours is None) == (theirs is None)
    if ours is not None:
        assert ours.groups() == theirs.groups()


def test_the_duplication_is_still_the_reason_for_itself():
    """``grouping_names`` and ``stamps`` import nothing from this project.

    That is the only justification for the copy; if either grows a project
    import the copy should be replaced by that import instead.
    """
    for module in (grouping_names, stamps):
        source = Path(inspect.getsourcefile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:                   # a relative import is ours
                    imported.append("." * node.level + (node.module or ""))
                elif node.module:
                    imported.append(node.module)
        project = [name for name in imported
                   if name.startswith((".", "src", "common", "constants",
                                       "utils", "pipeline_stages"))]
        assert project == [], (
            f"{module.__name__} now imports {project}; it is no longer a leaf "
            "module, so the duplicated stamp fragments have lost their excuse."
        )
