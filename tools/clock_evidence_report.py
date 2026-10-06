r"""Report where the archive suggests camera clocks were changed, or trips began.

READ-ONLY. Changes no file and no setting; every finding is an indication, with
a ready-to-paste ``timezone.json`` line for a person to confirm (openspec
change camera-time-correction, capability clock-evidence-report).

    python tools\clock_evidence_report.py --year 2026
    python tools\clock_evidence_report.py --from 2025-06-01 --to 2025-09-30 --camera ILC7R5
    python tools\clock_evidence_report.py --root "c:\__PHOTOS" --all-findings

Without ``--root`` every configured photo root is scanned; a folder present
under several roots is read once. Sidecar reads are cached per root outside the
archive, so a second run over the NAS is quick.
"""

import argparse
import sys

from clock_tools_common import \
    engine, \
    in_range, \
    load_config, \
    parse_day, \
    report_path, \
    roots_from, \
    scan_roots

clock_evidence = __import__("importlib").import_module("src.pipeline_stages.clock_evidence")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", action="append", help="photo root to scan (repeatable; default: all configured)")
    parser.add_argument("--year", action="append", type=int, help="year tree to scan (repeatable)")
    parser.add_argument("--from", dest="start", help="first day, YYYY-MM-DD")
    parser.add_argument("--to", dest="end", help="last day, YYYY-MM-DD")
    parser.add_argument("--camera", action="append", help="camera symbol to report on (repeatable)")
    parser.add_argument("--all-findings", action="store_true", help="also list findings already recorded")
    parser.add_argument("--out", help="report file (default: the year's __LOGS, or a per-user folder)")
    parser.add_argument("--no-cache", action="store_true", help="read every sidecar again")
    parser.add_argument("--config", help="config.json to use")
    parser.add_argument("--timezone", help="a timezone.json to use instead of the repo's (to try one out)")
    args = parser.parse_args(argv)

    config = load_config(args.config, args.timezone)
    model = engine.model_from_config(config)
    for message in model.errors:
        print(f"timezone.json ERROR: {message}")
    roots = roots_from(config, args.root)
    start, end = parse_day(args.start), parse_day(args.end)
    years = args.year
    if not years and (start or end):
        years = list(range((start or end).year, (end or start).year + 1))

    print(f"Scanning {', '.join(str(root) for root in roots)} ...", flush=True)
    folders = scan_roots(roots, config, years, use_cache=not args.no_cache,
                         progress=lambda message: print("  " + message, flush=True))
    readings = [shot for folder in folders for shot in folder.readings
                if in_range(shot, start, end) and (not args.camera or shot.camera in args.camera)]
    findings = clock_evidence.find_evidence(readings, model)
    shown = [finding for finding in findings if args.all_findings or not finding.recorded]

    header = [
        "CLOCK EVIDENCE REPORT  (indications only -- nothing was changed)",
        f"roots: {', '.join(str(root) for root in roots)}",
        f"scope: years {years or 'all'}  from {args.start or '-'}  to {args.end or '-'}  cameras {args.camera or 'all'}",
        f"{len(folders)} folders, {len(readings)} shots; {len(findings)} findings, "
        f"{sum(1 for f in findings if f.recorded)} already recorded in timezone.json",
        "",
        "certain adjustment : reading went back while the shutter counter went forward",
        "possible adjustment: the camera's declared offset changed (never trusted on its own)",
        "trip start / end   : a phone's offset changed",
        "Paste a line into timezone.json only after checking it; replace ?? with the clock or country.",
        "",
    ]
    body = clock_evidence.format_findings(shown) or ["No new findings."]
    text = "\n".join(header + body)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "ascii", "replace").decode(sys.stdout.encoding or "ascii"))

    out = report_path(roots, years, "clock_evidence") if not args.out else __import__("pathlib").Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\nReport written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
