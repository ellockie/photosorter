import json
import re
from pathlib import Path

from src.core import file_md5, safe_delete

# Leading date or date-time part of a folder name, e.g.
# "2024-01-15 Birthday", "2024-01-15_18.30 Party", "2024.01.15-Trip".
DATE_PREFIX_PATTERN = re.compile(
    r"^\s*\d{4}[-_. ]\d{2}[-_. ]\d{2}"          # date
    r"(?:[-_. ]*\(\w{3}\))?"                     # optional (Ddd)
    r"(?:[-_. ]+\d{2}[._:h]\d{2}(?:[._:]\d{2})?)?"  # optional time
    r"[-_. ]*"
)


def provenance_settings(config: dict) -> dict:
    return config.get("provenance", {})


def dont_move_folder(config: dict) -> str:
    return provenance_settings(config).get("dont_move_folder", "__DONT_MOVE")


def geodata_extensions(config: dict) -> set[str]:
    return {
        value.lower()
        for value in provenance_settings(config).get("geodata_extensions", [".gpx"])
    }


def extract_origin_label(folder_name: str) -> str | None:
    label = DATE_PREFIX_PATTERN.sub("", folder_name).strip(" -_.")
    return label or None


def journal_dir(config: dict) -> Path:
    working = Path(config["paths"]["working_folder"])
    return working / provenance_settings(config).get("journal_folder", ".JOURNAL")


def journal_file(config: dict, run_id: str) -> Path:
    return journal_dir(config) / f"{run_id}.jsonl"


def append_journal_record(path: str | Path, record: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handler:
        handler.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_journal_records(config: dict) -> list[dict]:
    records = []
    directory = journal_dir(config)
    if not directory.exists():
        return records
    for journal in sorted(directory.glob("*.jsonl")):
        with journal.open("r", encoding="utf-8") as handler:
            for line in handler:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def renamed_sidecar_path(sidecar_path: Path, old_primary_name: str, new_primary_name: str) -> Path:
    # Sidecars embed the full primary filename (e.g. IMG_001.jpg._exif), so the
    # whole primary-name prefix must be substituted, not just the stem.
    if sidecar_path.name.startswith(old_primary_name):
        remainder = sidecar_path.name[len(old_primary_name):]
        return sidecar_path.with_name(new_primary_name + remainder)
    old_stem = Path(old_primary_name).stem
    new_stem = Path(new_primary_name).stem
    if sidecar_path.name.startswith(old_stem):
        remainder = sidecar_path.name[len(old_stem):]
        return sidecar_path.with_name(new_stem + remainder)
    return sidecar_path.with_name(new_primary_name + sidecar_path.suffix)


def resolve_sidecar_target(source: Path, target: Path) -> Path | None:
    """Decide where a sidecar should land when `target` may already be taken.

    A sidecar's name always mirrors its image's final name, and the collision
    resolver guarantees image names are unique, so a sidecar-name clash can only
    be a stale orphan left by an earlier run. Sidecars carry no hash of their own
    (only the image name they mirror), so we never compute or embed one here:
    - target free               -> use it
    - identical content exists  -> return None; the incoming copy is redundant
                                   and the caller should drop it (one shot must
                                   never accumulate multiple sidecars)
    - different content exists  -> the existing file is a stale orphan from a
                                   prior run; delete it and reuse the same name
                                   (the current image's sidecar is authoritative)
    """
    if target == source or not target.exists():
        return target
    if file_md5(source) != file_md5(target):
        safe_delete(target)
    else:
        return None
    return target


def rewrite_sidecar_path_fields(sidecar_path: Path, image_name: str, image_dir: str) -> None:
    """Correct the volatile `File Name` / `Directory` fields in an _exif sidecar.

    ExifTool writes these from the pre-rename inbox path because the metadata
    pass must run before the rename (it feeds the new filename). After the image
    reaches its final name and location we patch just these two path-derived
    lines so the sidecar reflects the renamed file; every other field is
    intrinsic to the pixels and is left exactly as ExifTool produced it.
    """
    if not sidecar_path.exists():
        return
    try:
        text = sidecar_path.read_text(encoding="iso-8859-1")
    except OSError:
        return
    # "File Name" / "Directory" are matched exactly (note the colon), so sibling
    # System fields like "File Modification Date/Time" are never touched.
    text = re.sub(r"(?m)^(File Name\s+: ).*$", lambda m: m.group(1) + image_name, text)
    text = re.sub(r"(?m)^(Directory\s+: ).*$", lambda m: m.group(1) + image_dir, text)
    sidecar_path.write_text(text, encoding="iso-8859-1")


def sidecar_candidates(media_path: Path, config: dict) -> list[Path]:
    """Pre-existing metadata files belonging to a media file.

    Two naming patterns are recognized:
    - full-name sidecars: IMG_001.jpg -> IMG_001.jpg._exif
    - stem sidecars:      IMG_001.jpg -> IMG_001.xmp
    """
    sidecar_extensions = config.get("extensions", {}).get("sidecars", ["._exif"])
    candidates = []
    for extension in sidecar_extensions:
        candidates.append(media_path.with_name(media_path.name + extension))
        candidates.append(media_path.with_name(media_path.stem + extension))
    seen = set()
    unique = []
    for candidate in candidates:
        if candidate not in seen and candidate != media_path:
            seen.add(candidate)
            unique.append(candidate)
    return unique
