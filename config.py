import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# MetaForge API (primary)
METAFORGE_BASE = "https://metaforge.app/api/arc-raiders"
METAFORGE_EVENTS = f"{METAFORGE_BASE}/events-schedule"
METAFORGE_MAPS = f"{METAFORGE_BASE}/game-map-data"

# Mahcks API (backup)
MAHCKS_BASE = "https://arcdata.mahcks.com"
MAHCKS_EVENTS = f"{MAHCKS_BASE}/v1/map-events?full=true"
MAHCKS_MAPS = f"{MAHCKS_BASE}/v1/maps"
