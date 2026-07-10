"""Parser HTML di esempio: pagina eventi di GuidaTorino.

ATTENZIONE: i selettori CSS vanno verificati sul sito reale (cambiano nel
tempo). Questo file serve da template: copia-incolla per ogni nuova fonte
HTML e adatta i selettori. Il main ignora le fonti che sollevano eccezioni,
quindi un parser rotto non blocca il resto.
"""
import requests
from bs4 import BeautifulSoup

from scraper.models import Event, guess_category
from scraper.parsers.rss import _find_event_date, _strip_html

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events: list[Event] = []

    # <-- ADATTARE: selettore delle card evento
    for card in soup.select("article"):
        a = card.select_one("h2 a, h3 a, a")
        if not a or not a.get_text(strip=True):
            continue
        title = a.get_text(strip=True)
        link = a.get("href", "")
        excerpt = _strip_html(" ".join(p.get_text(" ", strip=True) for p in card.select("p")))[:600]
        img = card.select_one("img")

        dt = _find_event_date(f"{title}. {excerpt}")
        events.append(Event(
            title=title,
            source_id=source["id"],
            url=link,
            description=excerpt,
            category=guess_category(f"{title} {excerpt}", source.get("default_category", "eventi")),
            start=dt.isoformat(timespec="seconds") if dt else None,
            all_day=True,
            date_confidence="high" if dt else "low",
            image=img.get("src", "") if img else "",
        ))
    return events
