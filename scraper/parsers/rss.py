"""Parser RSS generico.

Funziona con qualsiasi feed (Citynews, WordPress, ...).
Problema tipico: i feed di notizie non hanno la data DELL'EVENTO ma quella
di pubblicazione dell'articolo. Quindi:
  1. cerchiamo date in italiano nel titolo/descrizione con dateparser
  2. se non troviamo nulla, usiamo la data di pubblicazione con confidence=low
"""
from datetime import datetime, timedelta
import html
import re

import feedparser
from dateparser.search import search_dates

from scraper.models import Event, guess_category

_TAG_RE = re.compile(r"<[^>]+>")

# search_dates() su testo libero è generoso: prende per date anche token che
# date non sono. Il caso reale che ci ha morso: "sconto del 80%" -> anno 2080.
# Quindi accettiamo un match solo se il testo che l'ha prodotto ha davvero la
# forma di una data: nome di mese, oppure gg/mm, oppure un riferimento
# relativo esplicito ("domani", "sabato", "questo weekend", ...).
_MONTHS = (
    "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
    "ottobre|novembre|dicembre|gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic"
)
_RELATIVE = (
    "oggi|domani|dopodomani|stasera|stanotte|stamattina|weekend|"
    "lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica"
)
_DATE_LIKE_RE = re.compile(
    rf"\b(?:{_MONTHS})\b|\b(?:{_RELATIVE})\b|\b\d{{1,2}}\s*[/-]\s*\d{{1,2}}\b",
    re.IGNORECASE,
)

# Percentuali e prezzi non solo diventano date fasulle: sballano anche il
# match successivo, perché dateparser usa il token precedente come contesto
# ("80%" -> 2080, e il "12 luglio" che segue diventa 2081). Via prima.
_NOISE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|€|\$|euro\b)", re.IGNORECASE)

# Un feed di notizie non parla di eventi tra due anni: oltre questa soglia
# il match è quasi sempre un falso positivo (come il "2080" di cui sopra).
MAX_HORIZON_DAYS = 270


def _strip_html(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def _looks_like_date(matched: str) -> bool:
    if "%" in matched:
        return False
    return bool(_DATE_LIKE_RE.search(matched))


def _find_event_date(text: str) -> datetime | None:
    """Cerca la prima data plausibile dell'evento nel testo (italiano)."""
    try:
        found = search_dates(
            _NOISE_RE.sub(" ", text),
            languages=["it"],
            # NB: "current_period", non "future". Con "future" una data senza
            # anno che non sia STRETTAMENTE futura viene spinta all'anno dopo:
            # un articolo del 12 luglio che dice "12 luglio" finiva nel 2027.
            settings={"PREFER_DATES_FROM": "current_period", "DATE_ORDER": "DMY"},
        )
    except Exception:
        return None
    if not found:
        return None

    floor = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ceiling = floor + timedelta(days=MAX_HORIZON_DAYS)

    plausible = []
    for matched, dt in found:
        if not _looks_like_date(matched):
            continue
        # Data senza anno molto indietro nel tempo: è l'anno prossimo.
        # (articolo di dicembre che annuncia un evento di gennaio)
        if dt < floor and (floor - dt).days > 180:
            try:
                dt = dt.replace(year=dt.year + 1)
            except ValueError:  # 29 febbraio
                continue
        if floor <= dt <= ceiling:
            plausible.append(dt)

    return min(plausible) if plausible else None


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
