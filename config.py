"""
Konfigurationsmodul für den GeoGuessr Discord Stats Bot.

Lädt Umgebungsvariablen aus einer `.env`-Datei, validiert Pflichtfelder
und stellt modulweite Konstanten sowie eine Logging-Konfiguration bereit.
"""

import logging
import os
import sys

from dotenv import load_dotenv

# ── .env laden ───────────────────────────────────────────────────────────────
load_dotenv()

# ── Pflichtfelder ────────────────────────────────────────────────────────────
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
GEOGUESSR_NCFA: str = os.getenv("GEOGUESSR_NCFA", "")

if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN ist nicht gesetzt. "
        "Bitte in der .env-Datei oder als Umgebungsvariable definieren."
    )

if not GEOGUESSR_NCFA:
    raise RuntimeError(
        "GEOGUESSR_NCFA ist nicht gesetzt. "
        "Bitte den _ncfa-Session-Cookie aus dem Browser extrahieren "
        "und in der .env-Datei hinterlegen."
    )

# ── Optionale Felder mit Standardwerten ──────────────────────────────────────
GUILD_ID: int = int(os.getenv("GUILD_ID", "1516349812566659155"))
DB_PATH: str = os.getenv("DB_PATH", "./data/geoguessr_stats.db")

# ── Logging-Konfiguration ───────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s │ %(levelname)-8s │ %(name)-20s │ %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    datefmt=_LOG_DATE_FORMAT,
    stream=sys.stdout,
)


def get_logger(name: str) -> logging.Logger:
    """Erstellt und gibt einen Logger mit dem angegebenen Namen zurück.

    Args:
        name: Name des Loggers – üblicherweise ``__name__`` des aufrufenden Moduls.

    Returns:
        Konfigurierter :class:`logging.Logger`.
    """
    return logging.getLogger(name)
