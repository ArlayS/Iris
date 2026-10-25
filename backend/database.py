import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

from config import AUTH_LOG_TTL_DAYS, DB_NAME, MONGO_URL

logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

AUTH_LOG_TTL_SECONDS = AUTH_LOG_TTL_DAYS * 24 * 3600


async def _migrate_auth_log_dates() -> None:
    """Convertit les anciens created_at (string ISO) en vrais dates BSON.

    Un index TTL ignore les valeurs qui ne sont pas des dates : sans cette
    migration, les anciens logs ne expireraient jamais. Non destructif.
    """
    while True:
        batch = await db.auth_logs.find(
            {"created_at": {"$type": "string"}},
            {"created_at": 1},
        ).to_list(2000)
        if not batch:
            return
        operations = []
        for doc in batch:
            try:
                value = datetime.fromisoformat(doc["created_at"].replace("Z", "+00:00"))
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                value = datetime.now(timezone.utc)
            operations.append(UpdateOne({"_id": doc["_id"]}, {"$set": {"created_at": value}}))
        await db.auth_logs.bulk_write(operations, ordered=False)


async def _ensure_auth_logs_ttl() -> None:
    """Index TTL sur auth_logs.created_at (remplace l'ancien index simple)."""
    info = await db.auth_logs.index_information()
    existing = info.get("created_at_1")
    if existing is None:
        await db.auth_logs.create_index("created_at", expireAfterSeconds=AUTH_LOG_TTL_SECONDS)
    elif existing.get("expireAfterSeconds") != AUTH_LOG_TTL_SECONDS:
        if "expireAfterSeconds" in existing:
            await db.command(
                {
                    "collMod": "auth_logs",
                    "index": {"keyPattern": {"created_at": 1}, "expireAfterSeconds": AUTH_LOG_TTL_SECONDS},
                }
            )
        else:
            await db.auth_logs.drop_index("created_at_1")
            await db.auth_logs.create_index("created_at", expireAfterSeconds=AUTH_LOG_TTL_SECONDS)


async def initialize_indexes() -> None:
    await db.tickets.create_index("id", unique=True)
    await db.tickets.create_index("channel_id", unique=True)
    await db.tickets.create_index("member_id")
    await db.tickets.create_index("updated_at")
    await db.tickets.create_index("demo_ticket")
    await db.tickets.create_index("assigned_helper.id")

    await db.helper_profiles.create_index("helper_id", unique=True)

    await db.resources.create_index("id", unique=True)
    await db.resources.create_index([("is_deleted", 1), ("created_at", -1)])

    await db.absences.create_index("id", unique=True)
    await db.absences.create_index([("start_date", 1), ("end_date", 1)])

    await db.meeting_summaries.create_index("id", unique=True)
    await db.meeting_summaries.create_index("created_at")
    await db.meeting_summaries.create_index("meeting_date")
    await db.meeting_summaries.create_index("status")

    try:
        await _migrate_auth_log_dates()
        await _ensure_auth_logs_ttl()
    except Exception:
        logger.exception("Impossible de configurer l'expiration (TTL) de auth_logs")
    await db.auth_logs.create_index("event_type")
    await db.auth_logs.create_index("helper_id")
    await db.auth_logs.create_index([("helper_id", 1), ("created_at", -1)])
    await db.auth_logs.create_index([("event_type", 1), ("created_at", -1)])

    await db.casiers.create_index([("sanctions.source.message_id", 1)], name="sanctions_source_message_id")

    await db.channel_archives.create_index("id", unique=True)
    await db.channel_archives.create_index("channel_id", unique=True)
    await db.channel_archives.create_index("created_at")
    await db.channel_archives.create_index("updated_at")
