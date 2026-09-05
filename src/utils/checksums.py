"""MD5 of a file — defined here and nowhere else (T8).

Four copies of "hash a file in chunks" lived in this repo: ``core.file_md5``,
``common/common.py``'s, ``companion_matching.default_checksum`` and
``legacy_videos._default_checksum``. They agreed on the algorithm and disagreed
on the chunk size, which is the harmless-looking kind of drift: nothing breaks,
and then one of them is changed and the others are not.

This is a **leaf module**: it imports nothing but the standard library, so both
worlds can reach it — the legacy CLI, which runs with ``src`` on ``sys.path``
and spells it ``utils.checksums``, and the pipeline, which spells it
``src.utils.checksums``. In particular ``companion_matching`` may import it and
stay the dependency-free module its docstring promises.

The digest is MD5 because that is what the archive already holds: F4's
``_DUPE_<md5>`` and ``_DIFFERS_<md5>`` collision suffixes are written into
filenames on disk, and every hash in a run journal is one. The question asked
is always "are these two files the same file", never "did someone tamper with
this one", so the collision resistance MD5 has lost is not resistance this
archive was relying on.
"""

import hashlib
from pathlib import Path

# Big enough that a ".lrv" proxy on a network share is not read a page at a
# time, small enough that a run over a year of RAWs does not hold one in
# memory. ``safety.hash_chunk_size`` in config.json overrides it for callers
# that have a config in hand; a caller with none gets this.
DEFAULT_CHUNK_SIZE = 1024 * 1024


def file_md5(path: str | Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Return the MD5 hex digest of ``path``, read in chunks."""
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
