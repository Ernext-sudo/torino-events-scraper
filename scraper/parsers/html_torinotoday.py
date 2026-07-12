"""Parser HTML della sezione eventi di TorinoToday (Citynews).

I feed RSS di categoria (/rss/eventi, /rss/tempo-libero) rispondono 403: sono
stati disattivati lato server, non è un problema di User-Agent (anche
/rss/cronaca dà 403; risponde solo /rss, che però è il flusso di cronaca
generale, non di eventi). Restano le card della pagina /eventi/.

  <article class="c-card">
    <span class="c-card__kicker">Teatri</span>          (categoria)
    <header><a href="/eventi/…">Titolo</a></header>
    <div class="c-card__item-details">dal 11 giugno al 30 luglio 2026</div>
    <div class="c-card__item-details">Officine S</div>  (luogo)
  </article>

L'anno compare una volta sola, in fondo, e vale per tutta la fascia:
"dal 7 al 12 luglio 2026" -> inizio 7 luglio, fine 12 luglio.
"""
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper.models import Event, guess_category

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}

_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
_MESI_RE = "|".join(_MESI)
# "11 giugno" / "7" (giorno senza mese: il mese è quello della data finale)
_GIORNO_RE = re.compile(rf"(\d{{1,2}})(?:\s+({_MESI_RE}))?", re.IGNORECASE)
_ANNO_RE = re.compile(r"(\d{4})")


def _parse_range(text: str) -> tuple[datetime | None, datetime | None]:
    """'dal 7 al 12 luglio 2026' -> (7 lug 2026, 12 lug 2026)."""
    t = re.sub(r"\s+", " ", (text or "")).strip().lower()
    anno = _ANNO_RE.search(t)
    if not anno:
        return None, None
    year = int(anno[1])

    # i giorni/mesi stanno prima dell'anno
    parti = _GIORNO_RE.findall(t[: anno.start()])
    if not parti:
        return None, None

    # il mese di riferimento è l'ultimo esplicitato ("dal 7 al 12 luglio")
    mesi_espliciti = [m for _, m in parti if m]
    if not mesi_espliciti:
        return None, None
    mese_finale = mesi_espliciti[-1]

    date = []
    for giorno, mese in parti:
        nome_mese = mese or mese_finale
        try:
            date.append(datetime(year, _MESI[nome_mese], int(giorno)))
        except (KeyError, ValueError):
            continue
    if not date:
        return None, None

    start = date[0]
    end = date[-1] if len(date) > 1 else None
    # "dal 11 giugno al 30 luglio 2026": l'anno finale vale per la fine; se
    # l'inizio risulta dopo la fine, l'inizio è dell'anno precedente.
    if end and start > end:
        try:
            start = start.replace(year=year - 1)
        except ValueError:
            pass
    return start, end


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[Event] = []

    for card in soup.select("article.c-card"):
        a = card.select_one("header a[href]")
        if not a:
            continue
        title = a.get("aria-label") or a.get_text(" ", strip=True)
        if not title:
            continue

        details = [
            re.sub(r"\s+", " ", d.get_text(" ", strip=True))
            for d in card.select(".c-card__item-details")
        ]
        # il primo blocco con un anno è la data; il resto è il luogo
        data_txt = next((d for d in details if _ANNO_RE.search(d)), "")
        venue = next((d for d in details if d and d != data_txt), "")

        start, end = _parse_range(data_txt)

        kicker = card.select_one(".c-card__kicker")
        sezione = kicker.get_text(" ", strip=True) if kicker else ""

        img = card.select_one("img")
        image = img.get("src", "") if img else ""
        if image.startswith("//"):
            image = "https:" + image

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=urljoin(source["url"], a["href"]),
            description=" · ".join(x for x in (sezione, venue) if x)[:600],
            category=guess_category(
                f"{title} {sezione}", source.get("default_category", "eventi")
            ),
            venue=venue,
            start=start.isoformat(timespec="seconds") if start else None,
            end=end.isoformat(timespec="seconds") if end else None,
            all_day=True,
            date_confidence="high" if start else "low",
            image=image,
        ))

    return events
