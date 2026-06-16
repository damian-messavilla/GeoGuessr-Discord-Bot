"""Statistik-Cog — Textbasierte Spielstatistiken und Winrate-Anzeige."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from discord.ext.commands import Bot

# Guild-ID für Slash-Command-Registrierung
GUILD_ID = discord.Object(id=1516349812566659155)


def _format_result_icon(result: str | None) -> str:
    """Gibt das passende Emoji für ein Spielergebnis zurück."""
    if result and result.lower() == "win":
        return "🏆 Win "
    if result and result.lower() == "loss":
        return "❌ Loss"
    return "➖ Draw"


def _format_elo_change(elo_change: int | None) -> str:
    """Formatiert die Elo-Änderung mit +/- Vorzeichen."""
    if elo_change is None:
        return "  —  "
    sign = "+" if elo_change >= 0 else ""
    return f"{sign}{elo_change}"


def _truncate(text: str, max_len: int = 10) -> str:
    """Kürzt einen Text auf die angegebene Maximallänge."""
    if len(text) <= max_len:
        return text.ljust(max_len)
    return text[: max_len - 1] + "…"


def _build_recent_table(games: list[dict], display_name: str) -> str:
    """Erstellt die formatierte Tabelle der letzten Spiele als Code-Block."""

    header = f"📊 Letzte {len(games)} Spiele von @{display_name}"
    border_top = "┌──────────────┬────────────┬──────────┬──────────┐"
    col_header = "│ Datum        │ Modus      │ Ergebnis │ Elo Δ    │"
    separator = "├──────────────┼────────────┼──────────┼──────────┤"
    border_bot = "└──────────────┴────────────┴──────────┴──────────┘"

    rows: list[str] = []
    for game in games:
        # Datum formatieren: DD.MM. HH:MM
        played_at = game.get("played_at", "")
        try:
            dt = datetime.fromisoformat(played_at)
            date_str = dt.strftime("%d.%m. %H:%M")
        except (ValueError, TypeError):
            date_str = played_at[:12] if played_at else "???"
        date_str = date_str.ljust(12)

        mode = _truncate(game.get("mode", "?"), 10)
        result = _format_result_icon(game.get("result"))
        elo = _format_elo_change(game.get("elo_change")).ljust(8)

        rows.append(f"│ {date_str} │ {mode} │ {result} │ {elo} │")

    lines = [header, "```", border_top, col_header, separator, *rows, border_bot, "```"]
    return "\n".join(lines)


def _build_progress_bar(ratio: float, length: int = 10) -> str:
    """Erzeugt einen visuellen Fortschrittsbalken aus ▓ und ░."""
    filled = round(ratio * length)
    return "▓" * filled + "░" * (length - filled)


class Stats(commands.Cog):
    """Cog für textbasierte Spielstatistiken."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /recent — Letzte Spiele anzeigen
    # ------------------------------------------------------------------
    @app_commands.command(
        name="recent",
        description="Zeige die letzten Spiele eines Nutzers an.",
    )
    @app_commands.describe(user="Der Nutzer (Standard: du selbst)")
    @app_commands.guilds(GUILD_ID)
    async def recent(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Zeigt die letzten 5 Spiele als formatierte Tabelle an."""

        target = user or interaction.user

        player = await self.bot.db.get_player(target.id)
        if not player:
            await interaction.response.send_message(
                "Dieser Nutzer ist nicht verknüpft. Nutze `/link` zuerst.",
                ephemeral=True,
            )
            return

        games = await self.bot.db.get_recent_games(target.id, limit=5)
        if not games:
            await interaction.response.send_message(
                "Keine Spiele gefunden.",
                ephemeral=True,
            )
            return

        table = _build_recent_table(games, target.display_name)
        await interaction.response.send_message(table)

    # ------------------------------------------------------------------
    # /winrate — Winrate nach Modus anzeigen
    # ------------------------------------------------------------------
    @app_commands.command(
        name="winrate",
        description="Zeige die Winrate pro Spielmodus an.",
    )
    @app_commands.describe(user="Der Nutzer (Standard: du selbst)")
    @app_commands.guilds(GUILD_ID)
    async def winrate(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Zeigt die Winrate nach Spielmodus als Embed mit Fortschrittsbalken an."""

        target = user or interaction.user

        player = await self.bot.db.get_player(target.id)
        if not player:
            await interaction.response.send_message(
                "Dieser Nutzer ist nicht verknüpft. Nutze `/link` zuerst.",
                ephemeral=True,
            )
            return

        stats = await self.bot.db.get_winrate_by_mode(target.id)
        if not stats:
            await interaction.response.send_message(
                "Keine Spiele gefunden.",
                ephemeral=True,
            )
            return

        # Gesamt-Statistik berechnen
        total_wins = sum(s.get("wins", 0) for s in stats.values())
        total_losses = sum(s.get("losses", 0) for s in stats.values())
        total_games = total_wins + total_losses
        total_pct = (total_wins / total_games * 100) if total_games > 0 else 0.0

        embed = discord.Embed(
            title=f"📈 Winrate — {target.display_name}",
            description=(
                f"**Gesamt:** 🏆 {total_wins}W / ❌ {total_losses}L — "
                f"{total_pct:.0f}% {_build_progress_bar(total_pct / 100)}"
            ),
            color=discord.Color.from_str("#5865F2"),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # Ein Feld pro Spielmodus
        for mode, data in stats.items():
            wins = data.get("wins", 0)
            losses = data.get("losses", 0)
            games = wins + losses
            pct = (wins / games * 100) if games > 0 else 0.0
            bar = _build_progress_bar(pct / 100)

            embed.add_field(
                name=mode,
                value=f"🏆 {wins}W / ❌ {losses}L — {pct:.0f}% {bar}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /update — Spieldaten manuell aktualisieren
    # ------------------------------------------------------------------
    @app_commands.command(
        name="update",
        description="Aktualisiere deine GeoGuessr-Spieldaten manuell.",
    )
    @app_commands.guilds(GUILD_ID)
    async def update(self, interaction: discord.Interaction) -> None:
        """Ruft die GeoGuessr-API manuell ab, um neue Spiele zu finden."""

        player = await self.bot.db.get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message(
                "Dieser Nutzer ist nicht verknüpft. Nutze `/link` zuerst.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            import json
            from geoguessr_api import parse_feed_entries, process_duel_result

            feed = await self.bot.api.get_feed(count=50)
            if not feed:
                await interaction.followup.send("⚠️ Konnte den Aktivitäts-Feed nicht abrufen.")
                return

            game_entries = parse_feed_entries(feed)
            new_games = 0
            geoguessr_id = player["geoguessr_id"]

            for entry in game_entries:
                game_id = entry["game_id"]

                # Check ob das Spiel schon existiert
                if await self.bot.db.game_exists(game_id):
                    continue

                if entry["competitive_mode"]:
                    try:
                        result = await process_duel_result(
                            self.bot.api, game_id, geoguessr_id
                        )
                    except Exception:
                        result = {
                            "result": "unknown",
                            "elo_before": None,
                            "elo_after": None,
                            "elo_change": None,
                            "raw_data": {},
                        }
                else:
                    result = {
                        "result": "completed",
                        "elo_before": None,
                        "elo_after": None,
                        "elo_change": None,
                        "raw_data": {},
                    }

                inserted = await self.bot.db.add_game(
                    discord_id=interaction.user.id,
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

            if new_games > 0:
                await interaction.followup.send(f"✅ Update erfolgreich! **{new_games} neue Spiele** gespeichert.")
            else:
                await interaction.followup.send("🔄 Alles auf dem neuesten Stand. Keine neuen Spiele gefunden.")

        except Exception as e:
            await interaction.followup.send(f"❌ Fehler beim Aktualisieren: {e}")


async def setup(bot: Bot) -> None:
    """Lädt den Stats-Cog in den Bot."""
    await bot.add_cog(Stats(bot), guild=GUILD_ID)
