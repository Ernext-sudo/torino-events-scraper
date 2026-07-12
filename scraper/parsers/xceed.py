"""Parser Xceed — dal JSON-LD della pagina città, non più dall'API.

L'Open Event API pubblica non esiste più: `api.xceed.me/api/v1/events` risponde
404 e `/v1/events` risponde 401 (ora vuole una chiave). La pagina città però
pubblica gli eventi come schema.org/Event in <script type="application/ld+json">,
con nome, startDate ISO, luogo e prezzo: è una fonte pulita e senza chiavi.
"""
import json
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scraper.models import Event, guess_category

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


def _iter_nodes(node):
    """Il JSON-LD può essere un oggetto, una lista o un @graph annidato."""
    if isinstance(node, list):
        for n in node:
            yield from _iter_nodes(n)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item"):
            if key in node:
                yield from _iter_nodes(node[key])


def _is_event(node: dict) -> bool:
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(x and "Event" in str(x) for x in types)


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    # normalizziamo a naive locale come il resto del progetto
    return dt.replace(tzinfo=None)


def _price_of(node: dict) -> str:
    offers = node.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return ""
    p = offers.get("price")
    if p in (None, ""):
        return ""
    return "Gratuito" if str(p) in ("0", "0.0") else f"da €{p}"


def parse(source: dict) -> list[Event]:
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[Event] = []
    visti: set[str] = set()

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        for node in _iter_nodes(data):
            if not _is_event(node):
                continue
            title = (node.get("name") or "").strip()
            if not title or title in visti:
                continue
            visti.add(title)

            start = _parse_dt(node.get("startDate"))
            end = _parse_dt(node.get("endDate"))

            loc = node.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            venue = address = ""
            lat = lon = None
            if isinstance(loc, dict):
                venue = (loc.get("name") or "").strip()
                addr = loc.get("address")
                if isinstance(addr, dict):
                    address = " ".join(str(addr.get(k, "")) for k in
                                       ("streetAddress", "addressLocality")).strip()
                elif isinstance(addr, str):
                    address = addr
                geo = loc.get("geo") or {}
                if isinstance(geo, dict):
                    lat = geo.get("latitude")
                    lon = geo.get("longitude")

            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else ""
            if isinstance(image, dict):
                image = image.get("url", "")

            description = (node.get("description") or "")[:600]

            events.append(Event(
                title=title,
                source_id=source["id"],
                url=node.get("url") or source["url"],
                description=description,
                category=guess_category(
                    f"{title} {description}", source.get("default_category", "club")
                ),
                venue=venue,
                address=address,
                lat=float(lat) if lat not in (None, "") else None,
                lon=float(lon) if lon not in (None, "") else None,
                start=start.isoformat(timespec="seconds") if start else None,
                end=end.isoformat(timespec="seconds") if end else None,
                date_confidence="high" if start else "low",
                price=_price_of(node),
                image=image if isinstance(image, str) else "",
            ))

    return events
