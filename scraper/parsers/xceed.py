"""Parser Xceed Open Event API — nessuna autenticazione richiesta.

Documentazione ufficiale: https://docs.xceed.me/
Endpoint: GET /api/v1/events?city=torino&limit=50&page=0
"""
import requests
from datetime import datetime

from scraper.models import Event, guess_category

BASE_URL = "https://api.xceed.me/api/v1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)",
    "Accept": "application/json",
}


def parse(source: dict) -> list[Event]:
    events: list[Event] = []
    page = 0

    while True:
        resp = requests.get(
            f"{BASE_URL}/events",
            params={"city": "torino", "limit": 50, "page": page},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # La risposta può essere una lista diretta o un oggetto con "data"/"events"
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("data") or data.get("events") or data.get("items") or []
        else:
            break

        if not items:
            break

        for item in items:
            title = item.get("name") or item.get("title") or ""
            if not title:
                continue

            # Date
            start_ts = item.get("startDate") or item.get("start_date") or item.get("date")
            end_ts = item.get("endDate") or item.get("end_date")
            start_dt = _parse_ts(start_ts)
            end_dt = _parse_ts(end_ts)

            # Venue
            venue_obj = item.get("venue") or item.get("location") or {}
            venue_name = ""
            address = ""
            lat = lon = None
            if isinstance(venue_obj, dict):
                venue_name = venue_obj.get("name") or ""
                address = venue_obj.get("address") or venue_obj.get("fullAddress") or ""
                lat = venue_obj.get("lat") or venue_obj.get("latitude")
                lon = venue_obj.get("lng") or venue_obj.get("longitude")
            elif isinstance(venue_obj, str):
                venue_name = venue_obj

            # Immagine
            image = ""
            img = item.get("coverImage") or item.get("image") or item.get("cover") or {}
            if isinstance(img, dict):
                image = img.get("url") or img.get("src") or ""
            elif isinstance(img, str):
                image = img

            # Link
            slug = item.get("slug") or item.get("id") or ""
            link = item.get("url") or (f"https://xceed.me/en/torino/event/{slug}" if slug else "")

            # Prezzo
            price = ""
            price_obj = item.get("minPrice") or item.get("price")
            if price_obj is not None:
                price = f"da €{price_obj}" if str(price_obj) != "0" else "Gratuito"

            description = item.get("description") or item.get("shortDescription") or ""
            if isinstance(description, dict):
                description = description.get("text") or description.get("html") or ""
            description = description[:600]

            category = guess_category(
                f"{title} {description}", source.get("default_category", "club")
            )

            events.append(Event(
                title=title,
                source_id=source["id"],
                url=link,
                description=description,
                category=category,
                venue=venue_name,
                address=address,
                lat=float(lat) if lat else None,
                lon=float(lon) if lon else None,
                start=start_dt.isoformat(timespec="seconds") if start_dt else None,
                end=end_dt.isoformat(timespec="seconds") if end_dt else None,
                all_day=False,
                date_confidence="high" if start_dt else "low",
                price=price,
                image=image,
            ))

        # Paginazione: esci se siamo all'ultima pagina
        if isinstance(data, dict):
            total = data.get("total") or data.get("totalCount") or 0
            if total and len(events) >= total:
                break
            has_next = data.get("hasNextPage") or data.get("has_next")
            if has_next is False:
                break

        if len(items) < 50:
            break
        page += 1

    return events


def _parse_ts(ts) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            # millisecondi o secondi
            return datetime.fromtimestamp(ts / 1000 if ts > 1e10 else ts)
        except Exception:
            return None
    if isinstance(ts, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
    return None
