# ARC Raiders Event Tracker Bot

Discord bot that displays active and upcoming map events for ARC Raiders using slash commands.

## Commands

| Command | Description |
|---------|-------------|
| `/events` | Shows active events (one embed per event with map image) and upcoming events |
| `/maps` | Lists all available ARC Raiders maps |
| `/mapinfo <name>` | Detailed info about a specific map with image |

## Data Sources

- **Primary:** [MetaForge API](https://metaforge.app/api/arc-raiders/events-schedule)
- **Backup:** [Mahcks API](https://arcdata.mahcks.com/v1/map-events?full=true)
- **Map images:** [MapGenie CDN](https://cdn.mapgenie.io/images/games/arc-raiders/maps/)

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

## Requirements

- Python 3.11+
- discord.py >= 2.3
- aiohttp
- python-dotenv

## Deployment

Configured for deployment with a `Procfile` (worker process):
```
worker: python bot.py
```
