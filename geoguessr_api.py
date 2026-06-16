"""
GeoGuessr-API-Client für den Discord Stats Bot.

Verwendet ``aiohttp`` für alle HTTP-Anfragen und authentifiziert sich
über den ``_ncfa``-Session-Cookie. Enthält außerdem Hilfsfunktionen
zum Parsen des Aktivitäts-Feeds und zur Auswertung von Duell-Ergebnissen.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from config import get_logger

log = get_logger(__name__)

# ── Konstanten ───────────────────────────────────────────────────────────────
_BASE_URL = "https://www.geoguessr.com/api"
_GAME_SERVER_URL = "https://game-server.geoguessr.com/api"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # Sekunden


class GeoGuessrAPI:
    """Asynchroner Client für die GeoGuessr-REST-API."""

    def __init__(self, ncfa_cookie: str) -> None:
        """Speichert den Cookie – die Session wird erst mit :meth:`start` erzeugt.

        Args:
            ncfa_cookie: Wert des ``_ncfa``-Session-Cookies.
        """
        self._ncfa_cookie = ncfa_cookie
        self._session: aiohttp.ClientSession | None = None

    # ── Session-Verwaltung ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Erstellt die ``aiohttp.ClientSession`` mit Cookie und Headern."""
        cookie_jar = aiohttp.CookieJar()

        # Cookie für beide relevanten Domains setzen
        for domain in ("www.geoguessr.com", "game-server.geoguessr.com"):
            cookie_jar.update_cookies(
                {"_ncfa": self._ncfa_cookie},
                response_url=aiohttp.client.URL(f"https://{domain}"),
            )

        self._session = aiohttp.ClientSession(
            cookie_jar=cookie_jar,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
            },
        )
        log.info("GeoGuessr-API-Session gestartet.")

    async def close(self) -> None:
        """Schließt die HTTP-Session."""
        if self._session:
            await self._session.close()
            self._session = None
            log.info("GeoGuessr-API-Session geschlossen.")

    # ── Interne Anfrage-Methode ──────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict:
        """Führt eine HTTP-Anfrage aus und behandelt Fehler.

        Wiederholt die Anfrage automatisch bei HTTP 429 (Rate Limit)
        mit exponentiellem Backoff. Bei HTTP 401 wird eine Warnung
        über einen möglicherweise abgelaufenen Cookie geloggt.

        Args:
            method: HTTP-Methode (``GET``, ``POST`` etc.).
            url: Vollständige URL.
            **kwargs: Zusätzliche Parameter für ``aiohttp``.

        Returns:
            Geparste JSON-Antwort als Dictionary.

        Raises:
            aiohttp.ClientResponseError: Bei nicht behandelbaren HTTP-Fehlern.
        """
        if not self._session:
            raise RuntimeError(
                "Session nicht initialisiert – bitte zuerst start() aufrufen."
            )

        for attempt in range(1, _MAX_RETRIES + 1):
            log.debug("HTTP %s %s (Versuch %d)", method, url, attempt)

            async with self._session.request(method, url, **kwargs) as resp:
                if resp.status == 429:
                    # Rate Limit – exponentielles Backoff
                    retry_after = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    log.warning(
                        "Rate Limit erreicht (429) für %s – "
                        "warte %.1f s (Versuch %d/%d)",
                        url,
                        retry_after,
                        attempt,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status == 401:
                    log.warning(
                        "Authentifizierung fehlgeschlagen (401) für %s – "
                        "der _ncfa-Cookie ist möglicherweise abgelaufen. "
                        "Bitte einen neuen Cookie in der .env-Datei hinterlegen.",
                        url,
                    )

                resp.raise_for_status()

                data = await resp.json(content_type=None)
                log.debug("Antwort erhalten: %s (%d Bytes)", url, resp.content_length or 0)
                return data

        # Alle Versuche fehlgeschlagen
        raise aiohttp.ClientResponseError(
            request_info=aiohttp.RequestInfo(
                url=aiohttp.client.URL(url),
                method=method,
                headers={},
                real_url=aiohttp.client.URL(url),
            ),
            history=(),
            status=429,
            message=f"Rate Limit: Alle {_MAX_RETRIES} Versuche fehlgeschlagen für {url}",
        )

    # ── Öffentliche API-Methoden ─────────────────────────────────────────────

    async def get_feed(
        self,
        count: int = 50,
        pagination_token: str | None = None,
    ) -> dict:
        """Ruft den privaten Aktivitäts-Feed ab.

        Args:
            count: Anzahl der Feed-Einträge (Standard: 50).
            pagination_token: Token für die nächste Seite (optional).

        Returns:
            Rohe JSON-Antwort des Feeds.
        """
        url = f"{_BASE_URL}/v4/feed/private?count={count}"
        if pagination_token:
            url += f"&paginationToken={pagination_token}"
        return await self._request("GET", url)

    async def get_duel_details(self, game_id: str) -> dict:
        """Ruft die Details eines Duells ab.

        Args:
            game_id: Eindeutige Spiel-ID des Duells.

        Returns:
            Vollständige Duell-Daten.
        """
        url = f"{_GAME_SERVER_URL}/duels/{game_id}"
        return await self._request("GET", url)

    async def get_profile(self, user_id: str) -> dict:
        """Ruft das Profil eines GeoGuessr-Nutzers ab (inkl. Name).

        Args:
            user_id: GeoGuessr-Nutzer-ID.

        Returns:
            Nutzer-Profil.
        """
        url = f"{_BASE_URL}/v3/users/{user_id}"
        return await self._request("GET", url)

    async def get_ranked_rating(self) -> dict:
        """Ruft das eigene Ranked-Rating ab.

        Returns:
            Aktuelle Ranked-System-Daten des authentifizierten Nutzers.
        """
        url = f"{_BASE_URL}/v4/ranked-system/me"
        return await self._request("GET", url)


# ── Feed-Parsing ─────────────────────────────────────────────────────────────


def parse_feed_entries(feed_data: dict) -> list[dict]:
    """Parst den Aktivitäts-Feed und extrahiert eine flache Liste von Spielen.

    Unterstützte Feed-Eintragstypen:
      - ``type: 7`` – Gruppierte Spiele (Payload ist ein JSON-Array)
      - ``type: 6`` – Einzelnes kompetitives Spiel (Payload ist ein JSON-Objekt)
      - ``type: 1`` – Nicht-kompetitives Spiel / Standard-Kartenrunde

    Args:
        feed_data: Rohe JSON-Antwort von :meth:`GeoGuessrAPI.get_feed`.

    Returns:
        Flache Liste von Dictionaries mit den Schlüsseln
        ``game_id``, ``time``, ``game_mode``, ``competitive_mode``.
    """
    entries: list[dict] = []
    feed_items = feed_data.get("entries", [])

    for item in feed_items:
        entry_type = item.get("type")
        payload_raw = item.get("payload")
        time_stamp = item.get("time", item.get("timestamp"))

        if payload_raw is None:
            continue

        # Payload deserialisieren (ist als JSON-String gespeichert)
        try:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        except (json.JSONDecodeError, TypeError):
            log.warning("Feed-Eintrag mit ungültigem Payload übersprungen: %s", payload_raw[:120] if payload_raw else "")
            continue

        if entry_type == 7:
            # Gruppierte Spiele – Payload ist eine Liste
            games = payload if isinstance(payload, list) else [payload]
            for game in games:
                # game is e.g. {"type": 6, "payload": {"gameId": ...}}
                inner_payload = game.get("payload")
                if isinstance(inner_payload, str):
                    try:
                        inner_payload = json.loads(inner_payload)
                    except Exception:
                        continue
                
                if isinstance(inner_payload, dict):
                    # time_stamp fallback
                    game_time = game.get("time") or time_stamp
                    parsed = _parse_competitive_game(inner_payload, game_time)
                    if parsed:
                        entries.append(parsed)

        elif entry_type == 6:
            # Einzelnes kompetitives Spiel
            parsed = _parse_competitive_game(payload, time_stamp)
            if parsed:
                entries.append(parsed)

        elif entry_type == 1:
            # Nicht-kompetitives Spiel (Standardkarte)
            parsed = _parse_standard_game(payload, time_stamp)
            if parsed:
                entries.append(parsed)

    log.debug("%d Spiele aus dem Feed extrahiert.", len(entries))
    return entries


def _parse_competitive_game(
    game: dict,
    fallback_time: str | None,
) -> dict | None:
    """Parst ein kompetitives Spiel-Objekt aus dem Feed-Payload.

    Args:
        game: Einzelnes Spiel-Objekt.
        fallback_time: Zeitstempel aus dem Feed-Eintrag als Fallback.

    Returns:
        Geparste Spieldaten oder ``None`` bei fehlender Spiel-ID.
    """
    game_id = game.get("gameId") or game.get("gameToken")
    if not game_id:
        log.debug("Kompetitives Spiel ohne ID übersprungen.")
        return None

    return {
        "game_id": game_id,
        "time": game.get("time") or fallback_time,
        "game_mode": game.get("gameMode", "unknown"),
        "competitive_mode": game.get("competitiveGameMode"),
    }


def _parse_standard_game(
    game: dict,
    fallback_time: str | None,
) -> dict | None:
    """Parst ein nicht-kompetitives Spiel-Objekt (Standardkarte).

    Args:
        game: Einzelnes Spiel-Objekt.
        fallback_time: Zeitstempel aus dem Feed-Eintrag als Fallback.

    Returns:
        Geparste Spieldaten oder ``None`` bei fehlender Spiel-ID.
    """
    game_id = game.get("gameToken") or game.get("gameId")
    if not game_id:
        log.debug("Standardspiel ohne ID übersprungen.")
        return None

    map_name = game.get("mapName", "")
    map_slug = game.get("mapSlug", "")
    mode_label = f"standard:{map_slug}" if map_slug else "standard"

    return {
        "game_id": game_id,
        "time": game.get("time") or fallback_time,
        "game_mode": mode_label,
        "competitive_mode": None,
    }


# ── Duell-Ergebnis-Verarbeitung ──────────────────────────────────────────────


async def process_duel_result(
    api: GeoGuessrAPI,
    game_id: str,
    user_geoguessr_id: str,
) -> dict:
    """Ruft die Duell-Details ab und extrahiert Ergebnis sowie Elo-Daten.

    WICHTIG: Die API liefert die echten Elo-Werte in
    ``progressChange.rating``, nicht die in der UI angezeigten
    gedeckelten Wochenpunkte.

    Args:
        api: Initialisierte :class:`GeoGuessrAPI`-Instanz.
        game_id: Eindeutige Spiel-ID des Duells.
        user_geoguessr_id: GeoGuessr-Profil-ID des Nutzers.

    Returns:
        Dictionary mit ``result`` (``'win'``, ``'loss'``, ``'draw'``),
        ``elo_before``, ``elo_after``, ``elo_change`` und ``raw_data``.
    """
    result_default: dict[str, Any] = {
        "result": "unknown",
        "elo_before": None,
        "elo_after": None,
        "elo_change": None,
        "raw_data": {},
    }

    try:
        duel_data = await api.get_duel_details(game_id)
    except Exception:
        log.exception("Fehler beim Abrufen der Duell-Details für %s", game_id)
        return result_default

    result_default["raw_data"] = duel_data

    # ── Spieler in den Teams finden ──────────────────────────────────────
    teams: list[dict] = duel_data.get("teams", [])
    user_team_idx: int | None = None
    user_player: dict | None = None

    for team_idx, team in enumerate(teams):
        for player in team.get("players", []):
            if player.get("playerId") == user_geoguessr_id:
                user_team_idx = team_idx
                user_player = player
                break
        if user_player:
            break

    if user_player is None:
        log.warning(
            "Spieler %s nicht in den Duell-Teams gefunden (game_id=%s).",
            user_geoguessr_id,
            game_id,
        )
        return result_default

    # ── Elo-Daten extrahieren ────────────────────────────────────────────
    elo_before, elo_after, elo_change = _extract_elo(user_player)

    if elo_before is not None and elo_after is not None and elo_change is None:
        elo_change = elo_after - elo_before

    result_default["elo_before"] = elo_before
    result_default["elo_after"] = elo_after
    result_default["elo_change"] = elo_change

    # ── Spielergebnis bestimmen ──────────────────────────────────────────
    result_default["result"] = _determine_result(
        duel_data, teams, user_team_idx
    )

    return result_default


def _extract_elo(player: dict) -> tuple[int | None, int | None, int | None]:
    """Extrahiert Elo-Werte aus verschiedenen möglichen Pfaden im Spieler-Objekt.

    Versucht nacheinander:
      1. ``progressChange.rating.ratingBefore / ratingAfter``
      2. ``rating.ratingBefore / ratingAfter``
      3. ``ratingChange.before / after``

    Args:
        player: Spieler-Dictionary aus den Duell-Daten.

    Returns:
        Tuple ``(elo_before, elo_after, elo_change)``.
    """
    # Pfad 1: progressChange.rankedSystemProgress
    progress = player.get("progressChange", {})
    if isinstance(progress, dict):
        ranked = progress.get("rankedSystemProgress", {})
        if isinstance(ranked, dict):
            # Bevorzuge gameModeRatingBefore/After falls vorhanden (für Duels genauer)
            before = ranked.get("gameModeRatingBefore")
            after = ranked.get("gameModeRatingAfter")
            if before is None or after is None:
                before = ranked.get("ratingBefore")
                after = ranked.get("ratingAfter")
            if before is not None or after is not None:
                return _safe_int(before), _safe_int(after), None

    # Pfad 2: rating direkt am Spieler (alte API-Versionen)
    rating_direct = player.get("rating", {})
    rating_direct = player.get("rating", {})
    if isinstance(rating_direct, dict):
        before = rating_direct.get("ratingBefore")
        after = rating_direct.get("ratingAfter")
        if before is not None or after is not None:
            change = rating_direct.get("ratingChange")
            return (
                _safe_int(before),
                _safe_int(after),
                _safe_int(change),
            )

    # Pfad 3: ratingChange
    rc = player.get("ratingChange", {})
    if isinstance(rc, dict):
        before = rc.get("before")
        after = rc.get("after")
        if before is not None or after is not None:
            return _safe_int(before), _safe_int(after), None

    log.debug("Keine Elo-Daten im Spieler-Objekt gefunden.")
    return None, None, None


def _determine_result(
    duel_data: dict,
    teams: list[dict],
    user_team_idx: int,
) -> str:
    """Bestimmt das Spielergebnis (Sieg, Niederlage, Unentschieden).

    Prüft verschiedene Felder in den Duell-Daten, um das Ergebnis zu ermitteln:
      - ``teams[i].result``
      - ``teams[i].health`` / ``teams[i].lives``
      - ``gameResult`` auf Top-Level

    Args:
        duel_data: Vollständige Duell-Daten.
        teams: Liste der Team-Objekte.
        user_team_idx: Index des Teams, dem der Nutzer angehört.

    Returns:
        ``'win'``, ``'loss'`` oder ``'draw'``.
    """
    if not teams or user_team_idx is None:
        return "unknown"

    opponent_idx = 1 - user_team_idx if len(teams) == 2 else None

    # Methode 1: result.winningTeamId (Zuverlässigste Methode)
    res_obj = duel_data.get("result", {})
    if isinstance(res_obj, dict):
        winning_team_id = res_obj.get("winningTeamId")
        if winning_team_id:
            user_team_id = teams[user_team_idx].get("id")
            if user_team_id == winning_team_id:
                return "win"
            return "loss"

    # Methode 2: Explizites 'result'-Feld pro Team
    user_result = teams[user_team_idx].get("result")
    if user_result is not None:
        result_str = str(user_result).lower()
        if "win" in result_str or result_str == "1":
            return "win"
        if "loss" in result_str or "lose" in result_str or result_str == "2":
            return "loss"

    # Methode 3: Verbleibende Leben / Gesundheit vergleichen
    if opponent_idx is not None:
        user_health = teams[user_team_idx].get("health", teams[user_team_idx].get("lives"))
        opp_health = teams[opponent_idx].get("health", teams[opponent_idx].get("lives"))

        if user_health is not None and opp_health is not None:
            if user_health > opp_health:
                return "win"
            if user_health <= opp_health:
                return "loss"

    log.warning(
        "Spielergebnis konnte nicht bestimmt werden – "
        "Standardwert 'unknown' wird verwendet."
    )
    return "unknown"


def _safe_int(value: Any) -> int | None:
    """Wandelt einen Wert sicher in ``int`` um oder gibt ``None`` zurück.

    Args:
        value: Beliebiger Wert.

    Returns:
        ``int``-Wert oder ``None``.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
