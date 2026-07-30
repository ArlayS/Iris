from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from database import db
from services.auth_service import current_staff

router = APIRouter(prefix="/casier", tags=["moderation-casiers"])


class MemberSearchResult(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class CreateCasierPayload(BaseModel):
    member_id: Optional[str] = None
    discord_id: Optional[str] = Field(default=None, min_length=17, max_length=21)


class CasierResponse(BaseModel):
    id: str
    member_id: str
    discord_id: str
    created_at: str


@router.get("/search-members", response_model=list[MemberSearchResult])
async def search_members(
    q: str = Query(..., min_length=1),
    staff=Depends(current_staff),
):
    needle = q.strip().lower()
    if not needle:
        return []

    members_cursor = db.members.find({
        "$or": [
            {"username_lower": {"$regex": needle}},
            {"display_name_lower": {"$regex": needle}},
            {"id": {"$regex": needle}},
        ]
    }).limit(10)

    results = []
    async for member in members_cursor:
        results.append(
            MemberSearchResult(
                id=member["id"],
                username=member["username"],
                display_name=member.get("display_name"),
                avatar_url=member.get("avatar_url"),
            )
        )

    return results


@router.post("", response_model=CasierResponse, status_code=status.HTTP_201_CREATED)
async def create_casier(
    payload: CreateCasierPayload,
    staff=Depends(current_staff),
):
    member_id = payload.member_id
    discord_id = payload.discord_id

    if not member_id and not discord_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="member_id ou discord_id est requis.",
        )

    member = None

    if member_id:
        member = await db.members.find_one({"id": member_id})
        if not member:
            raise HTTPException(status_code=404, detail="Membre introuvable.")
        discord_id = member["id"]

    elif discord_id:
        member = await db.members.find_one({"id": discord_id})
        member_id = member["id"] if member else discord_id

    existing = await db.casiers.find_one({"discord_id": discord_id})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un casier existe déjà pour ce membre.",
        )

    now = datetime.now(timezone.utc).isoformat()

    document = {
        "member_id": member_id,
        "discord_id": discord_id,
        "created_at": now,
        "created_by": {
            "id": staff["id"],
            "username": staff["username"],
            "display_name": staff.get("display_name"),
        },
        "entries": [],
        "notes": [],
    }

    result = await db.casiers.insert_one(document)

    return CasierResponse(
        id=str(result.inserted_id),
        member_id=member_id,
        discord_id=discord_id,
        created_at=now,
    )
