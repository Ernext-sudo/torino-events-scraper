"""Parser HTML della pagina eventi del Magazzino sul Po.

I biglietti sono prodotti WooCommerce, ma il post type `product` esposto su
wp-json non pubblica la data dell'evento: sta nell'estratto mostrato in
pagina, dentro il carosello (WP Carousel Pro).

  <div class="wpcp-single-item">
    <h2 class="wpcp-product-title"><a href=…>Titolo</a></h2>
    <div class="wpcp-product-price">ENTRATA LIBERA</div>
    <div class="wpcp-product-content">9 Luglio ore 18.00…</div>
  </div>

La data non ha l'anno ("9 Luglio ore 18.00"): lo inferiamo con
scraper.dates.anno_probabile. Alcune voci coprono più giorni
("17 e 18 Luglio", "24, 25 Luglio"): teniamo il primo come inizio e
l'ultimo come fine.
"""
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper.dates import GIORNO_MESE_RE, MESI, anno_probabile, con_orario
from scraper.models import Event, guess_category
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}


def _text(node, sel: str) -> str:
    el = node.select_one(sel)
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _giorni(testo: str) -> list[datetime]:
    """'17 e 18 Luglio' / '24, 25 Luglio' -> tutte le date della fascia.

    Il mese compare una volta sola, in coda: vale per tutti i giorni elencati.
    """
    m = GIORNO_MESE_RE.search(testo or "")
    if not m:
        return []
    mese = MESI[m[2].lower()]
    # i giorni sono i numeri che precedono il nome del mese ("17 e 18 Luglio")
    prefisso = testo[: m.end(1)]
    giorni = [int(g) for g in re.findall(r"\b(\d{1,2})\b", prefisso)]
    if not giorni:
        giorni = [int(m[1])]

    anno = anno_probabile(mese, giorni[0])
    date = []
    for g in giorni:
        try:
            date.append(datetime(anno, mese, g))
        except ValueError:
            continue
    return date


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[Event] = []
    visti: set[str] = set()

    for card in soup.select(".wpcp-single-item"):
        a = card.select_one(".wpcp-product-title a[href]")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if not title or title in visti:
            continue
        visti.add(title)

        quando = _text(card, ".wpcp-product-content")
        date = _giorni(quando)
        start = con_orario(date[0], quando) if date else None
        end = date[-1] if len(date) > 1 else None

        prezzo = _text(card, ".wpcp-product-price")
        if prezzo.upper() in ("ENTRATA LIBERA", "FREE"):
            prezzo = "Entrata libera"

        img = card.select_one("img")

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=urljoin(source["url"], a["href"]),
            description=quando.rstrip(". ")[:600],
            category=guess_category(
                f"{title} {quando}", source.get("default_category", "concerti")
            ),
            venue="Magazzino sul Po",
            address="Murazzi del Po Armando Rossi 18/A, Torino",
            start=start.isoformat(timespec="seconds") if start else None,
            end=end.isoformat(timespec="seconds") if end else None,
            all_day=bool(start and start.hour == 0 and start.minute == 0),
            date_confidence="high" if start else "low",
            price=prezzo,
            image=img.get("src", "") if img else "",
        ))

    return events
