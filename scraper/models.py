"""Modello evento normalizzato + utilità."""
from dataclasses import dataclass, field, asdict
from datetime import datetime
import hashlib
import re

CATEGORIES = [
    "eventi", "concerti", "club", "mostre", "musei", "teatro",
    "workshop", "corsi", "conferenze", "centri_sociali", "altro",
]

# parole chiave -> categoria (euristica semplice, sostituibile con LLM in fase 2)
_KEYWORDS = {
    "concerti": ["concerto", "live", "tour", "in concerto", "band"],
    "club": ["dj set", "djset", "club", "serata", "party", "techno", "house", "ballare", "discoteca"],
    "mostre": ["mostra", "esposizione", "vernissage", "installazione"],
    "musei": ["museo", "musei", "gam", "mao", "egizio", "reggia", "palazzo madama", "rivoli"],
    "teatro": ["teatro", "spettacolo teatrale", "commedia", "prosa", "monologo", "stand up", "stand-up"],
    "workshop": ["workshop", "laboratorio", "lab "],
    "corsi": ["corso", "lezione", "masterclass"],
    "conferenze": ["conferenza", "talk", "incontro con", "presentazione del libro", "dibattito", "seminario"],
    "centri_sociali": ["centro sociale", "csa", "csoa", "autogestito", "occupato"],
}


def guess_category(text: str, default: str = "eventi") -> str:
    t = (text or "").lower()
    for cat, words in _KEYWORDS.items():
        if any(w in t for w in words):
            return cat
    return default


def norm_title(title: str) -> str:
    """Titolo normalizzato per deduplica."""
    t = (title or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


@dataclass
class Event:
    title: str
    source_id: str
    url: str = ""
    description: str = ""
    category: str = "eventi"
    venue: str = ""            # nome del luogo, es. "OGR Torino"
    address: str = ""          # indirizzo testuale per la mappa
    lat: float | None = None
    lon: float | None = None
    start: str | None = None   # ISO 8601, es. "2026-07-12T21:00:00"
    end: str | None = None
    all_day: bool = False
    date_confidence: str = "low"  # high = data esplicita, low = dedotta dal testo
    price: str = ""
    image: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def uid(self) -> str:
        day = (self.start or "")[:10]
        raw = f"{norm_title(self.title)}|{day}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.uid
        return d
