"""Parser generico per le Event Collection di Squarespace (es. Imbarchino).

Squarespace serve qualsiasi pagina anche in JSON aggiungendo ?format=json:
la collection eventi restituisce `upcoming` e `past`, con le date già come
unix timestamp in millisecondi. Nessuno scraping, nessuna euristica.

Vale per qualunque sito Squarespace: basta puntare `url` alla pagina eventi.

Attenzione a `location`: le coordinate sono spesso quelle di default del
template (New York), quindi le ignoriamo e teniamo solo il nome del luogo.
"""
import html
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests

from scraper.models import Event, guess_category

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def _from_ms(ts) -> datetime | None:
    if not isinstance(ts, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(ts / 1000)
    except (OverflowError, OSError, ValueError):
        return None


def parse(source: dict) -> list[Event]:
    resp = requests.get(
        source["url"], params={"format": "json"}, headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()

    base = f"{urlparse(source['url']).scheme}://{urlparse(source['url']).netloc}"
    # il nome del locale non sta nei singoli eventi: lo prendiamo dal sito
    locale = (data.get("website") or {}).get("siteTitle") or source.get("name", "")

    events: list[Event] = []

    for item in data.get("upcoming") or []:
        title = _strip(item.get("title"))
        if not title:
            continue

        start = _from_ms(item.get("startDate"))
        end = _from_ms(item.get("endDate"))

        description = _strip(item.get("excerpt") or item.get("body"))[:600]

        # location: teniamo l'indirizzo testuale, non le coordinate (default
        # del template, puntano a New York)
        loc = item.get("location") or {}
        address = " ".join(str(loc.get(k, "")).strip() for k in
                           ("addressLine1", "addressLine2") if loc.get(k)).strip()

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=urljoin(base, item.get("fullUrl", "")),
            description=description,
            category=guess_category(
                f"{title} {description}", source.get("default_category", "eventi")
            ),
            venue=locale,
            address=address,
            start=start.isoformat(timespec="seconds") if start else None,
            end=end.isoformat(timespec="seconds") if end else None,
            all_day=bool(start and start.hour == 0 and start.minute == 0),
            date_confidence="high" if start else "low",
            image=item.get("assetUrl") or "",
        ))

    return events
