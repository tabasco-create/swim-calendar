# swim-calendar

Filtered copy of the Ryan Tidal Waves SwimTopia calendar with USA Swimming meets
(events titled `*USA*`) removed.

**Subscribe:** `https://tabasco-create.github.io/swim-calendar/swim.ics`

Status page: https://tabasco-create.github.io/swim-calendar/

A GitHub Actions workflow (`.github/workflows/update.yml`) re-runs
`filter_calendar.py` once a day and commits `docs/swim.ics` when events change.
To drop more events, add a pattern to `EXCLUDE_PATTERNS` in `filter_calendar.py`.

## Ryan YMCA pool

`ryan_pool.py` (same daily run) reads the Ryan Family YMCA page on ymcasd.org and writes
`docs/pool.json`: pool hours, the link to this month's pool schedule PDF (lap swim lanes
and family swim times), the notes printed on that PDF, and any closures in the page's
alert boxes. The status page shows it under "Ryan YMCA pool", and the sd-events repo puts
the closures on the tabasco.dev homepage events list. If the page can't be read, the last
good copy stays and the page says so at the top of that section.
