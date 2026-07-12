"""Parser HTML degli eventi in programma di Variante Bunker.

variantebunker.com è WordPress, ma /feed/ restituisce HTML (il feed è
disattivato) e il post type `dp_events` esposto su wp-json non pubblica la
data dell'evento fra i meta. La pagina "eventi in programma" invece ce l'ha,
spezzata in tre span:

  <a class="dem_column_grid_view" href=… style="background-image: url('…')">
    <h3 class="dem_grid_title">Titolo</h3>
    <span class="dem_grid_venue">Bunker</span>
    <span class="dem-event-day">15</span>
    <span class="dem-event-month">Giugno,2026</span>
    <span class="dem-event-time">lunedì, 20:00 to 21:30</span>
  </a>
"""
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from scraper.models import Event, guess_category

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}

_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
_GIORNI = {
    "lunedì": 1, "martedì": 2, "mercoledì": 3, "giovedì": 4,
    "venerdì": 5, "sabato": 6, "domenica": 7,
}
# "Giugno,2026"
_MESE_ANNO_RE = re.compile(rf"({'|'.join(_MESI)})\s*,?\s*(\d{{4}})", re.IGNORECASE)
# "lunedì, 20:00 to 21:30" -> (20,00) e (21,30)
_ORE_RE = re.compile(r"(\d{1,2}):(\d{2})")
# background-image: url('…')
_BG_RE = re.compile(r"url\(['\"]?([^'\")]+)")
# "Ogni lunedì – Corso di…", "Ogni due lunedì del Mese", "Ogni 2 mercoledì"
_RICORRENZA_RE = re.compile(
    rf"\bogni\s+(due|\d+)?\s*({'|'.join(_GIORNI)})", re.IGNORECASE
)


def _prossima_occorrenza(start: datetime, weekday: int) -> datetime:
    """Porta `start` alla prima occorrenza di `weekday` da oggi in poi,
    conservando l'orario."""
    oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    avanti = (weekday - oggi.weekday() - 1) % 7
    giorno = oggi + timedelta(days=avanti)
    return giorno.replace(hour=start.hour, minute=start.minute)


def _text(node, sel: str) -> str:
    el = node.select_one(sel)
    return el.get_text(" ", strip=True) if el else ""


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[Event] = []

    for card in soup.select("a.dem_column_grid_view"):
        title = _text(card, ".dem_grid_title")
        if not title:
            continue

        start = end = None
        m = _MESE_ANNO_RE.search(_text(card, ".dem-event-month"))
        day = _text(card, ".dem-event-day")
        if m and day.isdigit():
            try:
                start = datetime(int(m[2]), _MESI[m[1].lower()], int(day))
            except ValueError:
                start = None

        if start:
            ore = _ORE_RE.findall(_text(card, ".dem-event-time"))
            if ore and int(ore[0][0]) <= 23:
                start = start.replace(hour=int(ore[0][0]), minute=int(ore[0][1]))
            if len(ore) > 1 and int(ore[1][0]) <= 23:
                end = start.replace(hour=int(ore[1][0]), minute=int(ore[1][1]))
                if end < start:  # evento che scavalca la mezzanotte
                    end = None

        # I corsi ricorrenti ("Ogni lunedì – Corso di Teatro") mostrano la data
        # della PRIMA lezione, che è ormai passata: senza questo verrebbero
        # scartati come eventi finiti, pur tenendosi ancora ogni settimana.
        # Li portiamo alla prossima occorrenza del giorno indicato.
        confidence = "high" if start else "low"
        ric = _RICORRENZA_RE.search(title)
        if start and ric and start < datetime.now():
            durata = (end - start) if end else None
            start = _prossima_occorrenza(start, _GIORNI[ric[2].lower()])
            end = (start + durata) if durata else None
            # "ogni due lunedì": la cadenza non è settimanale, quindi la
            # prossima occorrenza è una stima.
            if ric[1]:
                confidence = "low"

        venue = _text(card, ".dem_grid_venue") or "Bunker"

        image = ""
        bg = _BG_RE.search(card.get("style", "") or "")
        if bg:
            image = bg[1]

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=card.get("href", ""),
            description=venue,
            category=guess_category(title, source.get("default_category", "club")),
            venue=venue,
            start=start.isoformat(timespec="seconds") if start else None,
            end=end.isoformat(timespec="seconds") if end else None,
            all_day=bool(start and start.hour == 0 and start.minute == 0),
            date_confidence=confidence,
            image=image,
        ))

    return events
