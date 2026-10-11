#!/usr/bin/env python3
"""Download the Ryan Tidal Waves SwimTopia calendar and drop USA Swimming meets.

Writes, for GitHub Pages:
  docs/swim.ics      the filtered calendar feed
  docs/events.json   kept + filtered-out events and status times, for index.html
  docs/changes.json  history of added / removed / changed events
No third-party packages needed.
"""
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SOURCE_URL = "https://ryantidalwaves.swimtopia.com/calendar_events.ics"
SITE = Path("docs")
OUTPUT = SITE / "swim.ics"
CAL_NAME = "Ryan Tidal Waves (no USA meets)"
MAX_HISTORY = 50

# An event is dropped if its title matches any of these (case-insensitive).
EXCLUDE_PATTERNS = [
    r"^\W*USA\W",  # titles tagged *USA*
    # r"SI Winter Age Group",  # untagged USA meets can be added here
]

TRACKED_FIELDS = ["title", "start", "end", "time", "location"]


def unfold(lines):
    """Join ICS folded lines (continuations start with a space or tab)."""
    out = []
    for line in lines:
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def ics_unescape(value):
    value = re.sub(r"\\([nN])", "\n", value)
    value = re.sub(r"\\(.)", r"\1", value)
    return value.replace("\\", "").replace("&nbsp;", " ").strip()


def props(event_lines):
    """Map property name -> (params, raw value) for one VEVENT."""
    d = {}
    for line in unfold(event_lines):
        if ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, _, params = head.partition(";")
        d.setdefault(name.upper(), (params.upper(), value))
    return d


def parse_dt(params_value):
    params, value = params_value
    value = value.strip()
    if "VALUE=DATE" in params or len(value) == 8:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8])), None, True
    dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    return dt.date(), dt.time(), False


def fmt_time(t):
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def to_record(event_lines):
    p = props(event_lines)
    title = ics_unescape(p.get("SUMMARY", ("", ""))[1])
    start_d, start_t, all_day = parse_dt(p["DTSTART"])
    end_d = start_d
    if "DTEND" in p:
        end_d, _, end_all_day = parse_dt(p["DTEND"])
        if end_all_day and end_d > start_d:
            end_d -= timedelta(days=1)  # all-day DTEND is exclusive
    return {
        "uid": p.get("UID", ("", title))[1].strip(),
        "title": title,
        "start": start_d.isoformat(),
        "end": max(end_d, start_d).isoformat(),
        "time": None if all_day or start_t is None else fmt_time(start_t),
        "location": ics_unescape(p.get("LOCATION", ("", ""))[1]),
        "description": ics_unescape(p.get("DESCRIPTION", ("", ""))[1]),
    }


def clean_summary(event_lines):
    """SwimTopia double-escapes the * in titles, so calendars show \\*YMCA\\*."""
    return [re.sub(r"\\\\\*", "*", l) if l.upper().startswith("SUMMARY") else l
            for l in event_lines]


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def diff(old_events, new_events):
    old = {e["uid"]: e for e in old_events}
    new = {e["uid"]: e for e in new_events}
    added = [e for u, e in new.items() if u not in old]
    removed = [e for u, e in old.items() if u not in new]
    changed = []
    for u, e in new.items():
        if u in old:
            ch = [{"field": f, "from": old[u].get(f), "to": e.get(f)}
                  for f in TRACKED_FIELDS if old[u].get(f) != e.get(f)]
            if ch:
                changed.append({"event": e, "changes": ch})
    return added, removed, changed


def main():
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "calendar-filter"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    if "BEGIN:VCALENDAR" not in raw:
        sys.exit("Source did not return a calendar; leaving existing files alone.")

    patterns = [re.compile(p, re.I) for p in EXCLUDE_PATTERNS]
    out, event, kept, dropped = [], None, [], []

    for line in raw.splitlines():
        if line.startswith("BEGIN:VEVENT"):
            event = [line]
        elif line.startswith("END:VEVENT") and event is not None:
            event.append(line)
            rec = to_record(event)
            if any(p.search(rec["title"]) for p in patterns):
                dropped.append(rec)
            else:
                out.extend(clean_summary(event))
                kept.append(rec)
            event = None
        elif event is not None:
            event.append(line)
        elif line.startswith(("X-WR-CALNAME:", "NAME:")):
            out.append(line.split(":", 1)[0] + ":" + CAL_NAME)
        else:
            out.append(line)

    SITE.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\r\n".join(out) + "\r\n", encoding="utf-8")

    key = lambda e: (e["start"], e["title"])
    kept.sort(key=key)
    dropped.sort(key=key)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ev_path, ch_path = SITE / "events.json", SITE / "changes.json"
    old_doc = load_json(ev_path, {})
    history = load_json(ch_path, {}).get("history", [])

    updated_at = old_doc.get("updated_at", now)
    if old_doc.get("events") is not None:
        added, removed, changed = diff(old_doc["events"], kept)
        if added or removed or changed:
            updated_at = now
            history.insert(0, {"at": now, "added": added, "removed": removed, "changed": changed})
            print(f"Changes: +{len(added)} -{len(removed)} ~{len(changed)}")
        else:
            print("No changes since last update.")

    doc = {
        "checked_at": now,
        "updated_at": updated_at,
        "tracking_since": old_doc.get("tracking_since", now),
        "events": kept,
        "filtered_out": dropped,
    }
    ev_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    ch_path.write_text(json.dumps({"history": history[:MAX_HISTORY]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")

    print(f"Kept {len(kept)} events, dropped {len(dropped)}:")
    for e in dropped:
        print("  -", e["title"])


if __name__ == "__main__":
    main()
