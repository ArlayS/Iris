import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.environ.get("DISCORD_REDIRECT_URI")
APP_SESSION_SECRET = os.environ.get("APP_SESSION_SECRET")


def missing_discord_bot_settings() -> list[str]:
    required = {
        "DISCORD_GUILD_ID": DISCORD_GUILD_ID,
        "DISCORD_BOT_TOKEN": DISCORD_BOT_TOKEN,
    }
    return [name for name, value in required.items() if not value]


def missing_oauth_settings() -> list[str]:
    required = {
        "DISCORD_CLIENT_ID": DISCORD_CLIENT_ID,
        "DISCORD_CLIENT_SECRET": DISCORD_CLIENT_SECRET,
        "DISCORD_REDIRECT_URI": DISCORD_REDIRECT_URI,
        "APP_SESSION_SECRET": APP_SESSION_SECRET,
    }
    return [name for name, value in required.items() if not value]