r"""Show what clock every camera was on, folder by folder, across all photo roots.

READ-ONLY (openspec change camera-time-correction, capability
timezone-visualiser). Prints a git-log-like view and writes the same view as an
HTML page:

    python tools\timezone_visualiser.py --year 2026
    python tools\timezone_visualiser.py --from 2026-09-01 --to 2026-09-30 --open
    python tools\timezone_visualiser.py --root "c:\__PHOTOS" --ascii --no-html

Without ``--root`` every configured photo root is scanned; a folder present
under several roots is one row, tagged with each root's drive letter (``NAS``
for a network share). Sidecar reads are cached per root outside the archive.
"""

import argparse
import os
import sys
from pathlib import Path

from clock_tools_common import \
    engine, \
    in_range, \
    load_config, \
    parse_day, \
    report_path, \
    roots_from, \
    scan_roots

clock_view = __import__("importlib").import_module("src.pipeline_stages.clock_view")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", action="append", help="photo root to scan (repeatable; default: all configured)")
    parser.add_argument("--year", action="append", type=int, help="year tree to show (repeatable)")
    parser.add_argument("--from", dest="start", help="first day, YYYY-MM-DD")
    parser.add_argument("--to", dest="end", help="last day, YYYY-MM-DD")
    parser.add_argument("--html", help="where to write the HTML page (default: next to the reports)")
    parser.add_argument("--no-html", action="store_true", help="terminal only")
    parser.add_argument("--open", action="store_true", help="open the HTML page when done")
    parser.add_argument("--ascii", action="store_true", help="plain ASCII glyphs")
    parser.add_argument("--no-cache", action="store_true", help="read every sidecar again")
    parser.add_argument("--config", help="config.json to use")
    parser.add_argument("--timezone", help="a timezone.json to use instead of the repo's (to try one out)")
    args = parser.parse_args(argv)

    config = load_config(args.config, args.timezone)
    model = engine.model_from_config(config)
    for message in model.errors:
        print(f"timezone.json ERROR: {message}")
    if model.errors:
        return 2
    roots = roots_from(config, args.root)
    start, end = parse_day(args.start), parse_day(args.end)
    years = args.year
    if not years and (start or end):
        years = list(range((start or end).year, (end or start).year + 1))

    print(f"Scanning {', '.join(str(root) for root in roots)} ...", file=sys.stderr, flush=True)
    folders = scan_roots(roots, config, years, use_cache=not args.no_cache,
                         progress=lambda message: print("  " + message, file=sys.stderr, flush=True))
    for folder in folders:
        folder.readings = [shot for shot in folder.readings if in_range(shot, start, end)]
    if start or end:
        # Keep the folders with shots in range, and the groups that hold them.
        kept = {folder.relative for folder in folders if folder.readings}
        ancestors = {parent for relative in kept for parent in relative.parents}
        folders = [folder for folder in folders if folder.relative in kept or folder.relative in ancestors]
    labels = clock_view.root_labels(roots)
    view = clock_view.build_view(folders, model, labels)

    encoding = sys.stdout.encoding or "ascii"
    glyphs = clock_view.ASCII if args.ascii else clock_view.UNICODE
    try:
        "".join(glyphs.values()).encode(encoding)
    except UnicodeEncodeError:
        glyphs = clock_view.ASCII
    print("roots: " + "  ".join(f"{label}={root}" for label, root in zip(labels, roots)))
    for line in clock_view.render_text(view, glyphs):
        print(line.encode(encoding, "replace").decode(encoding))

    if not args.no_html:
        scope = (f"roots {', '.join(f'{label}={root}' for label, root in zip(labels, roots))}; years {years or 'all'}; "
                 f"from {args.start or '-'} to {args.end or '-'}")
        page = clock_view.render_html(view, "Camera clocks by folder", scope)
        out = Path(args.html) if args.html else report_path(roots, years, "timezone_view").with_suffix(".html")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        print(f"\nHTML written to {out}")
        if args.open:
            os.startfile(out)  # noqa: S606 -- Windows-only tool, opens the user's browser
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
