from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from database import db
from models.ticket import (
    AuthenticatedHelper,
    TicketCreate,
    TicketDetail,
    TicketStats,
    TicketSummary,
    TicketUpdate,
)
from services.auth_service import current_helper
from services.demo_data import is_demo_helper
from services.discord_service import DiscordService


router = APIRouter(prefix="/tickets", tags=["tickets"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ticket_scope(helper: AuthenticatedHelper) -> dict:
    if is_demo_helper(helper.id, helper.mode):
        return {"demo_ticket": True}
    return {"$or": [{"demo_ticket": {"$exists": False}}, {"demo_ticket": False}]}


async def ticket_or_404(ticket_id: str, helper: AuthenticatedHelper) -> dict:
    ticket = await db.tickets.find_one(
        {"$and": [{"id": ticket_id}, ticket_scope(helper)]},
        {"_id": 0},
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket Iris introuvable.")
    return ticket


@router.get("", response_model=list[TicketSummary])
async def list_tickets(
    _: AuthenticatedHelper = Depends(current_helper),
) -> list[TicketSummary]:
    tickets = await db.tickets.find(ticket_scope(_), {"_id": 0, "transcript": 0, "notes": 0, "vocal_summary": 0}).sort(
        "updated_at", -1
    ).to_list(250)
    return tickets


@router.get("/stats", response_model=TicketStats)
async def ticket_stats(helper: AuthenticatedHelper = Depends(current_helper)) -> TicketStats:
    scope = ticket_scope(helper)
    active_count = await db.tickets.count_documents({"$and": [scope, {"status": "active"}]})
    archived_count = await db.tickets.count_documents({"$and": [scope, {"status": "archived"}]})
    pipeline = [{"$match": scope}, {"$group": {"_id": None, "count": {"$sum": "$message_count"}}}]
    aggregate = await db.tickets.aggregate(pipeline).to_list(1)
    total_messages = aggregate[0]["count"] if aggregate else 0
    return TicketStats(
        active_count=active_count,
        archived_count=archived_count,
        total_messages=total_messages,
    )


@router.post("", response_model=TicketDetail, status_code=201)
async def create_ticket(
    input_data: TicketCreate,
    helper: AuthenticatedHelper = Depends(current_helper),
) -> TicketDetail:
    existing = await db.tickets.find_one({"$and": [{"channel_id": input_data.channel_id}, ticket_scope(helper)]}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="Un ticket existe déjà pour ce salon Discord.")
    discord = DiscordService()
    member = await discord.fetch_member(input_data.member_id)
    channel = await discord.fetch_text_channel(input_data.channel_id)
    transcript = await discord.fetch_channel_history(input_data.channel_id)
    timestamp = now_iso()
    ticket = TicketDetail(
        id=str(uuid4()),
        title=input_data.title or f"#{channel.get('name', input_data.channel_id)} · {member.display_name or member.username}",
        member=member,
        channel_id=input_data.channel_id,
        channel_name=channel.get("name", input_data.channel_id),
        status="active",
        message_count=len(transcript),
        transcript=transcript,
        notes="",
        vocal_summary="",
        last_synced_at=timestamp,
        created_by=helper.id,
        created_at=timestamp,
        updated_at=timestamp,
    )
    document = ticket.model_dump()
    await db.tickets.insert_one(document)
    return ticket


@router.get("/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: str,
    _: AuthenticatedHelper = Depends(current_helper),
) -> TicketDetail:
    return await ticket_or_404(ticket_id, _)


@router.patch("/{ticket_id}", response_model=TicketDetail)
async def update_ticket(
    ticket_id: str,
    input_data: TicketUpdate,
    _: AuthenticatedHelper = Depends(current_helper),
) -> TicketDetail:
    await ticket_or_404(ticket_id, _)
    updates = input_data.model_dump(exclude_none=True)
    if not updates:
        return await ticket_or_404(ticket_id, _)
    updates["updated_at"] = now_iso()
    await db.tickets.update_one(
        {"$and": [{"id": ticket_id}, ticket_scope(_)]},
        {"$set": updates},
    )
    return await ticket_or_404(ticket_id, _)


@router.post("/{ticket_id}/sync", response_model=TicketDetail)
async def sync_ticket(
    ticket_id: str,
    _: AuthenticatedHelper = Depends(current_helper),
) -> TicketDetail:
    ticket = await ticket_or_404(ticket_id, _)
    if ticket.get("is_demo"):
        await db.tickets.update_one(
            {"id": ticket_id, "demo_ticket": True},
            {"$set": {"last_synced_at": now_iso()}},
        )
        return await ticket_or_404(ticket_id, _)
    transcript = await DiscordService().fetch_channel_history(ticket["channel_id"])
    timestamp = now_iso()
    await db.tickets.update_one(
        {"id": ticket_id},
        {
            "$set": {
                "transcript": [message.model_dump() for message in transcript],
                "message_count": len(transcript),
                "last_synced_at": timestamp,
                "updated_at": timestamp,
            }
        },
    )
    return await ticket_or_404(ticket_id, _)