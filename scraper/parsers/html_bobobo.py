"""Parser HTML della lista eventi di Bobobo.

Nessun feed, nessun JSON-LD, ma il markup è regolare. Ogni evento:

  <div class="container-eventi-lista-evento">
    <div class="container-evento-riga2">1 - <span>01/04/2026 - 05/10/2026</span></div>
    <div class="container-evento-riga3"><h3><a href=…>Titolo</a></h3></div>
    <div class="container-evento-riga4">Dove: Torino Museo Nazionale del Cinema</div>
  </div>

Le date sono gg/mm/aaaa, singole o come intervallo: esplicite, quindi non
serve dateparser.
"""
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper.models import Event, guess_category

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}

_DATA_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _date(testo: str) -> list[datetime]:
    out = []
    for giorno, mese, anno in _DATA_RE.findall(testo or ""):
        try:
            out.append(datetime(int(anno), int(mese), int(giorno)))
        except ValueError:
            continue
    return out


def _text(node, sel: str) -> str:
    el = node.select_one(sel)
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[Event] = []

    for card in soup.select(".container-eventi-lista-evento"):
        a = card.select_one(".container-evento-riga3 a[href]")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue

        date = _date(_text(card, ".container-evento-riga2"))
        start = date[0] if date else None
        end = date[1] if len(date) > 1 else None

        # "Dove: Torino Museo Nazionale del Cinema"
        venue = re.sub(r"^\s*dove:\s*", "", _text(card, ".container-evento-riga4"),
                       flags=re.IGNORECASE).strip()

        img = card.select_one("img")

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=urljoin(source["url"], a["href"]),
            description=venue[:600],
            category=guess_category(title, source.get("default_category", "eventi")),
            venue=venue,
            start=start.isoformat(timespec="seconds") if start else None,
            end=end.isoformat(timespec="seconds") if end else None,
            all_day=True,
            date_confidence="high" if start else "low",
            image=img.get("src", "") if img else "",
        ))

    return events
