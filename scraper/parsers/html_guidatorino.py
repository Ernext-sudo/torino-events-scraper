"""Parser HTML della pagina eventi di GuidaTorino.

La pagina non espone né RSS né JSON-LD, ma il markup è pulito e regolare.
Ogni evento è una coppia di div dentro la stessa cella:

  <div class="eventlist-1">   <a href=…><img …></a>            (copertina)
  <div class="eventlist-2">
      <ul class="event-categories"><li><a>Mostre</a></li></ul>
      <h3><a href=…>Titolo</a></h3>
      <p><span class="lista-data"><b>20 Febbraio 2026 - 14 Febbraio 2027</b></span>
         <span class="lista-orario">Orario:  10:00 - 19:00</span></p>
      <p><span class="lista-luogo"><i>Palazzo Barolo</i></span>
         <span class="evento-indirizzo">Via delle Orfane, 7</span>
         <span class="evento-citta">Torino</span></p>
  </div>

Le date sono esplicite, quindi NON passiamo da dateparser: niente euristiche
sul testo libero, niente falsi positivi. Molte voci sono mostre di lunga
durata, per cui `end` conta più di `start` (il filtro in main.py tiene gli
eventi la cui fine non è ancora passata).
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scraper.models import Event, guess_category

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}

_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
# "20 Febbraio 2026"
_DATA_RE = re.compile(rf"(\d{{1,2}})\s+({'|'.join(_MESI)})\s+(\d{{4}})", re.IGNORECASE)
# "Orario:  10:00 - 19:00"  -> prima ora = inizio
_ORA_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _parse_date(text: str) -> datetime | None:
    m = _DATA_RE.search(text or "")
    if not m:
        return None
    try:
        return datetime(int(m[3]), _MESI[m[2].lower()], int(m[1]))
    except ValueError:
        return None


def _parse_range(text: str) -> tuple[datetime | None, datetime | None]:
    """'18 Gennaio 2026 - 13 Dicembre 2026' -> (inizio, fine).
    Se la data è una sola, fine = None."""
    found = _DATA_RE.findall(text or "")
    dates = []
    for day, month, year in found:
        try:
            dates.append(datetime(int(year), _MESI[month.lower()], int(day)))
        except ValueError:
            continue
    if not dates:
        return None, None
    return dates[0], (dates[1] if len(dates) > 1 else None)


def _text(node, sel: str) -> str:
    el = node.select_one(sel)
    return el.get_text(" ", strip=True) if el else ""


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[Event] = []

    for card in soup.select(".eventlist-2"):
        a = card.select_one("h3 a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue

        start, end = _parse_range(_text(card, "span.lista-data"))

        # orario: la prima ora della fascia "10:00 - 19:00"
        if start:
            om = _ORA_RE.search(_text(card, "span.lista-orario"))
            if om and int(om[1]) <= 23 and int(om[2]) <= 59:
                start = start.replace(hour=int(om[1]), minute=int(om[2]))

        venue = _text(card, "span.lista-luogo")
        address = " ".join(p for p in (
            _text(card, "span.evento-indirizzo"),
            _text(card, "span.evento-citta"),
        ) if p)

        cats = [li.get_text(" ", strip=True)
                for li in card.select("ul.event-categories li")]
        description = " · ".join(x for x in (venue, address, ", ".join(cats)) if x)[:600]

        # la copertina sta nel div gemello, appaiato nella stessa cella
        image = ""
        sibling = card.find_previous_sibling(
            "div", class_="eventlist-1")
        if sibling:
            img = sibling.select_one("img")
            if img:
                image = img.get("src", "")

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=a.get("href", ""),
            description=description,
            category=guess_category(
                f"{title} {' '.join(cats)}",
                source.get("default_category", "eventi"),
            ),
            venue=venue,
            address=address,
            start=start.isoformat(timespec="seconds") if start else None,
            end=end.isoformat(timespec="seconds") if end else None,
            all_day=bool(start and start.hour == 0 and start.minute == 0),
            date_confidence="high" if start else "low",
            image=image,
        ))

    return events
