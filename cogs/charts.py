"""Chart-Cog — Diagramm-basierte Statistiken (Aktivität, Elo, Winrate, Heatmap)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from utils.chart_generator import (
    generate_activity_chart,
    generate_elo_chart,
    generate_heatmap,
    generate_winrate_chart,
)

if TYPE_CHECKING:
    from discord.ext.commands import Bot

# Guild-ID für Slash-Command-Registrierung
GUILD_ID = discord.Object(id=1516349812566659155)

# Einheitliche Fehlermeldung bei fehlenden Spieldaten
_NO_DATA_MSG = (
    "Keine Spieldaten vorhanden. "
    "Spiele werden automatisch alle 10 Minuten erfasst."
)


class Charts(commands.Cog):
    """Cog für diagrammbasierte Spielstatistiken."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Hilfsmethode: Spieler auflösen und prüfen
    # ------------------------------------------------------------------
    async def _resolve_player(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None,
    ) -> dict | None:
        """Löst den Ziel-Nutzer auf und gibt den DB-Eintrag zurück.

        Sendet bei fehlendem Eintrag eine ephemerale Fehlermeldung
        und gibt ``None`` zurück.
        """
        target = user or interaction.user
        player = await self.bot.db.get_player(target.id)

        if not player:
            await interaction.followup.send(
                "Dieser Nutzer ist nicht verknüpft. Nutze `/link` zuerst.",
                ephemeral=True,
            )
            return None

        # Discord-ID für spätere DB-Abfragen mitgeben
        player["_discord_id"] = target.id
        player["_display_name"] = target.display_name
        return player

    # ------------------------------------------------------------------
    # /activity — Aktivitätsdiagramm (letzte 7 Tage)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="activity",
        description="Zeige ein Aktivitätsdiagramm der letzten 7 Tage.",
    )
    @app_commands.describe(user="Der Nutzer (Standard: du selbst)")
    @app_commands.guilds(GUILD_ID)
    async def activity(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Erstellt ein Balkendiagramm der Spielaktivität der letzten Woche."""

        await interaction.response.defer()

        player = await self._resolve_player(interaction, user)
        if player is None:
            return

        discord_id: int = player["_discord_id"]
        seven_days_ago = datetime.now(tz=timezone.utc) - timedelta(days=7)
        games = await self.bot.db.get_games_since(
            discord_id, seven_days_ago.isoformat()
        )

        if not games:
            await interaction.followup.send(_NO_DATA_MSG, ephemeral=True)
            return

        chart_path: str | None = None
        try:
            chart_path = await generate_activity_chart(games)
            file = discord.File(chart_path, filename="activity.png")
            await interaction.followup.send(file=file)
        finally:
            if chart_path and os.path.exists(chart_path):
                os.unlink(chart_path)

    # ------------------------------------------------------------------
    # /elo — Elo-Verlauf
    # ------------------------------------------------------------------
    @app_commands.command(
        name="elo",
        description="Zeige den Elo-Verlauf als Diagramm an.",
    )
    @app_commands.describe(user="Der Nutzer (Standard: du selbst)")
    @app_commands.guilds(GUILD_ID)
    async def elo(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Erstellt ein Liniendiagramm des Elo-Verlaufs."""

        await interaction.response.defer()

        player = await self._resolve_player(interaction, user)
        if player is None:
            return

        discord_id: int = player["_discord_id"]
        games = await self.bot.db.get_elo_history(discord_id, limit=200)

        if not games:
            await interaction.followup.send(_NO_DATA_MSG, ephemeral=True)
            return

        chart_path: str | None = None
        try:
            chart_path = await generate_elo_chart(games)
            file = discord.File(chart_path, filename="elo.png")
            await interaction.followup.send(file=file)
        finally:
            if chart_path and os.path.exists(chart_path):
                os.unlink(chart_path)

    # ------------------------------------------------------------------
    # /winrate_chart — Winrate-Diagramm nach Modus
    # ------------------------------------------------------------------
    @app_commands.command(
        name="winrate_chart",
        description="Zeige die Winrate pro Modus als Diagramm an.",
    )
    @app_commands.describe(user="Der Nutzer (Standard: du selbst)")
    @app_commands.guilds(GUILD_ID)
    async def winrate_chart(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Erstellt ein Kreisdiagramm der Winrate je Spielmodus."""

        await interaction.response.defer()

        player = await self._resolve_player(interaction, user)
        if player is None:
            return

        discord_id: int = player["_discord_id"]
        stats = await self.bot.db.get_winrate_by_mode(discord_id)

        if not stats:
            await interaction.followup.send(_NO_DATA_MSG, ephemeral=True)
            return

        chart_path: str | None = None
        try:
            chart_path = await generate_winrate_chart(stats)
            file = discord.File(chart_path, filename="winrate.png")
            await interaction.followup.send(file=file)
        finally:
            if chart_path and os.path.exists(chart_path):
                os.unlink(chart_path)

    # ------------------------------------------------------------------
    # /heatmap — Jahres-Heatmap der Spielaktivität
    # ------------------------------------------------------------------
    @app_commands.command(
        name="heatmap",
        description="Zeige eine Jahres-Heatmap deiner Spielaktivität.",
    )
    @app_commands.describe(user="Der Nutzer (Standard: du selbst)")
    @app_commands.guilds(GUILD_ID)
    async def heatmap(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Erstellt eine GitHub-Style-Heatmap der Spiele im aktuellen Jahr."""

        await interaction.response.defer()

        player = await self._resolve_player(interaction, user)
        if player is None:
            return

        discord_id: int = player["_discord_id"]
        current_year = datetime.now(tz=timezone.utc).year
        games = await self.bot.db.get_games_by_year(discord_id, current_year)

        if not games:
            await interaction.followup.send(_NO_DATA_MSG, ephemeral=True)
            return

        chart_path: str | None = None
        try:
            chart_path = await generate_heatmap(games, current_year)
            file = discord.File(chart_path, filename="heatmap.png")
            await interaction.followup.send(file=file)
        finally:
            if chart_path and os.path.exists(chart_path):
                os.unlink(chart_path)


async def setup(bot: Bot) -> None:
    """Lädt den Charts-Cog in den Bot."""
    await bot.add_cog(Charts(bot), guild=GUILD_ID)
