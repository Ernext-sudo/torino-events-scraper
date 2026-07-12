"""Parser dedicato per istanze Gancio (gancio.cisti.org e simili).

Il feed di gancio.cisti.org è RSS 2.0 puro: NON dichiara alcun namespace
custom (niente <gancio:start_datetime>). La data dell'evento sta in due punti,
entrambi affidabili:

  <title>[2026-07-11] Io accetto anche i 18 @ Comala</title>
  <description><![CDATA[
     <h3>Titolo</h3>
     <strong>Comala - corso Francesco Ferrucci 65/a, 10137 Torino</strong>
     <small>(sabato, 11 luglio 20:00)</small>
     ...
  ]]></description>

Quindi: giorno dal prefisso ISO nel titolo, orario dal tag <small>.
Il parser RSS generico invece dà il testo in pasto a dateparser con
DATE_ORDER=DMY, che rilegge "2026-07-11" come 7 novembre — da cui le date
sbagliate (mese e giorno scambiati).

Le istanze Gancio che espongono i tag namespace con gli unix timestamp sono
comunque supportate: se presenti hanno la priorità.
"""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from scraper.models import Event, guess_category

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}

_TAG_RE = re.compile(r"<[^>]+>")
# "[2026-07-11] Titolo dell'evento @ Luogo"
_TITLE_DATE_RE = re.compile(r"^\s*\[(\d{4})-(\d{2})-(\d{2})\]\s*(.*)$", re.S)
# "<small>(sabato, 11 luglio 20:00)</small>" -> 20:00
_TIME_RE = re.compile(r"<small>\s*\([^)]*?\b(\d{1,2}):(\d{2})[^)]*\)\s*</small>", re.S)
# primo <strong>...</strong> della description = luogo + indirizzo
_VENUE_RE = re.compile(r"<strong>(.*?)</strong>", re.S)


def _strip(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).replace("\xa0", " ").strip()


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _from_ts(ts) -> datetime | None:
    """Unix timestamp (secondi o millisecondi) -> datetime.
    Serve solo alle istanze Gancio che espongono i tag namespace."""
    if not ts:
        return None
    try:
        v = float(ts)
    except (TypeError, ValueError):
        return None
    if v > 1e11:  # millisecondi
        v /= 1000
    try:
        return datetime.fromtimestamp(v)
    except (OverflowError, OSError, ValueError):
        return None


def _find_gancio_ns(xml_bytes: bytes) -> str | None:
    for m in re.finditer(rb'xmlns:(\w+)\s*=\s*"([^"]+)"', xml_bytes[:2000]):
        if m.group(1) == b"gancio":
            return m.group(2).decode()
    return None


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        raise RuntimeError(f"XML non valido dal feed Gancio: {e}") from e

    ns = _find_gancio_ns(resp.content)
    g = f"{{{ns}}}" if ns else None

    events: list[Event] = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for item in root.iter("item"):
        raw_title = html.unescape(item.findtext("title") or "").strip()
        if not raw_title:
            continue

        raw_desc = item.findtext("description") or ""
        link = (item.findtext("link") or "").strip()

        start_dt = end_dt = None
        confidence = "low"

        # 1) tag namespace, se questa istanza li espone
        if g is not None:
            start_dt = _from_ts(item.findtext(f"{g}start_datetime"))
            end_dt = _from_ts(item.findtext(f"{g}end_datetime"))
            if start_dt:
                confidence = "high"

        # 2) prefisso [YYYY-MM-DD] nel titolo + orario dal tag <small>
        title = raw_title
        m = _TITLE_DATE_RE.match(raw_title)
        if m:
            year, month, day, title = int(m[1]), int(m[2]), int(m[3]), m[4].strip()
            if start_dt is None:
                hour = minute = 0
                tm = _TIME_RE.search(raw_desc)
                if tm and int(tm[1]) <= 23 and int(tm[2]) <= 59:
                    hour, minute = int(tm[1]), int(tm[2])
                try:
                    start_dt = datetime(year, month, day, hour, minute)
                    confidence = "high"
                except ValueError:
                    start_dt = None

        if start_dt and start_dt < today:
            continue

        # il titolo resta "Nome evento @ Luogo": il nome ci serve pulito,
        # il luogo lo prendiamo dalla description (ha anche l'indirizzo)
        name, _, venue_from_title = (
            title.rpartition(" @ ") if " @ " in title else (title, "", "")
        )
        name = name.strip() or title

        vm = _VENUE_RE.search(raw_desc)
        venue_full = _squash(_strip(vm[1])) if vm else ""
        if " - " in venue_full:
            venue_name, address = (p.strip() for p in venue_full.split(" - ", 1))
        else:
            venue_name, address = venue_full or venue_from_title.strip(), ""

        description = _squash(_strip(raw_desc))[:600]

        enc = item.find("enclosure")
        image = enc.get("url", "") if enc is not None else ""

        events.append(Event(
            title=name,
            source_id=source["id"],
            url=link,
            description=description,
            category=guess_category(
                f"{name} {description}",
                source.get("default_category", "centri_sociali"),
            ),
            venue=venue_name,
            address=address,
            start=start_dt.isoformat(timespec="seconds") if start_dt else None,
            end=end_dt.isoformat(timespec="seconds") if end_dt else None,
            all_day=bool(start_dt and start_dt.hour == 0 and start_dt.minute == 0),
            date_confidence=confidence,
            image=image,
        ))

    return events
