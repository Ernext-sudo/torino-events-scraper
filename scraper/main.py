"""Orchestratore: legge sources.yaml, esegue i parser, deduplica,
scrive events.json (consumato dall'app Flutter).

Uso:  python -m scraper.main
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from rapidfuzz import fuzz

from scraper.models import Event, norm_title
from scraper.parsers import rss, html_guidatorino, xceed

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
OUTPUT_FILE = ROOT / "events.json"

PARSERS = {
    "rss": rss.parse,
    "html_guidatorino": html_guidatorino.parse,
    "xceed": xceed.parse,
    # aggiungi qui i nuovi parser: "html_ogr": html_ogr.parse, ...
}

KEEP_PAST_DAYS = 1        # scarta eventi finiti da più di 1 giorno
KEEP_UNDATED = True       # tieni gli eventi senza data certa (confidence=low)
FUZZY_THRESHOLD = 88      # somiglianza titoli per deduplica


def load_sources() -> list[dict]:
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def dedupe(events: list[Event]) -> list[Event]:
    """Stesso giorno + titolo molto simile => stesso evento."""
    kept: list[Event] = []
    for ev in events:
        day = (ev.start or "")[:10]
        dup = False
        for k in kept:
            if (k.start or "")[:10] != day:
                continue
            if fuzz.token_sort_ratio(norm_title(ev.title), norm_title(k.title)) >= FUZZY_THRESHOLD:
                dup = True
                # preferisci la versione con più informazioni
                if len(ev.description) > len(k.description):
                    k.description = ev.description
                if not k.image and ev.image:
                    k.image = ev.image
                break
        if not dup:
            kept.append(ev)
    return kept


def main() -> int:
    sources = load_sources()
    all_events: list[Event] = []
    report = []

    for src in sources:
        if not src.get("enabled"):
            continue
        parser = PARSERS.get(src["type"])
        if parser is None:
            report.append(f"[skip] {src['id']}: parser '{src['type']}' non implementato")
            continue
        try:
            found = parser(src)
            all_events.extend(found)
            report.append(f"[ok]   {src['id']}: {len(found)} eventi")
        except Exception as e:  # una fonte rotta non blocca le altre
            report.append(f"[FAIL] {src['id']}: {e}")

    # filtro temporale
    cutoff = datetime.now() - timedelta(days=KEEP_PAST_DAYS)
    filtered = []
    for ev in all_events:
        if ev.start is None:
            if KEEP_UNDATED:
                filtered.append(ev)
            continue
        end = datetime.fromisoformat(ev.end) if ev.end else datetime.fromisoformat(ev.start)
        if end >= cutoff:
            filtered.append(ev)

    final = dedupe(filtered)
    final.sort(key=lambda e: (e.start is None, e.start or "", e.title))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "city": "Torino",
        "sources": [
            {"id": s["id"], "name": s["name"], "enabled": bool(s.get("enabled"))}
            for s in sources
        ],
        "events": [e.to_dict() for e in final],
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n".join(report))
    print(f"\nTotale: {len(all_events)} raccolti -> {len(final)} dopo filtro+dedup")
    print(f"Scritto {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
