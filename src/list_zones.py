"""List countries and their time zones, for ``timezone.json``.

A trip or ``home`` names a country by its two-letter code. A country with more
than one distinct time zone has to be named by region instead, and this is the
list to copy one from. Usage::

    python -m src.list_zones            # every country: code, name, zone(s)
    python -m src.list_zones pol        # countries/zones containing "pol"
    python -m src.list_zones US         # one country's zones
"""

import sys

from src.pipeline_stages.timezone_engine import \
    country_tables, \
    country_zones


def main(argv: list[str]) -> int:
    needle = argv[0].lower() if argv else None
    names, _ = country_tables()
    shown = 0
    for code in sorted(names):
        zones = country_zones(code)
        line = f"{code}  {names[code]}"
        text = (line + " " + " ".join(zones)).lower()
        if needle is not None and needle != code.lower() and needle not in text:
            continue
        if len(zones) == 1:
            print(f"{line:<46} {zones[0]}")
        else:
            print(f"{line:<46} several zones -- name a region:")
            for zone in zones:
                print(f"{'':<48}{zone}")
        shown += 1
    print(f"\n{shown} of {len(names)} countries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
