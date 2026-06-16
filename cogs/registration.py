"""Registrierungs-Cog — Verknüpfung von Discord- und GeoGuessr-Accounts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from discord.ext.commands import Bot

# Guild-ID für Slash-Command-Registrierung
GUILD_ID = discord.Object(id=1516349812566659155)


class Registration(commands.Cog):
    """Cog für Account-Verknüpfung und Profilanzeige."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /link — GeoGuessr-Account mit Discord verknüpfen
    # ------------------------------------------------------------------
    @app_commands.command(
        name="link",
        description="Verknüpfe deinen GeoGuessr-Account mit Discord.",
    )
    @app_commands.describe(geoguessr_id="Deine GeoGuessr User-ID")
    @app_commands.guilds(GUILD_ID)
    async def link(
        self,
        interaction: discord.Interaction,
        geoguessr_id: str,
    ) -> None:
        """Verknüpft einen GeoGuessr-Account anhand der User-ID."""

        nick: str | None = None
        warn_message: str | None = None

        # GeoGuessr-ID validieren und Nickname holen
        try:
            profile = await self.bot.api.get_profile(geoguessr_id)
            nick = profile.get("user", {}).get("nick") or profile.get("nick") or profile.get("name")
        except Exception:
            # API-Fehler → trotzdem registrieren, aber Nutzer warnen
            warn_message = (
                "⚠️ Die GeoGuessr-API konnte nicht erreicht werden. "
                "Der Account wurde trotzdem verknüpft, der Nickname "
                "wird beim nächsten Update ergänzt."
            )

        # In Datenbank speichern
        await self.bot.db.add_player(
            discord_id=interaction.user.id,
            geoguessr_id=geoguessr_id,
            nick=nick,
        )

        # Erfolgs-Embed erstellen
        embed = discord.Embed(
            title="✅ Account verknüpft",
            color=discord.Color.green(),
            timestamp=datetime.now(tz=timezone.utc),
        )
        embed.add_field(
            name="Discord User",
            value=interaction.user.mention,
            inline=True,
        )
        embed.add_field(
            name="GeoGuessr Nick",
            value=nick or "*unbekannt*",
            inline=True,
        )
        embed.add_field(
            name="GeoGuessr ID",
            value=f"`{geoguessr_id}`",
            inline=False,
        )

        content = warn_message  # None wenn alles OK, sonst Warn-Text
        await interaction.response.send_message(
            content=content,
            embed=embed,
        )

    # ------------------------------------------------------------------
    # /unlink — Verknüpfung aufheben
    # ------------------------------------------------------------------
    @app_commands.command(
        name="unlink",
        description="Trenne deinen GeoGuessr-Account von Discord.",
    )
    @app_commands.guilds(GUILD_ID)
    async def unlink(self, interaction: discord.Interaction) -> None:
        """Hebt die Account-Verknüpfung auf."""

        removed = await self.bot.db.remove_player(interaction.user.id)

        if not removed:
            await interaction.response.send_message(
                "Du hast keinen verknüpften Account.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔓 Account getrennt",
            description="Dein GeoGuessr-Account wurde erfolgreich getrennt.",
            color=discord.Color.orange(),
            timestamp=datetime.now(tz=timezone.utc),
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /profile — Profilübersicht anzeigen
    # ------------------------------------------------------------------
    @app_commands.command(
        name="profile",
        description="Zeige das GeoGuessr-Profil eines Nutzers an.",
    )
    @app_commands.describe(user="Der Nutzer, dessen Profil angezeigt werden soll (Standard: du selbst)")
    @app_commands.guilds(GUILD_ID)
    async def profile(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        """Zeigt das GeoGuessr-Profil eines verknüpften Nutzers an."""

        target = user or interaction.user

        # Spieler in der Datenbank suchen
        player = await self.bot.db.get_player(target.id)
        if not player:
            await interaction.response.send_message(
                "Dieser Nutzer ist nicht verknüpft. Nutze `/link` zuerst.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Aktuelles Ranking abrufen (optional, Fehler werden abgefangen)
        elo_text: str = "*nicht verfügbar*"
        try:
            ranking = await self.bot.api.get_ranked_rating(player["geoguessr_id"])
            if ranking and ranking.get("rating"):
                elo_value = ranking["rating"]
                elo_text = f"**{elo_value}**"
        except Exception:
            pass

        # Registrierungsdatum formatieren
        registered_raw = player.get("registered_at", "")
        if registered_raw:
            try:
                dt = datetime.fromisoformat(registered_raw)
                registered = dt.strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                registered = registered_raw
        else:
            registered = "*unbekannt*"

        # Embed erstellen – Discord Blurple
        embed = discord.Embed(
            title=f"🌍 Profil — {target.display_name}",
            color=discord.Color.from_str("#5865F2"),
            timestamp=datetime.now(tz=timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="Discord User",
            value=target.mention,
            inline=True,
        )
        # Nickname aktualisieren falls unbekannt
        nick = player.get("geoguessr_nick")
        if not nick:
            try:
                profile = await self.bot.api.get_profile(player["geoguessr_id"])
                nick = profile.get("user", {}).get("nick") or profile.get("nick") or profile.get("name")
                if nick:
                    await self.bot.db.add_player(target.id, player["geoguessr_id"], nick)
            except Exception:
                pass

        embed.add_field(
            name="GeoGuessr Nick",
            value=nick or "*unbekannt*",
            inline=True,
        )
        embed.add_field(
            name="GeoGuessr ID",
            value=f"`{player['geoguessr_id']}`",
            inline=False,
        )
        embed.add_field(
            name="Aktuelles Elo",
            value=elo_text,
            inline=True,
        )
        embed.add_field(
            name="Registriert seit",
            value=registered,
            inline=True,
        )

        await interaction.followup.send(embed=embed)


async def setup(bot: Bot) -> None:
    """Lädt den Registration-Cog in den Bot."""
    await bot.add_cog(Registration(bot), guild=GUILD_ID)
