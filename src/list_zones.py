"""Print every available IANA timezone name for copy-paste into the ``zones``
alias map in ``config.json``.

The alias map only needs the handful of places you actually go; this is the
lookup you raid when visiting somewhere new. Usage::

    python -m src.list_zones            # all zones, one per line
    python -m src.list_zones Europe     # only zones containing "Europe"
"""

import sys
from zoneinfo import available_timezones


def main(argv: list[str]) -> int:
    needle = argv[0].lower() if argv else None
    zones = sorted(available_timezones())
    matches = [zone for zone in zones if needle is None or needle in zone.lower()]
    for zone in matches:
        print(zone)
    print(f"\n{len(matches)} of {len(zones)} zones", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
