import os
from datetime import datetime, timezone

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

SANCTION_TYPES = {"avertissement", "bannissement", "kick", "rappel_a_lordre"}

STATUS_SEVERITY = {
    "vierge": 0,
    "vigilance": 1,
    "surveillance": 2,
    "sanctionne": 3,
    "bloque": 4,
}


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


class SanctionAuthor(BaseModel):
    id: str | None = None
    username: str | None = None
    display_name: str | None = None


class Sanction(BaseModel):
    type: str
    reason: str
    created_at: str
    created_by: SanctionAuthor | None = None
    duration: str | None = None


class CreateSanctionPayload(BaseModel):
    type: str
    reason: str = Field(..., min_length=1, max_length=1000)
    duration: str | None = None


class FicheS(BaseModel):
    id: str
    title: str
    content: str
    created_at: str
    created_by: SanctionAuthor | None = None
    active: bool
    closed_at: str | None = None
    closed_by: SanctionAuthor | None = None


class CreateFicheSPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    content: str = Field(..., min_length=1, max_length=8000)


class CasierListItem(BaseModel):
    id: str
    member: CasierMember
    status: str
    sanctions_count: int
    has_active_fiche_s: bool
    last_sanction_at: str | None = None
    last_sanction_label: str | None = None
    created_at: str


class CasierDetailResponse(BaseModel):
    id: str
    member: CasierMember
    status: str
    created_at: str
    sanctions_count: int
    sanctions: list[Sanction]
    fiches_s: list[FicheS]


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
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}


def discord_avatar_url(user: dict) -> str | None:
    avatar = user.get("avatar")
    user_id = user.get("id")
    if not avatar or not user_id:
        return None
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png"


def has_active_fiche_s(casier: dict) -> bool:
    return any(fiche.get("active") for fiche in casier.get("fiches_s", []))


def compute_status(casier: dict) -> str:
    sanctions = casier.get("sanctions", [])

    has_ban = any(s.get("type") == "bannissement" for s in sanctions)
    has_kick = any(s.get("type") == "kick" for s in sanctions)
    has_warning = any(s.get("type") == "avertissement" for s in sanctions)
    has_reminder = any(s.get("type") == "rappel_a_lordre" for s in sanctions)

    if has_ban:
        base_status = "bloque"
    elif has_kick:
        base_status = "sanctionne"
    elif has_warning:
        base_status = "surveillance"
    elif has_reminder:
        base_status = "vigilance"
    else:
        base_status = "vierge"

    if has_active_fiche_s(casier):
        minimum_status = "surveillance"
        if STATUS_SEVERITY[base_status] < STATUS_SEVERITY[minimum_status]:
            return minimum_status

    return base_status


def latest_sanction(casier: dict) -> dict | None:
    sanctions = casier.get("sanctions", [])
    if not sanctions:
        return None
    return sorted(sanctions, key=lambda s: s.get("created_at", ""), reverse=True)[0]


def staff_to_author(staff) -> dict:
    return {
        "id": getattr(staff, "id", None),
        "username": getattr(staff, "username", None),
        "display_name": getattr(staff, "display_name", None),
    }


async def search_guild_members(query: str, limit: int = 10) -> list[dict]:
    url = f"{DISCORD_API_BASE}/guilds/{DISCORD_GUILD_ID}/members/search"
    params = {"query": query, "limit": max(1, min(limit, 25))}

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


def member_from_snapshot(snapshot: dict) -> CasierMember:
    return CasierMember(
        id=snapshot.get("id"),
        username=snapshot.get("username"),
        display_name=snapshot.get("display_name"),
        avatar_url=snapshot.get("avatar_url"),
    )


def snapshot_from_guild_member(guild_member: dict) -> dict:
    user = guild_member.get("user", {})
    return {
        "id": user.get("id"),
        "username": user.get("username") or user.get("id"),
        "display_name": guild_member.get("nick")
        or user.get("global_name")
        or user.get("username"),
        "avatar_url": discord_avatar_url(user),
    }


async def resolve_member(discord_id: str, snapshot: dict | None) -> CasierMember:
    guild_member = await fetch_guild_member(discord_id)

    if guild_member:
        return CasierMember(**snapshot_from_guild_member(guild_member))

    if snapshot:
        return member_from_snapshot(snapshot)

    return CasierMember(id=discord_id, username=discord_id, display_name=discord_id, avatar_url=None)


def build_sanctions(casier: dict) -> list[Sanction]:
    sanctions = [
        Sanction(
            type=s.get("type", "sanction"),
            reason=s.get("reason", ""),
            created_at=s.get("created_at", ""),
            created_by=SanctionAuthor(**s["created_by"]) if s.get("created_by") else None,
            duration=s.get("duration"),
        )
        for s in casier.get("sanctions", [])
    ]
    sanctions.sort(key=lambda item: item.created_at, reverse=True)
    return sanctions


def build_fiches_s(casier: dict) -> list[FicheS]:
    fiches = [
        FicheS(
            id=f.get("id", ""),
            title=f.get("title", ""),
            content=f.get("content", ""),
            created_at=f.get("created_at", ""),
            created_by=SanctionAuthor(**f["created_by"]) if f.get("created_by") else None,
            active=bool(f.get("active", True)),
            closed_at=f.get("closed_at"),
            closed_by=SanctionAuthor(**f["closed_by"]) if f.get("closed_by") else None,
        )
        for f in casier.get("fiches_s", [])
    ]
    fiches.sort(key=lambda item: item.created_at, reverse=True)
    return fiches


async def build_detail_response(casier: dict) -> CasierDetailResponse:
    discord_id = casier.get("discord_id")
    member = await resolve_member(discord_id, casier.get("discord_member_snapshot"))

    sanctions = build_sanctions(casier)
    fiches_s = build_fiches_s(casier)

    return CasierDetailResponse(
        id=str(casier["_id"]),
        member=member,
        status=compute_status(casier),
        created_at=casier.get("created_at", ""),
        sanctions_count=len(sanctions),
        sanctions=sanctions,
        fiches_s=fiches_s,
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

        member = await resolve_member(discord_id, casier.get("discord_member_snapshot"))
        latest = latest_sanction(casier)

        results.append(
            CasierListItem(
                id=str(casier["_id"]),
                member=member,
                status=compute_status(casier),
                sanctions_count=len(casier.get("sanctions", [])),
                has_active_fiche_s=has_active_fiche_s(casier),
                last_sanction_at=latest.get("created_at") if latest else None,
                last_sanction_label=latest.get("reason") if latest else "Aucune sanction enregistrée.",
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
    snapshot = snapshot_from_guild_member(guild_member)

    document = {
        "discord_id": discord_id,
        "created_at": now,
        "status": "vierge",
        "discord_member_snapshot": snapshot,
        "created_by": staff_to_author(staff),
        "sanctions": [],
        "fiches_s": [],
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

    if not casier.get("discord_id"):
        raise HTTPException(status_code=500, detail="Casier invalide : discord_id manquant.")

    return await build_detail_response(casier)


@router.post("/{casier_id}/sanctions", response_model=CasierDetailResponse, status_code=status.HTTP_201_CREATED)
async def add_sanction(
    casier_id: str,
    payload: CreateSanctionPayload,
    staff=Depends(current_staff),
):
    if payload.type not in SANCTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Type de sanction invalide. Valeurs autorisées : {sorted(SANCTION_TYPES)}",
        )

    object_id = object_id_or_400(casier_id)
    casier = await db.casiers.find_one({"_id": object_id})

    if not casier:
        raise HTTPException(status_code=404, detail="Casier introuvable.")

    sanction = {
        "type": payload.type,
        "reason": payload.reason.strip(),
        "created_at": now_iso(),
        "created_by": staff_to_author(staff),
        "duration": payload.duration,
    }

    await db.casiers.update_one({"_id": object_id}, {"$push": {"sanctions": sanction}})

    updated = await db.casiers.find_one({"_id": object_id})
    return await build_detail_response(updated)


@router.post("/{casier_id}/fiches-s", response_model=CasierDetailResponse, status_code=status.HTTP_201_CREATED)
async def add_fiche_s(
    casier_id: str,
    payload: CreateFicheSPayload,
    staff=Depends(current_staff),
):
    object_id = object_id_or_400(casier_id)
    casier = await db.casiers.find_one({"_id": object_id})

    if not casier:
        raise HTTPException(status_code=404, detail="Casier introuvable.")

    fiche = {
        "id": str(ObjectId()),
        "title": payload.title.strip(),
        "content": payload.content,
        "created_at": now_iso(),
        "created_by": staff_to_author(staff),
        "active": True,
        "closed_at": None,
        "closed_by": None,
    }

    await db.casiers.update_one({"_id": object_id}, {"$push": {"fiches_s": fiche}})

    updated = await db.casiers.find_one({"_id": object_id})
    return await build_detail_response(updated)


@router.patch("/{casier_id}/fiches-s/{fiche_id}/close", response_model=CasierDetailResponse)
async def close_fiche_s(
    casier_id: str,
    fiche_id: str,
    staff=Depends(current_staff),
):
    object_id = object_id_or_400(casier_id)
    casier = await db.casiers.find_one({"_id": object_id})

    if not casier:
        raise HTTPException(status_code=404, detail="Casier introuvable.")

    fiches = casier.get("fiches_s", [])
    target = next((f for f in fiches if f.get("id") == fiche_id), None)

    if not target:
        raise HTTPException(status_code=404, detail="Fiche S introuvable.")

    if not target.get("active", True):
        raise HTTPException(status_code=409, detail="Cette fiche S est déjà clôturée.")

    await db.casiers.update_one(
        {"_id": object_id, "fiches_s.id": fiche_id},
        {
            "$set": {
                "fiches_s.$.active": False,
                "fiches_s.$.closed_at": now_iso(),
                "fiches_s.$.closed_by": staff_to_author(staff),
            }
        },
    )

    updated = await db.casiers.find_one({"_id": object_id})
    return await build_detail_response(updated)
