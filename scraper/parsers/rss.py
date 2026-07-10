"""Parser RSS generico.

Funziona con qualsiasi feed (Citynews, WordPress, ...).
Problema tipico: i feed di notizie non hanno la data DELL'EVENTO ma quella
di pubblicazione dell'articolo. Quindi:
  1. cerchiamo date in italiano nel titolo/descrizione con dateparser
  2. se non troviamo nulla, usiamo la data di pubblicazione con confidence=low
"""
from datetime import datetime
import html
import re

import feedparser
from dateparser.search import search_dates

from scraper.models import Event, guess_category

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def _find_event_date(text: str) -> datetime | None:
    """Cerca una data futura nel testo (italiano)."""
    try:
        found = search_dates(
            text,
            languages=["it"],
            settings={"PREFER_DATES_FROM": "future", "DATE_ORDER": "DMY"},
        )
    except Exception:
        return None
    if not found:
        return None
    now = datetime.now()
    future = [d for _, d in found if d >= now.replace(hour=0, minute=0)]
    return min(future) if future else None


def parse(source: dict) -> list[Event]:
    feed = feedparser.parse(source["url"])
    events: list[Event] = []

    for entry in feed.entries:
        title = _strip_html(entry.get("title", ""))
        if not title:
            continue
        summary = _strip_html(entry.get("summary", ""))[:600]
        link = entry.get("link", "")
        image = ""
        for enc in entry.get("media_content", []) or []:
            image = enc.get("url", "") or image
        if not image and entry.get("links"):
            for l in entry["links"]:
                if l.get("type", "").startswith("image"):
                    image = l.get("href", "")

        # data evento: prima dal testo, poi fallback su pubblicazione
        event_dt = _find_event_date(f"{title}. {summary}")
        confidence = "high" if event_dt else "low"
        if not event_dt and entry.get("published_parsed"):
            p = entry.published_parsed
            event_dt = datetime(p.tm_year, p.tm_mon, p.tm_mday)

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=link,
            description=summary,
            category=guess_category(f"{title} {summary}", source.get("default_category", "eventi")),
            start=event_dt.isoformat(timespec="seconds") if event_dt else None,
            all_day=bool(event_dt and event_dt.hour == 0),
            date_confidence=confidence,
            image=image,
        ))
    return events
