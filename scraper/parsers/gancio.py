"""Parser dedicato per istanze Gancio (gancio.cisti.org e simili).

Gancio espone nel feed RSS i tag custom:
  <gancio:start_datetime> — unix timestamp (ms) inizio evento
  <gancio:end_datetime>   — unix timestamp (ms) fine evento
  <gancio:place>          — nome del luogo
  <gancio:tags>           — tag separati da virgola

Il parser generico li ignora e finisce per estrarre date sbagliate dal testo.
"""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from scraper.models import Event, guess_category

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}
_TAG_RE = re.compile(r"<[^>]+>")
_NS = {"gancio": "https://gancio.org/ns#"}   # namespace usato da Gancio


def _strip(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def _from_ts(ts) -> datetime | None:
    """Converte unix timestamp (secondi o millisecondi) in datetime."""
    if ts is None:
        return None
    try:
        v = float(ts)
        if v > 1e10:          # millisecondi
            v /= 1000
        return datetime.fromtimestamp(v)
    except (ValueError, TypeError, OSError):
        return None


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # feedparser non espone i namespace custom comodamente;
    # usiamo ElementTree direttamente sul testo grezzo.
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        raise RuntimeError(f"Errore parsing XML Gancio: {e}") from e

    # Cerca tutti i namespace dichiarati nel documento
    ns_map: dict[str, str] = {}
    for _, (prefix, uri) in ET.iterparse(
        __import__("io").BytesIO(resp.content), events=["start-ns"]
    ):
        ns_map[prefix] = uri

    # Namespace gancio (può variare leggermente tra versioni)
    gancio_ns = ns_map.get("gancio", "https://gancio.org/ns#")
    g = f"{{{gancio_ns}}}"

    events: list[Event] = []
    now = datetime.now()

    for item in root.iter("item"):
        title = _strip(item.findtext("title") or "")
        if not title:
            continue

        link = (item.findtext("link") or "").strip()
        description = _strip(item.findtext("description") or "")[:600]

        # Date dal namespace Gancio (priorità assoluta)
        start_raw = item.findtext(f"{g}start_datetime")
        end_raw = item.findtext(f"{g}end_datetime")
        start_dt = _from_ts(start_raw)
        end_dt = _from_ts(end_raw)

        # Fallback: pubDate del feed
        if start_dt is None:
            pub = item.findtext("pubDate") or ""
            try:
                from email.utils import parsedate_to_datetime
                start_dt = parsedate_to_datetime(pub).replace(tzinfo=None)
            except Exception:
                pass

        # Scarta eventi già passati da più di un giorno
        if start_dt and start_dt < now.replace(hour=0, minute=0, second=0):
            continue

        # Luogo
        place = _strip(item.findtext(f"{g}place") or "")

        # Immagine (enclosure o media:content)
        image = ""
        enc = item.find("enclosure")
        if enc is not None:
            image = enc.get("url", "")
        if not image:
            for ns_uri in ns_map.values():
                mc = item.find(f"{{{ns_uri}}}content")
                if mc is not None:
                    image = mc.get("url", "")
                    break

        # Tag -> categoria
        tags_raw = _strip(item.findtext(f"{g}tags") or "")
        category = guess_category(
            f"{title} {description} {tags_raw}",
            source.get("default_category", "centri_sociali"),
        )

        events.append(Event(
            title=title,
            source_id=source["id"],
            url=link,
            description=description,
            category=category,
            venue=place,
            start=start_dt.isoformat(timespec="seconds") if start_dt else None,
            end=end_dt.isoformat(timespec="seconds") if end_dt else None,
            all_day=bool(start_dt and start_dt.hour == 0 and start_dt.minute == 0),
            date_confidence="high" if start_raw else "low",
            image=image,
        ))

    return events
