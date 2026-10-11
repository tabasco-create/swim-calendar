#!/usr/bin/env python3
"""Download the Ryan Tidal Waves SwimTopia calendar and drop USA Swimming meets.

Writes docs/swim.ics for GitHub Pages. No third-party packages needed.
"""
import re
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://ryantidalwaves.swimtopia.com/calendar_events.ics"
OUTPUT = Path("docs/swim.ics")
CAL_NAME = "Ryan Tidal Waves (no USA meets)"

# An event is dropped if its title matches any of these (case-insensitive).
EXCLUDE_PATTERNS = [
    r"^\W*USA\W",  # titles tagged *USA*
    # r"SI Winter Age Group",  # untagged USA meets can be added here
]


def unfold(lines):
    """Join ICS folded lines (continuations start with a space or tab)."""
    out = []
    for line in lines:
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def summary_of(event_lines):
    for line in unfold(event_lines):
        if line.upper().startswith("SUMMARY"):
            value = line.split(":", 1)[1] if ":" in line else ""
            return value.replace("\\", "")
    return ""


def main():
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "calendar-filter"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    if "BEGIN:VCALENDAR" not in raw:
        sys.exit("Source did not return a calendar; leaving existing file alone.")

    patterns = [re.compile(p, re.I) for p in EXCLUDE_PATTERNS]
    out, event, kept, dropped = [], None, 0, []

    for line in raw.splitlines():
        if line.startswith("BEGIN:VEVENT"):
            event = [line]
        elif line.startswith("END:VEVENT") and event is not None:
            event.append(line)
            title = summary_of(event)
            if any(p.search(title) for p in patterns):
                dropped.append(title)
            else:
                out.extend(event)
                kept += 1
            event = None
        elif event is not None:
            event.append(line)
        elif line.startswith(("X-WR-CALNAME:", "NAME:")):
            out.append(line.split(":", 1)[0] + ":" + CAL_NAME)
        else:
            out.append(line)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\r\n".join(out) + "\r\n", encoding="utf-8")
    print(f"Kept {kept} events, dropped {len(dropped)}:")
    for t in dropped:
        print("  -", t)


if __name__ == "__main__":
    main()
