#!/usr/bin/env python3
"""Ryan Family YMCA pool info: hours, this month's pool schedule PDF, and closures.

Reads the Ryan YMCA location page on ymcasd.org (and the pool schedule PDF it links to)
once a day and writes, for GitHub Pages:
  docs/pool.json   read by index.html (the swim page) and by the sd-events repo,
                   which puts the closures on the tabasco.dev homepage events list

If the page can't be reached, the last good copy is kept and the error is recorded,
so the swim page can say so at the top instead of quietly showing stale info.

The PDF notes need pypdf (`pip install pypdf`, done in the workflow). Without it the
link and closures still work; only the notes from inside the PDF are skipped.
"""
import html
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PAGE_URL = "https://www.ymcasd.org/locations/t-claude-and-gladys-b-ryan-family-ymca/"
SITE = Path("docs")
OUTPUT = SITE / "pool.json"
UA = "Mozilla/5.0 (compatible; tabasco.dev swim page; github.com/tabasco-create/swim-calendar)"

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTH_DAY_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?", re.I)
# PDF notes worth showing (sentences that mention any of these)
NOTE_RE = re.compile(r"closure|closed|closing|reopen|family swim|recommended times|holiday|replaster", re.I)
CLOSURE_RE = re.compile(r"\bclos(ed|ure|ures|ing)\b", re.I)


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def text_of(fragment):
    s = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", fragment)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    lines = [re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"[ \t]+", " ", l)).strip() for l in s.split("\n")]
    return "\n".join(l for l in lines if l)


def guess_year(month, day, today):
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d >= today - timedelta(days=60):
            return d
    return None


def date_range(text, today):
    """First date and (optional) end date mentioned in text: "Monday, December 14 through
    Friday December 18, 2026", "Dec 14–18", "12/14 ... 12/18"."""
    found = list(MONTH_DAY_RE.finditer(text))
    if found:
        def to_date(m, ref):
            mo, d = MONTHS[m.group(1)[:3].lower()], int(m.group(2))
            if m.group(3):
                try:
                    return date(int(m.group(3)), mo, d)
                except ValueError:
                    return None
            return guess_year(mo, d, ref)
        # a year written only on the end date ("December 14 through December 18, 2026")
        year = next((int(m.group(3)) for m in found[:2] if m.group(3)), None)
        start = to_date(found[0], today)
        if year and start and not found[0].group(3):
            try:
                start = start.replace(year=year)
            except ValueError:
                pass
        end = to_date(found[1], start or today) if len(found) > 1 else None
        if not end and start:
            span = re.search(re.escape(found[0].group(0)) + r"\s*[–—-]\s*(\d{1,2})\b", text)
            if span:
                try:
                    end = start.replace(day=int(span.group(1)))
                except ValueError:
                    end = None
        if start and end and end < start:
            end = None
        return start, end
    nums = re.findall(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if nums:
        def to_date(n):
            mo, d = int(n[0]), int(n[1])
            if not (1 <= mo <= 12):
                return None
            if n[2]:
                y = int(n[2]) + (2000 if len(n[2]) == 2 else 0)
                try:
                    return date(y, mo, d)
                except ValueError:
                    return None
            return guess_year(mo, d, today)
        start = to_date(nums[0])
        end = to_date(nums[1]) if len(nums) > 1 else None
        return start, (end if start and end and end >= start else None)
    return None, None


def parse_alerts(page, today):
    """The yellow alert boxes at the top of the location page."""
    alerts = []
    for block in re.findall(r'(?is)<div class="ymca-alert">(.*?)</div>\s*</div>\s*</div>', page):
        label = re.search(r'(?is)class="[^"]*ymca-alert-label[^"]*"[^>]*>(.*?)</', block)
        body = re.search(r'(?is)class="[^"]*ymca-alert-content[^"]*"[^>]*>(.*)', block)
        label = text_of(label.group(1)) if label else ""
        body = text_of(body.group(1)) if body else ""
        if not (label or body):
            continue
        a = {"label": label, "text": body}
        if CLOSURE_RE.search(f"{label} {body}"):
            start, end = date_range(body, today)
            if not start:
                start, end = date_range(label, today)
            if start:
                a["closed_from"] = start.isoformat()
                a["closed_to"] = (end or start).isoformat()
                a["pool"] = bool(re.search(r"\b(pool|aquatic|swim)", f"{label} {body}", re.I))
        alerts.append(a)
    return alerts


def parse_hours(page):
    """The "Pool Hours" list in the location page's POOL & SPECIAL HOURS panel."""
    i = page.find("Pool Hours")
    if i < 0:
        return []
    lines = text_of(page[i:i + 6000]).split("\n")[1:]
    hours = []
    day_re = re.compile(r"^(sun|mon|tue|wed|thu|fri|sat)[a-z]*(\s*[-–&,]\s*(sun|mon|tue|wed|thu|fri|sat)[a-z]*)*$", re.I)
    time_re = re.compile(r"\d{1,2}(:\d{2})?\s*[ap]\.?m", re.I)
    k = 0
    while k + 1 < len(lines) and len(hours) < 7:
        if day_re.match(lines[k]) and time_re.search(lines[k + 1]):
            hours.append({"days": lines[k], "hours": re.sub(r"\s*-\s*", "–", lines[k + 1])})
            k += 2
        elif hours:
            break
        else:
            k += 1
    return hours


def find_link(page, pattern):
    for href in re.findall(r'href="([^"]+)"', page):
        href = html.unescape(href)
        if re.search(pattern, href, re.I):
            return urllib.parse.urljoin(PAGE_URL, href)
    return None


def month_label(url):
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_ ]?(\d{4})", url or "", re.I)
    if not m:
        return None
    name = ["January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December"][MONTHS[m.group(1)[:3].lower()] - 1]
    return f"{name} {m.group(2)}"


def pdf_notes(url, today):
    """Effective date and the closure / family-swim notes printed on the schedule PDF."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"error": "pypdf not installed"}
    try:
        reader = PdfReader(io.BytesIO(get(url, binary=True)))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as ex:
        return {"error": f"couldn't read the PDF: {str(ex)[:150]}"}
    out = {}
    eff = re.search(r"Effective\s+(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if eff:
        try:
            out["effective"] = date(int(eff.group(3)), int(eff.group(1)), int(eff.group(2))).isoformat()
        except ValueError:
            pass
    flat = re.sub(r"\s+", " ", text)
    sentences = re.split(r"(?<=[.!])\s+(?=[A-Z])", flat)
    notes = []
    for s in sentences:
        s = s.strip()
        if "." in s[:-1]:
            s = s[:s.rfind(".") + 1]   # drop schedule-grid text that follows the last sentence
        if 25 <= len(s) <= 300 and NOTE_RE.search(s) and s not in notes:
            notes.append(s)
    out["notes"] = notes[:6]
    return out


def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(timezone(timedelta(hours=-8))).date()
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        old = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}

    try:
        page = get(PAGE_URL)
        if "Ryan" not in page:
            raise RuntimeError("the page came back without the Ryan YMCA content")
        pdf = find_link(page, r"Pool-Schedule[^\"']*\.pdf$")
        doc = {
            "ok": True,
            "checked_at": stamp,
            "updated_at": stamp,
            "page_url": PAGE_URL,
            "hours": parse_hours(page),
            "schedule_pdf": pdf,
            "schedule_month": month_label(pdf),
            "alerts": parse_alerts(page, today),
        }
        if pdf:
            doc["pdf"] = pdf_notes(pdf, today)
        # closures that are over aren't worth showing
        doc["closures"] = [
            {"title": a["label"] or "Closed", "from": a["closed_from"], "to": a["closed_to"],
             "pool": a["pool"], "text": a["text"]}
            for a in doc["alerts"] if a.get("closed_to") and a["closed_to"] >= today.isoformat()
        ]
        if not pdf:
            doc["warning"] = "No pool schedule PDF link found on the Ryan YMCA page."
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as ex:
        doc = dict(old) if old else {"page_url": PAGE_URL}
        doc["ok"] = False
        doc["checked_at"] = stamp
        doc["error"] = f"Couldn't read the Ryan YMCA page: {str(ex)[:200]}"
        print(doc["error"], file=sys.stderr)

    SITE.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc.get(k) for k in ("ok", "schedule_pdf", "closures", "hours", "error")}, indent=1))


if __name__ == "__main__":
    main()
