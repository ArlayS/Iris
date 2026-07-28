from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from database import db
from models.staff import (
    AbsenceCreate,
    AbsenceEntry,
    MeetingSummary,
    MeetingSummaryCreate,
    MeetingSummaryUpdate,
)
from models.ticket import AuthenticatedHelper
from services.auth_service import current_responsable, current_staff


router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/absences", response_model=list[AbsenceEntry])
async def list_absences(_: AuthenticatedHelper = Depends(current_staff)) -> list[AbsenceEntry]:
    return await db.absences.find({}, {"_id": 0}).sort("start_date", 1).to_list(1000)


@router.post("/absences", response_model=AbsenceEntry, status_code=status.HTTP_201_CREATED)
async def create_absence(
    payload: AbsenceCreate,
    helper: AuthenticatedHelper = Depends(current_staff),
) -> AbsenceEntry:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="La date de fin doit suivre la date de début.")
    entry = AbsenceEntry(
        id=str(uuid4()),
        helper={
            "id": helper.id,
            "username": helper.username,
            "display_name": helper.global_name,
            "avatar_url": helper.avatar_url,
        },
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason.strip(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await db.absences.insert_one(entry.model_dump())
    return entry


@router.delete("/absences/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_absence(
    absence_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
) -> None:
    result = await db.absences.delete_one({"id": absence_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Absence introuvable.")


@router.get("/meetings", response_model=list[MeetingSummary])
async def list_meetings(_: AuthenticatedHelper = Depends(current_staff)) -> list[MeetingSummary]:
    return await db.meeting_summaries.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/meetings/{meeting_id}", response_model=MeetingSummary)
async def get_meeting(
    meeting_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
) -> MeetingSummary:
    meeting = await db.meeting_summaries.find_one({"id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Résumé introuvable.")
    return meeting


@router.post("/meetings", response_model=MeetingSummary, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingSummaryCreate,
    helper: AuthenticatedHelper = Depends(current_responsable),
) -> MeetingSummary:
    now = datetime.now(timezone.utc).isoformat()
    meeting = MeetingSummary(
        id=str(uuid4()),
        title=payload.title.strip(),
        content_markdown=payload.content_markdown,
        author={
            "id": helper.id,
            "username": helper.username,
            "display_name": helper.global_name,
            "avatar_url": helper.avatar_url,
        },
        created_at=now,
        updated_at=now,
    )
    await db.meeting_summaries.insert_one(meeting.model_dump())
    return meeting


@router.put("/meetings/{meeting_id}", response_model=MeetingSummary)
async def update_meeting(
    meeting_id: str,
    payload: MeetingSummaryUpdate,
    _: AuthenticatedHelper = Depends(current_staff),
) -> MeetingSummary:
    existing = await db.meeting_summaries.find_one({"id": meeting_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Résumé introuvable.")
    updated_at = datetime.now(timezone.utc).isoformat()
    await db.meeting_summaries.update_one(
        {"id": meeting_id},
        {"$set": {"title": payload.title.strip(), "content_markdown": payload.content_markdown, "updated_at": updated_at}},
    )
    existing.update(title=payload.title.strip(), content_markdown=payload.content_markdown, updated_at=updated_at)
    return existing


@router.delete("/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
) -> None:
    result = await db.meeting_summaries.delete_one({"id": meeting_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Résumé introuvable.")
