# Torino Events — scraper

Aggregatore di eventi a Torino. GitHub Actions esegue lo scraper 4 volte al
giorno e committa `events.json`, che l'app Flutter scarica da:

```
https://raw.githubusercontent.com/<USER>/<REPO>/main/events.json
```

## Setup (una volta sola)

1. Crea un repo su GitHub (anche privato*) e pusha questi file
2. Tab **Actions** → abilita i workflow → "Scrape eventi Torino" → **Run workflow**
3. Dopo ~1 minuto trovi `events.json` nel repo

\* Con repo privato il raw URL richiede un token: per iniziare usa un repo
pubblico, è solo un elenco di eventi pubblici.

## Test in locale

```bash
pip install -r requirements.txt
python -m scraper.main
```

Il report a terminale mostra `[ok]`/`[FAIL]` per ogni fonte: se un feed in
`sources.yaml` è morto lo vedi subito, correggi l'URL o metti `enabled: false`.

## Aggiungere una fonte

- **Feed RSS**: aggiungi una voce in `sources.yaml` con `type: rss`. Fine.
- **Pagina HTML**: copia `scraper/parsers/html_guidatorino.py`, adatta i
  selettori CSS, registra il parser in `PARSERS` dentro `scraper/main.py`
  e aggiungi la voce nello yaml col nuovo `type`.

## Schema events.json

```json
{
  "generated_at": "...",
  "sources": [{"id": "...", "name": "...", "enabled": true}],
  "events": [{
    "id": "hash", "title": "...", "source_id": "...",
    "url": "...", "description": "...",
    "category": "concerti|club|mostre|musei|teatro|workshop|corsi|conferenze|centri_sociali|eventi|altro",
    "venue": "", "address": "", "lat": null, "lon": null,
    "start": "2026-07-12T21:00:00", "end": null, "all_day": false,
    "date_confidence": "high|low",
    "price": "", "image": ""
  }]
}
```

`date_confidence: low` = data dedotta dal testo o dalla pubblicazione
dell'articolo: nell'app mostrala come "data da verificare".

## Roadmap fase 2 (mini PC + Ollama)

- Parser LLM: HTML grezzo → JSON strutturato (venue, prezzo, orario precisi)
- Geocoding indirizzi (Nominatim) per lat/lon
- Resident Advisor / DICE / Xceed per club e concerti
- Canali Telegram dei centri sociali (Telethon)
