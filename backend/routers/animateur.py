"""Router pour la gestion des projets animateur."""
import asyncio
import mimetypes
import os
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, status
from pydantic import BaseModel, Field

from config import DISCORD_ANIMATEUR_ROLE_ID
from database import db
from models.project import Project, ProjectUpdate
from models.ticket import AuthenticatedHelper, HelperIdentity
from services.audit_service import log_auth_event
from services.auth_service import (
    current_staff,
    current_responsable,
    current_helper,
    is_animateur_helper,
    is_responsable_helper,
)
from services.discord_service import DiscordService
from services.file_response_service import safe_content_type, stream_local_file
from services.storage_service import extension_from_filename, put_object_from_file, sanitize_extension

router = APIRouter(prefix="/animateur/projects", tags=["animateur-projects"])
tasks_router = APIRouter(prefix="/animateur/tasks", tags=["animateur-tasks"])
resources_router = APIRouter(prefix="/animateur/resources", tags=["animateur-resources"])
members_router = APIRouter(prefix="/animateur/members", tags=["animateur-members"])


def _upload_limit_mb() -> int:
    try:
        value = int(os.environ.get("ANIMATEUR_MAX_UPLOAD_MB", "100"))
    except ValueError:
        return 100
    return value if value > 0 else 100


# Taille max d'un rendu de tâche ou d'une ressource de projet.
MAX_UPLOAD_MB = _upload_limit_mb()
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_to_iso(value):
    return value.isoformat() if value else None


def _helper_identity(helper: AuthenticatedHelper) -> dict:
    return {
        "id": helper.id,
        "username": helper.username,
        "display_name": getattr(helper, "global_name", None) or getattr(helper, "display_name", helper.username),
        "avatar_url": getattr(helper, "avatar_url", None),
    }


class ProjectDetailsPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


async def current_project_editor(request: Request) -> AuthenticatedHelper:
    helper = await current_helper(request)
    if await is_animateur_helper(helper.id):
        return helper
    if await is_responsable_helper(helper.id):
        return helper
    raise HTTPException(status_code=403, detail="Rôle Animateur ou Responsable requis.")


def _is_project_member(project: dict | None, helper_id: str) -> bool:
    if not project:
        return False
    if (project.get("created_by") or {}).get("id") == helper_id:
        return True
    return any(member.get("id") == helper_id for member in project.get("members") or [])


async def _ensure_project_member_or_responsable(project: dict | None, helper: AuthenticatedHelper) -> None:
    if _is_project_member(project, helper.id) or await is_responsable_helper(helper.id):
        return
    raise HTTPException(status_code=403, detail="Réservé aux membres du projet ou à un Responsable.")


def _upload_extension(filename: str | None) -> str:
    return sanitize_extension(extension_from_filename(filename or ""))


# Absents de la table intégrée de Python (image python:3.11-slim sans /etc/mime.types).
_EXTRA_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "webp": "image/webp",
}


def _upload_content_type(extension: str) -> str:
    # Déduit de l'extension assainie : le type annoncé par le navigateur n'est jamais conservé.
    guessed = _EXTRA_CONTENT_TYPES.get(extension) or mimetypes.guess_type(f"fichier.{extension}")[0]
    return safe_content_type(guessed)


async def _store_upload(file: UploadFile, storage_path: str, content_type: str) -> int:
    """Copie l'upload par blocs de 1 Mio vers le stockage ; 413 au-delà de MAX_UPLOAD_SIZE."""
    temp_path = None
    total_size = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fichier trop volumineux (max {MAX_UPLOAD_MB} Mo).",
                    )
                temp_file.write(chunk)
        await asyncio.to_thread(put_object_from_file, storage_path, temp_path, content_type)
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
    return total_size


@members_router.get("/search", response_model=list[HelperIdentity])
async def search_animateur_members(_: AuthenticatedHelper = Depends(current_staff)):
    if not DISCORD_ANIMATEUR_ROLE_ID:
        raise HTTPException(status_code=503, detail="Rôle animateur non configuré.")
    discord = DiscordService()
    return await discord.fetch_helpers(DISCORD_ANIMATEUR_ROLE_ID)


@router.get("")
async def list_projects(_: AuthenticatedHelper = Depends(current_staff)):
    return await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_staff),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    await log_auth_event(
        "project.viewed",
        request,
        helper=helper,
        status_code=200,
        details={
            "project_id": project_id,
            "title": project.get("title"),
        },
    )

    return Project(**project)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Project)
async def create_project(
    payload: dict,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_staff),
):
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Le titre est requis.")

    start_date = payload.get("start_date")
    end_date = payload.get("end_date")

    if not start_date:
        raise HTTPException(status_code=422, detail="La date de début est requise.")
    if end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="La date de fin doit suivre la date de début.")

    now = _now()
    identity = _helper_identity(helper)
    project = {
        "id": str(uuid4()),
        "title": title,
        "description": (payload.get("description") or "").strip(),
        "content_markdown": "",
        "status": "en_cours",
        "start_date": start_date.isoformat() if hasattr(start_date, "isoformat") else start_date,
        "end_date": end_date.isoformat() if hasattr(end_date, "isoformat") else end_date,
        "members": [identity],
        "created_by": identity,
        "created_at": now,
        "updated_at": now,
    }

    await db.projects.insert_one(project)

    await log_auth_event(
        "project.created",
        request,
        helper=helper,
        status_code=201,
        details={
            "project_id": project["id"],
            "title": project["title"],
            "start_date": project["start_date"],
            "end_date": project["end_date"],
        },
    )

    return Project(**project)


@router.patch("/{project_id}/details", response_model=Project)
async def update_project_details(
    project_id: str,
    payload: ProjectDetailsPayload,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_responsable),
) -> Project:
    """Modifie uniquement le titre et la description d'un projet. Réservé au rôle Responsable."""
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    title_after = payload.title.strip()
    description_after = payload.description.strip()

    if not title_after:
        raise HTTPException(status_code=422, detail="Le titre est requis.")

    previous_title = existing.get("title", "")
    previous_description = existing.get("description", "")
    updated_at = _now()

    await db.projects.update_one(
        {"id": project_id},
        {
            "$set": {
                "title": title_after,
                "description": description_after,
                "updated_at": updated_at,
            }
        },
    )

    updated = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="Projet introuvable après mise à jour.")

    if previous_title != title_after or previous_description != description_after:
        await log_auth_event(
            "project.details.updated",
            request,
            helper=helper,
            status_code=200,
            details={
                "project_id": project_id,
                "before": {"title": previous_title, "description": previous_description},
                "after": {"title": title_after, "description": description_after},
            },
        )

    return Project(**updated)


@router.put("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_project_editor),
) -> Project:
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    await _ensure_project_member_or_responsable(existing, helper)

    title_after = (payload.title or "").strip()
    description_after = (payload.description or "").strip()
    content_after = payload.content_markdown or ""
    end_date_value = _date_to_iso(payload.end_date)
    status_value = payload.status or existing.get("status", "en_cours")

    previous_title = existing.get("title", "")
    previous_description = existing.get("description", "")
    previous_content = existing.get("content_markdown", "")
    previous_end_date = existing.get("end_date")
    previous_status = existing.get("status")

    updated_at = _now()

    result = await db.projects.update_one(
        {"id": project_id},
        {
            "$set": {
                "title": title_after,
                "description": description_after,
                "content_markdown": content_after,
                "end_date": end_date_value,
                "status": status_value,
                "updated_at": updated_at,
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    updated = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="Projet introuvable après mise à jour.")

    title_changed = previous_title != title_after
    description_changed = previous_description != description_after
    content_changed = previous_content != content_after
    end_date_changed = previous_end_date != end_date_value
    status_changed = previous_status != status_value

    if title_changed or description_changed or content_changed or end_date_changed or status_changed:
        await log_auth_event(
            "project.content.updated",
            request,
            helper=helper,
            status_code=200,
            details={
                "project_id": project_id,
                "title": title_after,
                "title_changed": title_changed,
                "description_changed": description_changed,
                "content_changed": content_changed,
                "end_date_changed": end_date_changed,
                "status_changed": status_changed,
                "before": {
                    "title": previous_title,
                    "description": previous_description,
                    "content_length": len(previous_content or ""),
                    "end_date": previous_end_date,
                    "status": previous_status,
                },
                "after": {
                    "title": title_after,
                    "description": description_after,
                    "content_length": len(content_after or ""),
                    "end_date": end_date_value,
                    "status": status_value,
                },
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )

    return Project(**updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_responsable),
) -> None:
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    await db.project_tasks.delete_many({"project_id": project_id})
    await db.project_resources.delete_many({"project_id": project_id})

    result = await db.projects.delete_one({"id": project_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    await log_auth_event(
        "project.deleted",
        request,
        helper=helper,
        status_code=204,
        details={
            "project_id": project_id,
            "title": existing.get("title"),
        },
    )


@router.post("/{project_id}/members")
async def add_member(
    project_id: str,
    payload: dict,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_staff),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    member_id = payload.get("member_id")
    if not member_id:
        raise HTTPException(status_code=422, detail="member_id requis.")
    if any(m["id"] == member_id for m in project.get("members", [])):
        raise HTTPException(status_code=409, detail="Ce membre fait déjà partie du projet.")

    if not DISCORD_ANIMATEUR_ROLE_ID:
        raise HTTPException(status_code=503, detail="Rôle animateur non configuré.")

    discord = DiscordService()
    candidates = await discord.fetch_helpers(DISCORD_ANIMATEUR_ROLE_ID)
    member = next((m for m in candidates if m.id == member_id), None)
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable parmi les animateurs.")

    identity = {
        "id": member.id,
        "username": member.username,
        "display_name": member.display_name,
        "avatar_url": member.avatar_url,
    }

    updated_at = _now()
    await db.projects.update_one(
        {"id": project_id},
        {"$push": {"members": identity}, "$set": {"updated_at": updated_at}},
    )

    project["members"].append(identity)
    project["updated_at"] = updated_at

    await log_auth_event(
        "project.member.added",
        request,
        helper=helper,
        status_code=200,
        details={
            "project_id": project_id,
            "member_id": identity["id"],
            "member_username": identity["username"],
        },
    )

    return project


@router.get("/{project_id}/tasks")
async def list_project_tasks(
    project_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
):
    return await db.project_tasks.find({"project_id": project_id}, {"_id": 0}).sort("due_date", 1).to_list(500)


@router.post("/{project_id}/tasks", status_code=status.HTTP_201_CREATED)
async def create_project_task(
    project_id: str,
    payload: dict,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_responsable),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    assignee_id = payload.get("assignee_id")
    assignee = next((m for m in project.get("members", []) if m["id"] == assignee_id), None)
    if not assignee:
        raise HTTPException(status_code=422, detail="Le membre assigné doit faire partie du projet.")

    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="Le titre est requis.")

    now = _now()
    task = {
        "id": str(uuid4()),
        "project_id": project_id,
        "title": title,
        "description": (payload.get("description") or "").strip(),
        "due_date": payload.get("due_date").isoformat() if hasattr(payload.get("due_date"), "isoformat") else payload.get("due_date"),
        "assignee": assignee,
        "status": "a_faire",
        "submission_note": "",
        "created_at": now,
        "updated_at": now,
    }

    await db.project_tasks.insert_one(task)

    await log_auth_event(
        "project.task.created",
        request,
        helper=helper,
        status_code=201,
        details={
            "project_id": project_id,
            "task_id": task["id"],
            "title": task["title"],
            "assignee_id": assignee["id"],
        },
    )

    return task


@tasks_router.put("/{task_id}/submit")
async def submit_task(
    task_id: str,
    submission_content: str = Form(""),
    file: UploadFile | None = File(None),
    request: Request = None,
    helper: AuthenticatedHelper = Depends(current_staff),
):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")

    is_assignee = (existing.get("assignee") or {}).get("id") == helper.id
    if not is_assignee and not await is_responsable_helper(helper.id):
        raise HTTPException(
            status_code=403,
            detail="Seul le membre assigné ou un Responsable peut rendre cette tâche.",
        )

    submission_file = None
    if file and file.filename:
        extension = _upload_extension(file.filename)
        content_type = _upload_content_type(extension)
        file_id = str(uuid4())
        storage_path = f"iris/task-submissions/{file_id}.{extension}"
        size = await _store_upload(file, storage_path, content_type)

        submission_file = {
            "original_filename": file.filename,
            "content_type": content_type,
            "size": size,
            "storage_path": storage_path,
        }

    updated_at = _now()
    updates = {
        "status": "rendu",
        "submission_note": submission_content,
        "submission_file": submission_file,
        "submitted_at": updated_at,
        "updated_at": updated_at,
    }

    await db.project_tasks.update_one({"id": task_id}, {"$set": updates})
    existing.update(updates)

    if request is not None:
        await log_auth_event(
            "project.task.submitted",
            request,
            helper=helper,
            status_code=200,
            details={
                "task_id": task_id,
                "project_id": existing.get("project_id"),
                "has_file": submission_file is not None,
            },
        )

    return existing


@tasks_router.get("/{task_id}/submission/download")
async def download_submission(
    task_id: str,
    request: Request,
    _: AuthenticatedHelper = Depends(current_staff),
):
    task = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task or not task.get("submission_file"):
        raise HTTPException(status_code=404, detail="Aucun fichier pour cette tâche.")

    submission_file = task["submission_file"]
    if not submission_file.get("storage_path"):
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque.")

    return stream_local_file(
        request,
        submission_file["storage_path"],
        content_type=safe_content_type(submission_file.get("content_type")),
        filename=submission_file.get("original_filename") or "fichier",
        attachment=True,
    )


@tasks_router.put("/{task_id}/validate")
async def validate_task(
    task_id: str,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_responsable),
):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")

    updated_at = _now()
    await db.project_tasks.update_one(
        {"id": task_id},
        {"$set": {"status": "valide", "updated_at": updated_at}},
    )

    existing["status"] = "valide"
    existing["updated_at"] = updated_at

    await log_auth_event(
        "project.task.validated",
        request,
        helper=helper,
        status_code=200,
        details={
            "task_id": task_id,
            "project_id": existing.get("project_id"),
        },
    )

    return existing


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_responsable),
):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    result = await db.project_tasks.delete_one({"id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")

    await log_auth_event(
        "project.task.deleted",
        request,
        helper=helper,
        status_code=204,
        details={
            "task_id": task_id,
            "project_id": existing.get("project_id") if existing else None,
        },
    )


@router.get("/{project_id}/resources")
async def list_resources(
    project_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
):
    return await db.project_resources.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/{project_id}/resources", status_code=status.HTTP_201_CREATED)
async def upload_resource(
    project_id: str,
    request: Request,
    title: str = Form(...),
    file: UploadFile = File(...),
    helper: AuthenticatedHelper = Depends(current_staff),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1})
    if not project:
        await file.close()
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    extension = _upload_extension(file.filename)
    content_type = _upload_content_type(extension)
    resource_id = str(uuid4())
    storage_path = f"iris/project-resources/{resource_id}.{extension}"
    size = await _store_upload(file, storage_path, content_type)

    now = _now()
    resource = {
        "id": resource_id,
        "project_id": project_id,
        "title": title.strip(),
        "original_filename": file.filename,
        "content_type": content_type,
        "size": size,
        "storage_path": storage_path,
        "uploaded_by": _helper_identity(helper),
        "created_at": now,
    }

    await db.project_resources.insert_one(resource)

    await log_auth_event(
        "project.resource.uploaded",
        request,
        helper=helper,
        status_code=201,
        details={
            "project_id": project_id,
            "resource_id": resource_id,
            "title": resource["title"],
            "original_filename": resource["original_filename"],
        },
    )

    resource.pop("_id", None)
    return resource


@resources_router.get("/{resource_id}/download")
async def download_resource(
    resource_id: str,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_project_editor),
):
    resource = await db.project_resources.find_one({"id": resource_id}, {"_id": 0})
    if not resource:
        raise HTTPException(status_code=404, detail="Ressource introuvable.")

    project = await db.projects.find_one({"id": resource.get("project_id")}, {"_id": 0, "created_by": 1, "members": 1})
    await _ensure_project_member_or_responsable(project, helper)

    return stream_local_file(
        request,
        resource["storage_path"],
        content_type=safe_content_type(resource.get("content_type")),
        filename=resource.get("original_filename") or "fichier",
        attachment=True,
    )


@resources_router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: str,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_responsable),
):
    existing = await db.project_resources.find_one({"id": resource_id}, {"_id": 0})
    result = await db.project_resources.delete_one({"id": resource_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ressource introuvable.")

    await log_auth_event(
        "project.resource.deleted",
        request,
        helper=helper,
        status_code=204,
        details={
            "resource_id": resource_id,
            "project_id": existing.get("project_id") if existing else None,
        },
    )
