"""Utility per le date in italiano, condivise dai parser.

Quasi tutte le fonti torinesi scrivono le date in italiano e quasi nessuna
mette l'anno ("9 Luglio ore 18.00"). Qui stanno le due cose che servivano in
copia in ogni parser: la tabella dei mesi e l'inferenza dell'anno mancante.
"""
import re
from datetime import datetime

MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
GIORNI = {
    "lunedì": 1, "martedì": 2, "mercoledì": 3, "giovedì": 4,
    "venerdì": 5, "sabato": 6, "domenica": 7,
}

MESI_RE = "|".join(MESI)
# "9 Luglio 2026", "9 Luglio", "17 e 18 Luglio"
GIORNO_MESE_RE = re.compile(rf"(\d{{1,2}})\s+({MESI_RE})\b", re.IGNORECASE)
# "ore 18.00", "dalle 16:30", "23.30"
ORA_RE = re.compile(r"\b(\d{1,2})[.:](\d{2})\b")

# Oltre questo scarto consideriamo che la data senza anno sia dell'anno dopo
# (un annuncio di dicembre che parla di gennaio), non di quello in corso.
_TOLLERANZA_PASSATO_GIORNI = 60


def anno_probabile(mese: int, giorno: int, oggi: datetime | None = None) -> int:
    """Anno da attribuire a una data che non lo indica.

    Regola: l'anno corrente, a meno che la data non risulti già passata da
    parecchio — nel qual caso la fonte sta parlando dell'anno prossimo.
    """
    oggi = oggi or datetime.now()
    try:
        candidata = datetime(oggi.year, mese, giorno)
    except ValueError:
        return oggi.year
    if (oggi - candidata).days > _TOLLERANZA_PASSATO_GIORNI:
        return oggi.year + 1
    return oggi.year


def data_italiana(testo: str, anno: int | None = None) -> datetime | None:
    """Prima data trovata in `testo`. Se manca l'anno lo inferisce."""
    m = GIORNO_MESE_RE.search(testo or "")
    if not m:
        return None
    giorno, mese = int(m[1]), MESI[m[2].lower()]
    if anno is None:
        esplicito = re.search(r"\b(20\d{2})\b", testo[m.end():m.end() + 8])
        anno = int(esplicito[1]) if esplicito else anno_probabile(mese, giorno)
    try:
        return datetime(anno, mese, giorno)
    except ValueError:
        return None


def con_orario(dt: datetime | None, testo: str) -> datetime | None:
    """Applica a `dt` il primo orario valido trovato in `testo`."""
    if dt is None:
        return None
    m = ORA_RE.search(testo or "")
    if not m:
        return dt
    ora, minuto = int(m[1]), int(m[2])
    if ora > 23 or minuto > 59:
        return dt
    return dt.replace(hour=ora, minute=minuto)
