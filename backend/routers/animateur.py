"""Router pour la gestion des projets animateur.

Suit le pattern de routers/staff.py : from database import db,
id en uuid4, identite embarquee via AuthenticatedHelper,
signup en toggle comme /tasks/{id}/signup.
"""
import os
import tempfile
from config import DISCORD_ANIMATEUR_ROLE_ID
from models.ticket import HelperIdentity
from services.discord_service import DiscordService
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from database import db
from models.ticket import AuthenticatedHelper
from services.auth_service import current_staff, current_responsable
from services.storage_service import extension_from_filename, get_object, put_object_from_file

router = APIRouter(prefix="/animateur/projects", tags=["animateur-projects"])
tasks_router = APIRouter(prefix="/animateur/tasks", tags=["animateur-tasks"])
resources_router = APIRouter(prefix="/animateur/resources", tags=["animateur-resources"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _helper_identity(helper: AuthenticatedHelper) -> dict:
    return {
        "id": helper.id,
        "username": helper.username,
        "display_name": helper.global_name,
        "avatar_url": helper.avatar_url,
    }
@router.get("/members/search", response_model=list[HelperIdentity])
async def search_animateur_members(_: AuthenticatedHelper = Depends(current_staff)):
    if not DISCORD_ANIMATEUR_ROLE_ID:
        raise HTTPException(status_code=503, detail="Rôle animateur non configuré.")
    discord = DiscordService()
    return await discord.fetch_helpers(DISCORD_ANIMATEUR_ROLE_ID)

# ---------------------------------------------------------------------------
# Projets
# ---------------------------------------------------------------------------

@router.get("")
async def list_projects(_: AuthenticatedHelper = Depends(current_staff)):
    return await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    return project


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: dict,
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
        "start_date": start_date,
        "end_date": end_date,
        "members": [identity],
        "created_by": identity,
        "created_at": now,
        "updated_at": now,
    }
    await db.projects.insert_one(project)
    project.pop("_id", None)
    return project


@router.put("/{project_id}")
async def update_project(
    project_id: str,
    payload: dict,
    _: AuthenticatedHelper = Depends(current_staff),
):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    updated_at = _now()
    updates = {
        "title": (payload.get("title") or existing["title"]).strip(),
        "description": (payload.get("description") or "").strip(),
        "content_markdown": payload.get("content_markdown", existing.get("content_markdown", "")),
        "end_date": payload.get("end_date", existing.get("end_date")),
        "updated_at": updated_at,
    }
    await db.projects.update_one({"id": project_id}, {"$set": updates})
    existing.update(updates)
    return existing


# ---------------------------------------------------------------------------
# Membres du projet (inscription en toggle, comme /tasks/{id}/signup)
# ---------------------------------------------------------------------------

@router.post("/{project_id}/signup")
async def signup_project(
    project_id: str,
    helper: AuthenticatedHelper = Depends(current_staff),
):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    members = existing.get("members", [])
    updated_at = _now()

    if any(m["id"] == helper.id for m in members):
        members = [m for m in members if m["id"] != helper.id]
    else:
        members.append(_helper_identity(helper))

    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"members": members, "updated_at": updated_at}},
    )
    existing["members"] = members
    existing["updated_at"] = updated_at
    return existing


@router.delete("/{project_id}/members/{member_id}")
async def remove_member(
    project_id: str,
    member_id: str,
    _: AuthenticatedHelper = Depends(current_responsable),
):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    members = [m for m in existing.get("members", []) if m["id"] != member_id]
    updated_at = _now()
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"members": members, "updated_at": updated_at}},
    )
    existing["members"] = members
    existing["updated_at"] = updated_at
    return existing


# ---------------------------------------------------------------------------
# Tâches du projet
# ---------------------------------------------------------------------------

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
    _: AuthenticatedHelper = Depends(current_responsable),
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
        "due_date": payload.get("due_date"),
        "assignee": assignee,
        "status": "a_faire",
        "submission_note": "",
        "created_at": now,
        "updated_at": now,
    }
    await db.project_tasks.insert_one(task)
    task.pop("_id", None)
    return task


@tasks_router.put("/{task_id}/submit")
async def submit_task(
    task_id: str,
    submission_note: str = "",
    _: AuthenticatedHelper = Depends(current_staff),
):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")
    updated_at = _now()
    await db.project_tasks.update_one(
        {"id": task_id},
        {"$set": {"status": "rendu", "submission_note": submission_note, "updated_at": updated_at}},
    )
    existing["status"] = "rendu"
    existing["submission_note"] = submission_note
    existing["updated_at"] = updated_at
    return existing


@tasks_router.put("/{task_id}/validate")
async def validate_task(
    task_id: str,
    _: AuthenticatedHelper = Depends(current_responsable),
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
    return existing


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    _: AuthenticatedHelper = Depends(current_responsable),
):
    result = await db.project_tasks.delete_one({"id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")


# ---------------------------------------------------------------------------
# Ressources du projet
# ---------------------------------------------------------------------------

@router.get("/{project_id}/resources")
async def list_resources(
    project_id: str,
    _: AuthenticatedHelper = Depends(current_staff),
):
    return await db.project_resources.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/{project_id}/resources", status_code=status.HTTP_201_CREATED)
async def upload_resource(
    project_id: str,
    title: str = Form(...),
    file: UploadFile = File(...),
    helper: AuthenticatedHelper = Depends(current_staff),
):
    extension = extension_from_filename(file.filename)
    resource_id = str(uuid4())
    storage_path = f"iris/project-resources/{resource_id}.{extension}"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
            content = await file.read()
            temp_file.write(content)

        put_object_from_file(storage_path, temp_path, file.content_type or "application/octet-stream")
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    now = _now()
    resource = {
        "id": resource_id,
        "project_id": project_id,
        "title": title.strip(),
        "original_filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "storage_path": storage_path,
        "uploaded_by": _helper_identity(helper),
        "created_at": now,
    }
    await db.project_resources.insert_one(resource)
    resource.pop("_id", None)
    return resource


@resources_router.get("/{resource_id}/download")
async def download_resource(resource_id: str):
    resource = await db.project_resources.find_one({"id": resource_id}, {"_id": 0})
    if not resource:
        raise HTTPException(status_code=404, detail="Ressource introuvable.")
    try:
        content, _unused = get_object(resource["storage_path"])
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque.") from error
    return Response(
        content=content,
        media_type=resource.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{resource.get("original_filename", "fichier")}"'},
    )


@resources_router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: str,
    _: AuthenticatedHelper = Depends(current_responsable),
):
    result = await db.project_resources.delete_one({"id": resource_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ressource introuvable.")
