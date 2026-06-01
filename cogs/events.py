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


MAP_IMAGES = {
    "dam battlegrounds": "https://cdn.mapgenie.io/images/games/arc-raiders/maps/dam-battlegrounds.jpg",
    "dam":               "https://cdn.mapgenie.io/images/games/arc-raiders/maps/dam-battlegrounds.jpg",
    "buried city":       "https://cdn.mapgenie.io/images/games/arc-raiders/maps/buried-city.jpg",
    "spaceport":         "https://cdn.mapgenie.io/images/games/arc-raiders/maps/spaceport.jpg",
    "the blue gate":     "https://cdn.mapgenie.io/images/games/arc-raiders/maps/the-blue-gate.jpg",
    "blue gate":         "https://cdn.mapgenie.io/images/games/arc-raiders/maps/the-blue-gate.jpg",
    "stella montis":     "https://cdn.mapgenie.io/images/games/arc-raiders/maps/stella-montis.jpg",
    "riven tides":       "https://cdn.mapgenie.io/images/games/arc-raiders/maps/riven-tides.jpg",
}


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def _fetch(self, *urls: str) -> dict | list | None:
        """Try each URL in order, return first successful JSON response."""
        for url in urls:
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("content-type", "")
                        if "json" not in content_type and "javascript" not in content_type:
                            continue
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
    def _localized_str(value) -> str | None:
        """Extract a string from a value that may be a plain string or a localization dict."""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("en") or next(iter(value.values()), None)
        return None

    @staticmethod
    def _map_name(m: dict) -> str:
        for key in ("name", "title", "mapName", "displayName"):
            val = m.get(key)
            if val is None:
                continue
            resolved = Events._localized_str(val)
            if resolved:
                return resolved
        return "Unknown"

    @staticmethod
    def _map_description(m: dict) -> str:
        for key in ("description", "desc", "summary"):
            val = m.get(key)
            if val is None:
                continue
            resolved = Events._localized_str(val)
            if resolved:
                return resolved
        return "No description available."

    @staticmethod
    def _parse_timestamp(raw) -> datetime | None:
        """Parse a timestamp from the API (ms epoch, seconds epoch, or ISO string)."""
        if raw is None:
            return None
        try:
            if isinstance(raw, (int, float)):
                ts = raw / 1000 if raw > 1e12 else raw
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _get_start_time(event: dict):
        return event.get("startTime") or event.get("start_time") or event.get("startsAt")

    @staticmethod
    def _get_end_time(event: dict):
        return event.get("endTime") or event.get("end_time") or event.get("endsAt")

    @staticmethod
    def _get_map_image(map_name: str) -> str | None:
        """Return a MapGenie CDN image URL for the given map name, or None."""
        if not map_name:
            return None
        base = map_name.rsplit(" Upper", 1)[0].rsplit(" Lower", 1)[0]
        return MAP_IMAGES.get(base.lower())

    def _is_active(self, event: dict) -> bool:
        """Check if an event is currently active."""
        now = datetime.now(timezone.utc)
        end_dt = self._parse_timestamp(self._get_end_time(event))
        if end_dt and end_dt > now:
            start_dt = self._parse_timestamp(self._get_start_time(event))
            if start_dt is None or start_dt <= now:
                return True
        return False

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

        seen = set()
        for m in maps_data[:25]:
            name = self._map_name(m)
            # Deduplicate maps with variants (e.g. "Stella Montis Upper/Lower")
            base_name = name.rsplit(" Upper", 1)[0].rsplit(" Lower", 1)[0]
            if base_name in seen:
                continue
            seen.add(base_name)
            desc = self._map_description(m)
            value = desc if desc != "No description available." else "—"
            embed.add_field(name=base_name, value=value, inline=False)

        embed.set_footer(text="Data from Mahcks API")
        await interaction.followup.send(embed=embed)

    # ── /events ───────────────────────────────────────────────────────

    @app_commands.command(name="events", description="Show active Arc Raiders map events and timers")
    async def events_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events_data = await self._get_events()

        if not events_data:
            await interaction.followup.send("Could not retrieve events data from the API.")
            return

        now = datetime.now(timezone.utc)
        active_events = []
        upcoming_events = []
        for ev in events_data:
            end_dt = self._parse_timestamp(self._get_end_time(ev))
            if end_dt and end_dt <= now:
                continue  # skip past events
            if self._is_active(ev):
                active_events.append(ev)
            else:
                upcoming_events.append(ev)

        embeds = []

        # Active events — one embed per event
        if active_events:
            for ev in active_events[:10]:
                name = ev.get("name") or ev.get("title") or ev.get("eventName") or "Unknown Event"
                map_name = ev.get("map") or ev.get("mapName") or ev.get("location") or ""
                end_dt = self._parse_timestamp(self._get_end_time(ev))
                timer = f"<t:{int(end_dt.timestamp())}:R>" if end_dt else "Unknown"

                embed_ev = discord.Embed(
                    title=f"🟢 {name}",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc),
                )
                if map_name:
                    embed_ev.add_field(name="Map", value=map_name, inline=True)
                embed_ev.add_field(name="Ends", value=timer, inline=True)

                map_img = self._get_map_image(map_name)
                if map_img:
                    embed_ev.set_thumbnail(url=map_img)

                embed_ev.set_footer(text="Data from MetaForge / Mahcks API")
                embeds.append(embed_ev)
        else:
            embed_none = discord.Embed(
                title="Active Events",
                description="Sin eventos activo en este momento.",
                color=discord.Color.gold(),
                timestamp=datetime.now(timezone.utc),
            )
            embed_none.set_footer(text="Data from MetaForge / Mahcks API")
            embeds.append(embed_none)

        # Upcoming events — single embed
        embed_upcoming = discord.Embed(
            title="Upcoming Events",
            color=discord.Color.teal(),
            timestamp=datetime.now(timezone.utc),
        )
        if upcoming_events:
            for ev in upcoming_events[:12]:
                name = ev.get("name") or ev.get("title") or ev.get("eventName") or "Unknown Event"
                map_name = ev.get("map") or ev.get("mapName") or ev.get("location") or ""
                start_dt = self._parse_timestamp(self._get_start_time(ev))
                timer = f"<t:{int(start_dt.timestamp())}:R>" if start_dt else "Unknown"

                value_parts = []
                if map_name:
                    value_parts.append(f"**Map:** {map_name}")
                value_parts.append(f"**Starts:** {timer}")
                embed_upcoming.add_field(name=name, value="\n".join(value_parts), inline=False)
        else:
            embed_upcoming.description = "Sin eventos próximos en este momento."
        embed_upcoming.set_footer(text="Data from MetaForge / Mahcks API")
        embeds.append(embed_upcoming)

        await interaction.followup.send(embeds=embeds)

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

        image_url = (match.get("image") or match.get("imageUrl") or match.get("thumbnail")
                     or self._get_map_image(self._map_name(match)))
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
