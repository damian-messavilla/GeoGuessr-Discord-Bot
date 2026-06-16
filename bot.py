"""
GeoGuessr Discord Stats Bot — Haupteinstiegspunkt.

Startet den Discord-Bot, lädt alle Cogs und führt den Background-Task
für das automatische Polling der GeoGuessr-API aus.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from config import DISCORD_TOKEN, GUILD_ID, DB_PATH, GEOGUESSR_NCFA, get_logger
from database import Database
from geoguessr_api import GeoGuessrAPI, parse_feed_entries, process_duel_result

logger = get_logger(__name__)

# ─── Bot-Konfiguration ───────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",  # Fallback, hauptsächlich Slash-Commands
    intents=intents,
    description="GeoGuessr Stats Bot — Sammelt und zeigt Spielstatistiken.",
)

# Globale Instanzen (werden in setup_hook initialisiert)
bot.db = None
bot.api = None


# ─── Events ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    """Wird aufgerufen, sobald der Bot erfolgreich verbunden ist."""
    logger.info(f"✅ Bot eingeloggt als {bot.user} (ID: {bot.user.id})")
    logger.info(f"📡 Verbunden mit {len(bot.guilds)} Server(n)")

    # Slash-Commands für die spezifische Guild synchronisieren
    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"🔄 {len(synced)} Slash-Commands synchronisiert für Guild {GUILD_ID}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Synchronisieren der Commands: {e}")

    logger.info("🟢 Bot ist bereit!")


async def setup_hook():
    """
    Wird vor on_ready aufgerufen.
    Initialisiert Datenbank, API-Client und lädt Cogs.
    """
    # Datenbank initialisieren
    bot.db = Database(DB_PATH)
    await bot.db.init()
    logger.info("💾 Datenbank initialisiert")

    # API-Client starten
    bot.api = GeoGuessrAPI(GEOGUESSR_NCFA)
    await bot.api.start()
    logger.info("🌐 GeoGuessr API-Client gestartet")

    # Cogs laden
    cog_extensions = [
        "cogs.registration",
        "cogs.stats",
        "cogs.charts",
    ]

    for ext in cog_extensions:
        try:
            await bot.load_extension(ext)
            logger.info(f"📦 Cog geladen: {ext}")
        except Exception as e:
            logger.error(f"❌ Fehler beim Laden von {ext}: {e}")

    # Slash-Commands für die Guild kopieren
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)

    # Background-Task starten
    if not poll_games.is_running():
        poll_games.start()
        logger.info("⏱️ Background-Task gestartet (Intervall: 10 Minuten)")


bot.setup_hook = setup_hook


# ─── Background-Task: Spiele-Polling ────────────────────────────────────────

@tasks.loop(minutes=10)
async def poll_games():
    """
    Fragt alle 10 Minuten die GeoGuessr-API für alle registrierten Spieler ab.
    Erkennt neue Spiele und speichert sie in der Datenbank.
    """
    try:
        players = await bot.db.get_all_players()

        if not players:
            logger.debug("Keine registrierten Spieler — Polling übersprungen")
            return

        logger.info(f"🔄 Polling gestartet für {len(players)} Spieler...")
        total_new_games = 0

        for player in players:
            discord_id = player["discord_id"]
            geoguessr_id = player["geoguessr_id"]
            nick = player["geoguessr_nick"] or geoguessr_id

            try:
                # Feed abrufen
                feed = await bot.api.get_feed(count=50)

                if not feed:
                    logger.warning(f"Leerer Feed für {nick}")
                    continue

                # Spiele aus dem Feed extrahieren
                game_entries = parse_feed_entries(feed)
                new_games = 0

                for entry in game_entries:
                    game_id = entry["game_id"]

                    # Duplikat-Check
                    if await bot.db.game_exists(game_id):
                        continue

                    # Nur competitive Spiele detailliert abrufen
                    if entry["competitive_mode"]:
                        try:
                            result = await process_duel_result(
                                bot.api, game_id, geoguessr_id
                            )
                        except Exception as e:
                            logger.warning(
                                f"Konnte Spieldetails für {game_id} nicht abrufen: {e}"
                            )
                            result = {
                                "result": "unknown",
                                "elo_before": None,
                                "elo_after": None,
                                "elo_change": None,
                                "raw_data": {},
                            }
                    else:
                        # Nicht-competitive Spiele (Standard, Streaks etc.)
                        result = {
                            "result": "completed",
                            "elo_before": None,
                            "elo_after": None,
                            "elo_change": None,
                            "raw_data": {},
                        }

                    # In Datenbank speichern
                    inserted = await bot.db.add_game(
                        discord_id=discord_id,
                        game_id=game_id,
                        played_at=entry["time"],
                        game_mode=entry["game_mode"],
                        competitive_mode=entry.get("competitive_mode"),
                        result=result["result"],
                        elo_before=result.get("elo_before"),
                        elo_after=result.get("elo_after"),
                        elo_change=result.get("elo_change"),
                        raw_data=json.dumps(result.get("raw_data", {})),
                    )

                    if inserted:
                        new_games += 1
                        logger.debug(
                            f"  Neues Spiel: {game_id[:8]}... | "
                            f"{entry['game_mode']} | {result['result']}"
                        )

                if new_games > 0:
                    logger.info(f"  📊 {nick}: {new_games} neue Spiele gespeichert")
                    total_new_games += new_games

                # Rate-Limit-Schutz: 2 Sekunden Pause zwischen Spielern
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"❌ Fehler beim Polling für {nick} ({discord_id}): {e}")
                continue

        if total_new_games > 0:
            logger.info(f"✅ Polling abgeschlossen: {total_new_games} neue Spiele insgesamt")
        else:
            logger.debug("Polling abgeschlossen: Keine neuen Spiele")

    except Exception as e:
        logger.error(f"❌ Kritischer Fehler im Polling-Task: {e}", exc_info=True)


@poll_games.before_loop
async def before_poll():
    """Wartet bis der Bot vollständig bereit ist, bevor das Polling startet."""
    await bot.wait_until_ready()
    logger.info("⏱️ Bot bereit — erstes Polling beginnt in 10 Minuten")


@poll_games.error
async def poll_games_error(error):
    """Fehlerbehandlung für den Polling-Task."""
    logger.error(f"❌ Unbehandelter Fehler im Polling-Task: {error}", exc_info=True)


# ─── Graceful Shutdown ───────────────────────────────────────────────────────

async def cleanup():
    """Räumt Ressourcen beim Herunterfahren auf."""
    logger.info("🔴 Bot wird heruntergefahren...")

    if poll_games.is_running():
        poll_games.cancel()
        logger.info("⏱️ Polling-Task gestoppt")

    if bot.api:
        await bot.api.close()
        logger.info("🌐 API-Client geschlossen")

    if bot.db:
        await bot.db.close()
        logger.info("💾 Datenbank geschlossen")


# ─── Hauptprogramm ──────────────────────────────────────────────────────────

def main():
    """Startet den Bot."""
    logger.info("🚀 GeoGuessr Discord Stats Bot wird gestartet...")

    async def runner():
        async with bot:
            try:
                await bot.start(DISCORD_TOKEN)
            finally:
                await cleanup()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        logger.info("Bot durch Benutzer gestoppt (Ctrl+C)")


if __name__ == "__main__":
    main()
