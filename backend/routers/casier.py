import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from database import db
from services.auth_service import current_staff

router = APIRouter(prefix="/moderation/casiers", tags=["moderation-casiers"])

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
DISCORD_API_BASE = "https://discord.com/api/v10"


class MemberSearchResult(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class CreateCasierPayload(BaseModel):
    discord_id: str = Field(..., min_length=17, max_length=21)


class CasierResponse(BaseModel):
    id: str
    discord_id: str
    created_at: str


class CasierMember(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class CasierListItem(BaseModel):
    id: str
    member: CasierMember
    status: str
    notes_count: int
    sanctions_count: int
    last_entry_at: str | None = None
    last_entry_label: str | None = None
    created_at: str


class CasierEntryAuthor(BaseModel):
    id: str | None = None
    username: str | None = None
    display_name: str | None = None


class CasierEntry(BaseModel):
    type: str
    reason: str
    created_at: str
    created_by: CasierEntryAuthor | None = None
    duration: str | None = None


class CasierDetailResponse(BaseModel):
    id: str
    member: CasierMember
    status: str
    created_at: str
    notes_count: int
    sanctions_count: int
    entries: list[CasierEntry]
    notes: list[CasierEntry]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def object_id_or_400(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifiant invalide.")


def ensure_discord_config():
    if not DISCORD_BOT_TOKEN or not DISCORD_GUILD_ID:
        raise HTTPException(status_code=500, detail="Configuration Discord manquante.")


def discord_headers() -> dict:
    ensure_discord_config()
    return {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    }


def compute_status(casier: dict) -> str:
    if casier.get("status"):
        return casier["status"]

    entries = casier.get("entries", [])

    has_ban = any(entry.get("type") == "ban" for entry in entries)
    has_timeout = any(entry.get("type") == "timeout" for entry in entries)
    has_warning = any(entry.get("type") == "warning" for entry in entries)

    if has_ban:
        return "bloque"
    if has_timeout:
        return "sanctionne"
    if has_warning:
        return "surveillance"
    return "vierge"


def latest_casier_event(casier: dict) -> dict | None:
    entries = casier.get("entries", [])
    notes = casier.get("notes", [])
    combined = [*entries, *notes]

    if not combined:
        return None

    combined.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return combined[0]


def discord_avatar_url(user: dict) -> str | None:
    avatar = user.get("avatar")
    user_id = user.get("id")
    if not avatar or not user_id:
        return None
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png"


async def search_guild_members(query: str, limit: int = 10) -> list[dict]:
    url = f"{DISCORD_API_BASE}/guilds/{DISCORD_GUILD_ID}/members/search"
    params = {
        "query": query,
        "limit": max(1, min(limit, 25)),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=discord_headers(), params=params)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Recherche Discord impossible ({response.status_code}).",
        )

    payload = response.json()
    results = []

    for item in payload:
        user = item.get("user", {})
        results.append(
            {
                "id": user.get("id"),
                "username": user.get("username") or user.get("id"),
                "display_name": item.get("nick") or user.get("global_name") or user.get("username"),
                "avatar_url": discord_avatar_url(user),
            }
        )

    return results


async def fetch_guild_member(discord_id: str) -> dict | None:
    url = f"{DISCORD_API_BASE}/guilds/{DISCORD_GUILD_ID}/members/{discord_id}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=discord_headers())

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Impossible de récupérer le membre Discord ({response.status_code}).",
        )

    return response.json()


async def resolve_member_from_discord(discord_id: str) -> CasierMember:
    guild_member = await fetch_guild_member(discord_id)

    if guild_member:
        user = guild_member.get("user", {})
        return CasierMember(
            id=user.get("id"),
            username=user.get("username") or user.get("id"),
            display_name=guild_member.get("nick") or user.get("global_name") or user.get("username"),
            avatar_url=discord_avatar_url(user),
        )

    return CasierMember(
        id=discord_id,
        username=discord_id,
        display_name=discord_id,
        avatar_url=None,
    )


@router.get("/search-members", response_model=list[MemberSearchResult])
async def search_members(
    q: str = Query(..., min_length=1),
    staff=Depends(current_staff),
):
    needle = q.strip()
    if not needle:
        return []

    results = await search_guild_members(needle, limit=10)
    return [MemberSearchResult(**member) for member in results]


@router.get("", response_model=list[CasierListItem])
async def list_casiers(
    staff=Depends(current_staff),
):
    cursor = db.casiers.find().sort("created_at", -1)

    results = []
    async for casier in cursor:
        discord_id = casier.get("discord_id")
        if not discord_id:
            continue

        member = await resolve_member_from_discord(discord_id)
        latest = latest_casier_event(casier)

        results.append(
            CasierListItem(
                id=str(casier["_id"]),
                member=member,
                status=compute_status(casier),
                notes_count=len(casier.get("notes", [])),
                sanctions_count=len(casier.get("entries", [])),
                last_entry_at=latest.get("created_at") if latest else casier.get("created_at"),
                last_entry_label=latest.get("reason") if latest else "Dossier créé.",
                created_at=casier.get("created_at", ""),
            )
        )

    return results


@router.post("", response_model=CasierResponse, status_code=status.HTTP_201_CREATED)
async def create_casier(
    payload: CreateCasierPayload,
    staff=Depends(current_staff),
):
    discord_id = payload.discord_id.strip()

    guild_member = await fetch_guild_member(discord_id)
    if not guild_member:
        raise HTTPException(
            status_code=404,
            detail="Membre introuvable sur le serveur Discord.",
        )

    existing = await db.casiers.find_one({"discord_id": discord_id})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un casier existe déjà pour ce membre.",
        )

    now = now_iso()

    document = {
        "discord_id": discord_id,
        "created_at": now,
        "status": "vierge",
        "discord_member_snapshot": {
            "id": guild_member.get("user", {}).get("id"),
            "username": guild_member.get("user", {}).get("username"),
            "display_name": guild_member.get("nick")
            or guild_member.get("user", {}).get("global_name")
            or guild_member.get("user", {}).get("username"),
            "avatar_url": discord_avatar_url(guild_member.get("user", {})),
        },
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
        discord_id=discord_id,
        created_at=now,
    )


@router.get("/{casier_id}", response_model=CasierDetailResponse)
async def get_casier(
    casier_id: str,
    staff=Depends(current_staff),
):
    object_id = object_id_or_400(casier_id)
    casier = await db.casiers.find_one({"_id": object_id})

    if not casier:
        raise HTTPException(status_code=404, detail="Casier introuvable.")

    discord_id = casier.get("discord_id")
    if not discord_id:
        raise HTTPException(status_code=500, detail="Casier invalide : discord_id manquant.")

    member = await resolve_member_from_discord(discord_id)

    entries = [
        CasierEntry(
            type=entry.get("type", "entry"),
            reason=entry.get("reason", ""),
            created_at=entry.get("created_at", ""),
            created_by=CasierEntryAuthor(**entry["created_by"]) if entry.get("created_by") else None,
            duration=entry.get("duration"),
        )
        for entry in casier.get("entries", [])
    ]

    notes = [
        CasierEntry(
            type=note.get("type", "note"),
            reason=note.get("reason", ""),
            created_at=note.get("created_at", ""),
            created_by=CasierEntryAuthor(**note["created_by"]) if note.get("created_by") else None,
            duration=note.get("duration"),
        )
        for note in casier.get("notes", [])
    ]

    entries.sort(key=lambda item: item.created_at, reverse=True)
    notes.sort(key=lambda item: item.created_at, reverse=True)

    return CasierDetailResponse(
        id=str(casier["_id"]),
        member=member,
        status=compute_status(casier),
        created_at=casier.get("created_at", ""),
        notes_count=len(notes),
        sanctions_count=len(entries),
        entries=entries,
        notes=notes,
    )
