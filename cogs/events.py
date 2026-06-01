import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from datetime import datetime, timezone

from config import (
    METAFORGE_EVENTS,
    METAFORGE_MAPS,
    MAHCKS_EVENTS,
    MAHCKS_MAPS,
)


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def _fetch(self, primary_url: str, backup_url: str) -> dict | list | None:
        """Try primary API, fall back to backup on failure."""
        for url in (primary_url, backup_url):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                continue
        return None

    async def _get_maps(self) -> list | None:
        data = await self._fetch(METAFORGE_MAPS, MAHCKS_MAPS)
        if data is None:
            return None
        # Normalize: MetaForge may return {"maps": [...]} or a list directly
        if isinstance(data, dict):
            return data.get("maps") or data.get("data") or []
        return data

    async def _get_events(self) -> list | None:
        data = await self._fetch(METAFORGE_EVENTS, MAHCKS_EVENTS)
        if data is None:
            return None
        if isinstance(data, dict):
            return data.get("events") or data.get("data") or data.get("schedule") or []
        return data

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _map_name(m: dict) -> str:
        return m.get("name") or m.get("title") or m.get("mapName") or "Unknown"

    @staticmethod
    def _map_description(m: dict) -> str:
        return (
            m.get("description")
            or m.get("desc")
            or m.get("summary")
            or "No description available."
        )

    @staticmethod
    def _format_timer(event: dict) -> str:
        """Build a human-readable timer string from an event dict."""
        end_raw = event.get("endTime") or event.get("end_time") or event.get("endsAt")
        if end_raw:
            try:
                if isinstance(end_raw, (int, float)):
                    # API returns milliseconds, convert to seconds
                    ts = end_raw / 1000 if end_raw > 1e12 else end_raw
                    end_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                else:
                    end_dt = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
                return f"<t:{int(end_dt.timestamp())}:R>"
            except Exception:
                return str(end_raw)
        return "Unknown"

    # ── /maps ─────────────────────────────────────────────────────────

    @app_commands.command(name="maps", description="List all available Arc Raiders maps")
    async def maps_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        maps_data = await self._get_maps()

        if not maps_data:
            await interaction.followup.send("Could not retrieve map data from the API.")
            return

        embed = discord.Embed(
            title="Arc Raiders — Maps",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )

        for m in maps_data[:25]:  # Discord embed field limit
            name = self._map_name(m)
            desc = self._map_description(m)
            if len(desc) > 100:
                desc = desc[:97] + "..."
            embed.add_field(name=name, value=desc, inline=False)

        embed.set_footer(text="Data from MetaForge / Mahcks API")
        await interaction.followup.send(embed=embed)

    # ── /events ───────────────────────────────────────────────────────

    @app_commands.command(name="events", description="Show active Arc Raiders map events and timers")
    async def events_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events_data = await self._get_events()

        if not events_data:
            await interaction.followup.send("Could not retrieve events data from the API.")
            return

        embed = discord.Embed(
            title="Arc Raiders — Active Events",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc),
        )

        for ev in events_data[:25]:
            name = ev.get("name") or ev.get("title") or ev.get("eventName") or "Unknown Event"
            map_name = ev.get("map") or ev.get("mapName") or ev.get("location") or ""
            timer = self._format_timer(ev)

            value_parts = []
            if map_name:
                value_parts.append(f"**Map:** {map_name}")
            value_parts.append(f"**Ends:** {timer}")

            description = ev.get("description") or ev.get("desc") or ""
            if description:
                if len(description) > 80:
                    description = description[:77] + "..."
                value_parts.append(description)

            embed.add_field(name=name, value="\n".join(value_parts), inline=False)

        if not events_data:
            embed.description = "No active events right now."

        embed.set_footer(text="Data from MetaForge / Mahcks API")
        await interaction.followup.send(embed=embed)

    # ── /mapinfo ──────────────────────────────────────────────────────

    @app_commands.command(name="mapinfo", description="Detailed info about a specific Arc Raiders map")
    @app_commands.describe(name="Name of the map")
    async def mapinfo_command(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        maps_data = await self._get_maps()

        if not maps_data:
            await interaction.followup.send("Could not retrieve map data from the API.")
            return

        target = name.lower()
        match = next(
            (m for m in maps_data if self._map_name(m).lower() == target),
            None,
        )
        if match is None:
            # Fuzzy: partial match
            match = next(
                (m for m in maps_data if target in self._map_name(m).lower()),
                None,
            )

        if match is None:
            available = ", ".join(self._map_name(m) for m in maps_data[:20])
            await interaction.followup.send(
                f"Map **{name}** not found. Available maps: {available}"
            )
            return

        embed = discord.Embed(
            title=self._map_name(match),
            description=self._map_description(match),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )

        # Add any extra fields present in the data
        for key in ("difficulty", "tier", "level", "region", "biome", "type", "size", "players"):
            value = match.get(key)
            if value is not None:
                embed.add_field(name=key.capitalize(), value=str(value), inline=True)

        image_url = match.get("image") or match.get("imageUrl") or match.get("thumbnail")
        if image_url:
            embed.set_image(url=image_url)

        embed.set_footer(text="Data from MetaForge / Mahcks API")
        await interaction.followup.send(embed=embed)

    @mapinfo_command.autocomplete("name")
    async def mapinfo_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        maps_data = await self._get_maps()
        if not maps_data:
            return []

        choices = []
        current_lower = current.lower()
        for m in maps_data:
            map_name = self._map_name(m)
            if current_lower in map_name.lower():
                choices.append(app_commands.Choice(name=map_name[:100], value=map_name[:100]))
            if len(choices) >= 25:
                break
        return choices


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
