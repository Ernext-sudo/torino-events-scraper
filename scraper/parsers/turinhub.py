"""Parser TurinHub.

turinhub.it è una pagina statica: gli eventi li carica via JS da un Google
Sheet, servito da un Cloudflare Worker che fa da proxy con cache
(assets/js/api.js). Interroghiamo lo stesso endpoint pubblico che usa il sito,
così non serve né una chiave né rendere il JavaScript.

Il Worker restituisce le righe grezze del foglio; la mappatura delle colonne è
quella di assets/js/normalize.js:

  0 locale · 1 data gg/mm/aaaa · 2 titolo · 3 ora inizio · 4 ora fine
  5 generi (separati da ∙) · 6 tipo · 7 prezzo · 8 link · 9 mappa

È la fonte più ricca del progetto: aggrega decine di locali torinesi.
"""
from datetime import datetime

import requests

from scraper.models import Event, guess_category

HEADERS = {"User-Agent": "Mozilla/5.0 (TorinoEventsBot; personal use)"}

# Endpoint del Worker letto da assets/js/api.js. Se cambia, il sito smette di
# funzionare prima di noi: è la stessa fonte che usa la loro pagina.
API_URL = "https://turinhub-proxy.kattabbo.workers.dev"

# La colonna "tipo" del foglio -> categorie del progetto
_TIPO = {
    "live music": "concerti",
    "dj set": "club",
    "clubbing": "club",
    "teatro": "teatro",
    "mostra": "mostre",
    "cinema": "eventi",
}


def _orario(dt: datetime, testo: str) -> datetime:
    parti = (testo or "").strip().split(":")
    if len(parti) < 2:
        return dt
    try:
        ora, minuto = int(parti[0]), int(parti[1])
    except ValueError:
        return dt
    if ora > 23 or minuto > 59:
        return dt
    return dt.replace(hour=ora, minute=minuto)


def parse(source: dict) -> list[Event]:
    resp = requests.get(source.get("url") or API_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    righe = resp.json().get("values", [])

    events: list[Event] = []
    oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for riga in righe:
        # righe corte: il foglio non riempie le colonne finali vuote
        campi = list(riga) + [""] * (10 - len(riga))
        locale, data_raw, titolo = campi[0].strip(), campi[1].strip(), campi[2].strip()
        if not (locale and data_raw and titolo):
            continue

        try:
            giorno, mese, anno = (int(x) for x in data_raw.split("/"))
            start = datetime(anno, mese, giorno)
        except ValueError:
            continue

        start = _orario(start, campi[3])
        end = _orario(start, campi[4]) if campi[4].strip() else None
        if end and end < start:  # serata che scavalca la mezzanotte
            end = None

        if start < oggi:
            continue

        generi = campi[5].strip()
        tipo = campi[6].strip()
        prezzo = campi[7].strip()

        categoria = _TIPO.get(tipo.lower()) or guess_category(
            f"{titolo} {generi} {tipo}", source.get("default_category", "concerti")
        )

        events.append(Event(
            title=titolo,
            source_id=source["id"],
            url=campi[8].strip(),
            description=" · ".join(x for x in (locale, generi, tipo) if x)[:600],
            category=categoria,
            venue=locale,
            start=start.isoformat(timespec="seconds"),
            end=end.isoformat(timespec="seconds") if end else None,
            all_day=start.hour == 0 and start.minute == 0,
            date_confidence="high",
            price="" if prezzo.lower() in ("", "n.d.") else prezzo,
        ))

    return events
