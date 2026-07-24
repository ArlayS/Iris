from motor.motor_asyncio import AsyncIOMotorClient

from config import DB_NAME, MONGO_URL


client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


async def initialize_indexes() -> None:
    await db.tickets.create_index("id", unique=True)
    await db.tickets.create_index("channel_id", unique=True)
    await db.tickets.create_index("member_id")
    await db.tickets.create_index("updated_at")
    await db.tickets.create_index("demo_ticket")
    await db.tickets.create_index("assigned_helper.id")