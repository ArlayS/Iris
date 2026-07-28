import asyncio
import os
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

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
from services.storage_service import extension_from_filename, get_object, put_object_from_file

router = APIRouter(prefix="/staff", tags=["staff"])

MEETING_IMAGE_TYPES = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_MEETING_IMAGE_SIZE = 10 * 1024 * 1024  # 10 Mo


def _meeting_status(content_markdown: str) -> str:
    return "redige" if content_markdown.strip() else "en_attente_resume"


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
    return await db.meeting_summaries.find({}, {"_id": 0}).sort("meeting_date", -1).to_list(500)


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
        agenda=payload.agenda.strip(),
        content_markdown=payload.content_markdown,
        status=_meeting_status(payload.content_markdown),
        meeting_date=payload.meeting_date,
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
    new_status = _meeting_status(payload.content_markdown)
    await db.meeting_summaries.update_one(
        {"id": meeting_id},
        {"$set": {
            "title": payload.title.strip(),
            "agenda": payload.agenda.strip(),
            "content_markdown": payload.content_markdown,
            "status": new_status,
            "updated_at": updated_at,
        }},
    )
    existing.update(
        title=payload.title.strip(),
        agenda=payload.agenda.strip(),
        content_markdown=payload.content_markdown,
        status=new_status,
        updated_at=updated_at,
    )
    return existing


@router.delete("/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
) -> None:
    result = await db.meeting_summaries.delete_one({"id": meeting_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Résumé introuvable.")
MEETING_MEDIA_TYPES = {
    "jpg", "jpeg", "png", "webp", "gif",
    "mp4", "webm", "mov",
    "mp3", "wav", "ogg", "m4a",
}
MAX_MEETING_MEDIA_SIZE = 50 * 1024 * 1024  # 50 Mo

VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a"}


def _media_content_type(extension: str) -> str:
    if extension in VIDEO_EXTENSIONS:
        return f"video/{extension}"
    if extension in AUDIO_EXTENSIONS:
        audio_map = {"mp3": "mpeg", "wav": "wav", "ogg": "ogg", "m4a": "mp4"}
        return f"audio/{audio_map[extension]}"
    return f"image/{extension if extension != 'jpg' else 'jpeg'}"


@router.post("/meetings/upload-image")
async def upload_meeting_media(
    file: UploadFile = File(...),
    _: AuthenticatedHelper = Depends(current_staff),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=422, detail="Choisissez un fichier à envoyer.")

    extension = extension_from_filename(file.filename)
    if extension not in MEETING_MEDIA_TYPES:
        raise HTTPException(status_code=422, detail="Format non autorisé.")

    temp_path: str | None = None
    total_size = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > MAX_MEETING_MEDIA_SIZE:
                    raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 50 Mo).")
                temp_file.write(chunk)

        media_id = str(uuid4())
        media_filename = f"{media_id}.{extension}"
        media_path = f"iris/meeting-images/{media_filename}"
        content_type = _media_content_type(extension)
        await asyncio.to_thread(put_object_from_file, media_path, temp_path, content_type)

        return {"url": f"/api/staff/meetings/images/{media_filename}"}
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.get("/meetings/images/{filename}")
async def get_meeting_media(filename: str) -> StreamingResponse:
    extension = filename.rsplit(".", 1)[-1].lower()
    content_type = _media_content_type(extension)
    try:
        content, _unused = await asyncio.to_thread(get_object, f"iris/meeting-images/{filename}")
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Fichier introuvable.") from error
    return StreamingResponse(BytesIO(content), media_type=content_type)
