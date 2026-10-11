# swim-calendar

Filtered copy of the Ryan Tidal Waves SwimTopia calendar with USA Swimming meets
(events titled `*USA*`) removed.

**Subscribe:** `https://tabasco-create.github.io/swim-calendar/swim.ics`

Status page: https://tabasco-create.github.io/swim-calendar/

A GitHub Actions workflow (`.github/workflows/update.yml`) re-runs
`filter_calendar.py` once a day and commits `docs/swim.ics` when events change.
To drop more events, add a pattern to `EXCLUDE_PATTERNS` in `filter_calendar.py`.
