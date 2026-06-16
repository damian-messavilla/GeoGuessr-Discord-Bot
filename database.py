"""
Datenbankmodul für den GeoGuessr Discord Stats Bot.

Verwendet ``aiosqlite`` für alle asynchronen SQLite-Operationen.
Tabellen werden beim ersten Start automatisch angelegt.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from config import get_logger

log = get_logger(__name__)

# ── SQL-Schemadefinitionen ───────────────────────────────────────────────────
_CREATE_PLAYERS = """
CREATE TABLE IF NOT EXISTS players (
    discord_id     INTEGER PRIMARY KEY,
    geoguessr_id   TEXT NOT NULL UNIQUE,
    geoguessr_nick TEXT,
    registered_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_GAMES = """
CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id       INTEGER NOT NULL,
    game_id          TEXT NOT NULL UNIQUE,
    played_at        TIMESTAMP NOT NULL,
    game_mode        TEXT NOT NULL,
    competitive_mode TEXT,
    result           TEXT NOT NULL,
    elo_before       INTEGER,
    elo_after        INTEGER,
    elo_change       INTEGER,
    raw_data         TEXT,
    FOREIGN KEY (discord_id) REFERENCES players(discord_id)
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_games_discord_id ON games(discord_id);",
    "CREATE INDEX IF NOT EXISTS idx_games_played_at  ON games(played_at);",
    "CREATE INDEX IF NOT EXISTS idx_games_game_id    ON games(game_id);",
]


class Database:
    """Asynchrone Datenbankschnittstelle für Spieler- und Spieldaten."""

    def __init__(self, db_path: str) -> None:
        """Speichert den Datenbankpfad – die Verbindung wird erst mit :meth:`init` hergestellt.

        Args:
            db_path: Pfad zur SQLite-Datenbankdatei.
        """
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    # ── Verbindung / Initialisierung ─────────────────────────────────────────

    async def init(self) -> None:
        """Erstellt das Datenverzeichnis (falls nötig), öffnet die Verbindung
        und legt die Tabellen sowie Indizes an."""
        data_dir = Path(self.db_path).parent
        data_dir.mkdir(parents=True, exist_ok=True)
        log.info("Datenbank wird geöffnet: %s", self.db_path)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # Fremdschlüssel aktivieren
        await self._db.execute("PRAGMA foreign_keys = ON;")

        # Tabellen anlegen
        await self._db.execute(_CREATE_PLAYERS)
        await self._db.execute(_CREATE_GAMES)
        for idx_sql in _CREATE_INDEXES:
            await self._db.execute(idx_sql)

        await self._db.commit()
        log.info("Datenbank initialisiert – Tabellen und Indizes angelegt.")

    async def close(self) -> None:
        """Schließt die Datenbankverbindung."""
        if self._db:
            await self._db.close()
            self._db = None
            log.info("Datenbankverbindung geschlossen.")

    # ── Spieler-Operationen ──────────────────────────────────────────────────

    async def add_player(
        self,
        discord_id: int,
        geoguessr_id: str,
        nick: str | None = None,
    ) -> bool:
        """Fügt einen Spieler hinzu oder aktualisiert den bestehenden Eintrag.

        Args:
            discord_id: Discord-Nutzer-ID.
            geoguessr_id: GeoGuessr-Profil-ID.
            nick: Optionaler GeoGuessr-Anzeigename.

        Returns:
            ``True`` bei Erfolg.
        """
        try:
            await self._db.execute(
                """
                INSERT OR REPLACE INTO players (discord_id, geoguessr_id, geoguessr_nick)
                VALUES (?, ?, ?)
                """,
                (discord_id, geoguessr_id, nick),
            )
            await self._db.commit()
            log.info(
                "Spieler hinzugefügt/aktualisiert: discord_id=%s, geoguessr_id=%s",
                discord_id,
                geoguessr_id,
            )
            return True
        except Exception:
            log.exception("Fehler beim Hinzufügen des Spielers %s", discord_id)
            return False

    async def remove_player(self, discord_id: int) -> bool:
        """Entfernt einen Spieler und alle zugehörigen Spiele.

        Args:
            discord_id: Discord-Nutzer-ID.

        Returns:
            ``True`` wenn der Spieler existierte und gelöscht wurde.
        """
        try:
            # Zuerst zugehörige Spiele löschen
            await self._db.execute(
                "DELETE FROM games WHERE discord_id = ?", (discord_id,)
            )
            cursor = await self._db.execute(
                "DELETE FROM players WHERE discord_id = ?", (discord_id,)
            )
            await self._db.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                log.info("Spieler entfernt: discord_id=%s", discord_id)
            else:
                log.warning(
                    "Spieler zum Entfernen nicht gefunden: discord_id=%s", discord_id
                )
            return deleted
        except Exception:
            log.exception("Fehler beim Entfernen des Spielers %s", discord_id)
            return False

    async def get_player(self, discord_id: int) -> dict | None:
        """Gibt den Spieler als Dictionary zurück oder ``None``.

        Args:
            discord_id: Discord-Nutzer-ID.
        """
        async with self._db.execute(
            "SELECT * FROM players WHERE discord_id = ?", (discord_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_player_by_geoguessr_id(self, geoguessr_id: str) -> dict | None:
        """Sucht einen Spieler anhand der GeoGuessr-ID.

        Args:
            geoguessr_id: GeoGuessr-Profil-ID.
        """
        async with self._db.execute(
            "SELECT * FROM players WHERE geoguessr_id = ?", (geoguessr_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_players(self) -> list[dict]:
        """Gibt alle registrierten Spieler als Liste von Dictionaries zurück."""
        async with self._db.execute("SELECT * FROM players") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ── Spiel-Operationen ────────────────────────────────────────────────────

    async def add_game(
        self,
        discord_id: int,
        game_id: str,
        played_at: str,
        game_mode: str,
        competitive_mode: str | None,
        result: str,
        elo_before: int | None,
        elo_after: int | None,
        elo_change: int | None,
        raw_data: str | None,
    ) -> bool:
        """Speichert ein Spiel. Duplikate (gleiche ``game_id``) werden übersprungen.

        Returns:
            ``True`` wenn das Spiel neu eingefügt wurde, ``False`` bei Duplikat.
        """
        try:
            cursor = await self._db.execute(
                """
                INSERT OR IGNORE INTO games
                    (discord_id, game_id, played_at, game_mode,
                     competitive_mode, result, elo_before, elo_after,
                     elo_change, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    discord_id,
                    game_id,
                    played_at,
                    game_mode,
                    competitive_mode,
                    result,
                    elo_before,
                    elo_after,
                    elo_change,
                    raw_data,
                ),
            )
            await self._db.commit()
            inserted = cursor.rowcount > 0
            if inserted:
                log.debug("Spiel gespeichert: game_id=%s", game_id)
            else:
                log.debug("Spiel bereits vorhanden (übersprungen): game_id=%s", game_id)
            return inserted
        except Exception:
            log.exception("Fehler beim Speichern des Spiels %s", game_id)
            return False

    async def game_exists(self, game_id: str) -> bool:
        """Prüft, ob ein Spiel mit dieser ID bereits existiert.

        Args:
            game_id: Eindeutige GeoGuessr-Spiel-ID.
        """
        async with self._db.execute(
            "SELECT 1 FROM games WHERE game_id = ?", (game_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def get_recent_games(
        self, discord_id: int, limit: int = 5
    ) -> list[dict]:
        """Gibt die letzten Spiele eines Spielers zurück, neueste zuerst.

        Args:
            discord_id: Discord-Nutzer-ID.
            limit: Maximale Anzahl zurückgegebener Spiele.
        """
        async with self._db.execute(
            """
            SELECT * FROM games
            WHERE discord_id = ?
            ORDER BY played_at DESC
            LIMIT ?
            """,
            (discord_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_games_since(
        self, discord_id: int, since: str
    ) -> list[dict]:
        """Gibt Spiele seit einem bestimmten Datum zurück.

        Args:
            discord_id: Discord-Nutzer-ID.
            since: ISO-Datumsstring (z.B. ``'2025-01-01'``).
        """
        async with self._db.execute(
            """
            SELECT * FROM games
            WHERE discord_id = ? AND played_at >= ?
            ORDER BY played_at DESC
            """,
            (discord_id, since),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_games_by_year(
        self, discord_id: int, year: int
    ) -> list[dict]:
        """Gibt alle Spiele eines bestimmten Jahres zurück.

        Args:
            discord_id: Discord-Nutzer-ID.
            year: Das gewünschte Jahr (z.B. ``2025``).
        """
        async with self._db.execute(
            """
            SELECT * FROM games
            WHERE discord_id = ?
              AND played_at >= ? AND played_at < ?
            ORDER BY played_at DESC
            """,
            (discord_id, f"{year}-01-01", f"{year + 1}-01-01"),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_winrate_by_mode(self, discord_id: int) -> list[dict]:
        """Berechnet Gewinn- und Verlustanzahl gruppiert nach Spielmodus.

        Args:
            discord_id: Discord-Nutzer-ID.

        Returns:
            Liste mit ``game_mode``, ``wins``, ``losses``, ``draws``, ``total``.
        """
        async with self._db.execute(
            """
            SELECT
                game_mode,
                SUM(CASE WHEN result = 'win'  THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN result = 'draw' THEN 1 ELSE 0 END) AS draws,
                COUNT(*) AS total
            FROM games
            WHERE discord_id = ?
            GROUP BY game_mode
            """,
            (discord_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_elo_history(
        self, discord_id: int, limit: int = 100
    ) -> list[dict]:
        """Gibt die Elo-Verlaufsdaten chronologisch sortiert zurück.

        Args:
            discord_id: Discord-Nutzer-ID.
            limit: Maximale Anzahl zurückgegebener Einträge.

        Returns:
            Liste mit ``played_at``, ``elo_after``, ``game_mode``.
        """
        async with self._db.execute(
            """
            SELECT played_at, elo_after, game_mode
            FROM games
            WHERE discord_id = ? AND elo_after IS NOT NULL
            ORDER BY played_at ASC
            LIMIT ?
            """,
            (discord_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
