# routers/projects.py
import asyncio
import os
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from database import db
from models.project import (
    Project,
    ProjectCreate,
    ProjectMember,
    ProjectResource,
    ProjectTask,
    ProjectTaskCreate,
    ProjectUpdate,
)
from models.ticket import AuthenticatedHelper
from services.audit_service import log_auth_event
from services.auth_service import (
    current_animateur,
    current_helper,
    current_responsable_projet,
    is_animateur_helper,
    is_responsable_helper,
)
from services.storage_service import extension_from_filename, put_object_from_file

router = APIRouter(prefix="/animateur", tags=["animateur"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_member(helper: AuthenticatedHelper, role: str = "membre") -> ProjectMember:
    return ProjectMember(
        id=helper.id,
        username=helper.username,
        display_name=getattr(helper, "global_name", None) or getattr(helper, "globalname", helper.username),
        avatar_url=getattr(helper, "avatar_url", None) or getattr(helper, "avatarurl", None),
        role=role,
    )


async def current_project_editor(request: Request) -> AuthenticatedHelper:
    helper = await current_helper(request)
    if await is_animateur_helper(helper.id):
        return helper
    if await is_responsable_helper(helper.id):
        return helper
    raise HTTPException(status_code=403, detail="Rôle Animateur ou Responsable requis.")


@router.get("/projects", response_model=list[Project])
async def list_projects(helper: AuthenticatedHelper = Depends(current_animateur)):
    items = await db.projects.find({}, {"_id": 0}).sort("start_date", -1).to_list(500)
    return [Project(**item) for item in items]


@router.post("/projects", response_model=Project, status_code=201)
async def create_project(
    payload: ProjectCreate,
    helper: AuthenticatedHelper = Depends(current_animateur),
):
    now = _now()
    creator = to_member(helper, role="responsable")

    project = Project(
        id=str(uuid4()),
        title=(payload.title or "").strip(),
        description=(payload.description or "").strip(),
        content_markdown="",
        status="en_cours",
        start_date=payload.start_date,
        end_date=payload.end_date,
        members=[creator],
        created_by=creator,
        created_at=now,
        updated_at=now,
    )

    await db.projects.insert_one(project.model_dump(mode="json"))
    return project


@router.get("/projects/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    helper: AuthenticatedHelper = Depends(current_animateur),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    return Project(**project)


@router.put("/projects/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    helper: AuthenticatedHelper = Depends(current_project_editor),
) -> Project:
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    previous_title = existing.get("title", "")
    previous_description = existing.get("description", "")
    previous_content = existing.get("content_markdown", "")
    previous_end_date = existing.get("end_date")
    previous_status = existing.get("status")

    updated_at = _now()

    clean_title = (payload.title or "").strip()
    clean_description = (payload.description or "").strip()
    clean_content = payload.content_markdown or ""

    result = await db.projects.update_one(
        {"id": project_id},
        {
            "$set": {
                "title": clean_title,
                "description": clean_description,
                "content_markdown": clean_content,
                "end_date": payload.end_date,
                "status": payload.status or existing.get("status", "en_cours"),
                "updated_at": updated_at,
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    updated = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="Projet introuvable après mise à jour.")

    title_changed = previous_title != clean_title
    description_changed = previous_description != clean_description
    content_changed = previous_content != clean_content
    end_date_changed = previous_end_date != payload.end_date
    status_changed = previous_status != (payload.status or existing.get("status", "en_cours"))

    if title_changed or description_changed or content_changed or end_date_changed or status_changed:
        await log_auth_event(
            "project.content.updated",
            request,
            helper=helper,
            status_code=200,
            details={
                "project_id": project_id,
                "title": clean_title,
                "title_changed": title_changed,
                "description_changed": description_changed,
                "content_changed": content_changed,
                "end_date_changed": end_date_changed,
                "status_changed": status_changed,
                "before_length": len(previous_content or ""),
                "after_length": len(clean_content or ""),
            },
        )

    return Project(**updated)


@router.post("/projects/{project_id}/members/{helper_id}", response_model=Project)
async def add_member(
    project_id: str,
    helper_id: str,
    username: str,
    display_name: str,
    avatar_url: str | None = None,
    helper: AuthenticatedHelper = Depends(current_responsable_projet),
):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    if any(member["id"] == helper_id for member in existing.get("members", [])):
        raise HTTPException(status_code=409, detail="Déjà inscrit au projet.")

    member = ProjectMember(
        id=helper_id,
        username=username,
        display_name=display_name,
        avatar_url=avatar_url,
        role="membre",
    )

    existing["members"].append(member.model_dump(mode="json"))
    existing["updated_at"] = _now()

    await db.projects.update_one(
        {"id": project_id},
        {
            "$set": {
                "members": existing["members"],
                "updated_at": existing["updated_at"],
            }
        },
    )

    return Project(**existing)


@router.delete("/projects/{project_id}/members/{helper_id}", response_model=Project)
async def remove_member(
    project_id: str,
    helper_id: str,
    helper: AuthenticatedHelper = Depends(current_responsable_projet),
):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    existing["members"] = [
        member for member in existing.get("members", []) if member["id"] != helper_id
    ]
    existing["updated_at"] = _now()

    await db.projects.update_one(
        {"id": project_id},
        {
            "$set": {
                "members": existing["members"],
                "updated_at": existing["updated_at"],
            }
        },
    )

    return Project(**existing)


@router.get("/projects/{project_id}/tasks", response_model=list[ProjectTask])
async def list_tasks(
    project_id: str,
    helper: AuthenticatedHelper = Depends(current_animateur),
):
    items = await db.project_tasks.find({"project_id": project_id}, {"_id": 0}).sort("due_date", 1).to_list(500)
    return [ProjectTask(**item) for item in items]


@router.post("/projects/{project_id}/tasks", response_model=ProjectTask, status_code=201)
async def create_task(
    project_id: str,
    payload: ProjectTaskCreate,
    helper: AuthenticatedHelper = Depends(current_responsable_projet),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    assignee_data = next(
        (member for member in project.get("members", []) if member["id"] == payload.assignee_id),
        None,
    )
    if not assignee_data:
        raise HTTPException(status_code=422, detail="Ce membre n'est pas inscrit au projet.")

    now = _now()
    task = ProjectTask(
        id=str(uuid4()),
        project_id=project_id,
        title=(payload.title or "").strip(),
        description=(payload.description or "").strip(),
        due_date=payload.due_date,
        assignee=ProjectMember(**assignee_data),
        created_at=now,
        updated_at=now,
    )

    await db.project_tasks.insert_one(task.model_dump(mode="json"))
    return task


@router.put("/tasks/{task_id}/submit", response_model=ProjectTask)
async def submit_task(
    task_id: str,
    submission_note: str = "",
    helper: AuthenticatedHelper = Depends(current_animateur),
):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")

    if existing["assignee"]["id"] != helper.id:
        raise HTTPException(status_code=403, detail="Seul l'assigné peut rendre cette tâche.")

    updated_at = _now()
    note = (submission_note or "").strip()

    await db.project_tasks.update_one(
        {"id": task_id},
        {
            "$set": {
                "status": "rendu",
                "submission_note": note,
                "submitted_at": updated_at,
                "updated_at": updated_at,
            }
        },
    )

    existing.update(
        status="rendu",
        submission_note=note,
        submitted_at=updated_at,
        updated_at=updated_at,
    )
    return ProjectTask(**existing)


@router.put("/tasks/{task_id}/validate", response_model=ProjectTask)
async def validate_task(
    task_id: str,
    helper: AuthenticatedHelper = Depends(current_responsable_projet),
):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Tâche introuvable.")

    updated_at = _now()

    await db.project_tasks.update_one(
        {"id": task_id},
        {"$set": {"status": "valide", "updated_at": updated_at}},
    )

    existing.update(status="valide", updated_at=updated_at)
    return ProjectTask(**existing)


@router.post("/projects/{project_id}/resources", response_model=ProjectResource, status_code=201)
async def upload_project_resource(
    project_id: str,
    title: str,
    file: UploadFile = File(...),
    helper: AuthenticatedHelper = Depends(current_animateur),
):
    extension = extension_from_filename(file.filename)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name
            while chunk := await file.read(1024 * 1024):
                tmp.write(chunk)

        resource_id = str(uuid4())
        storage_path = f"iris/project-resources/{resource_id}.{extension}"
        result = await asyncio.to_thread(
            put_object_from_file,
            storage_path,
            temp_path,
            file.content_type,
        )

        resource = ProjectResource(
            id=resource_id,
            project_id=project_id,
            title=(title or "").strip(),
            original_filename=file.filename,
            content_type=file.content_type,
            size=result.get("size", 0) if isinstance(result, dict) else 0,
            storage_path=storage_path,
            uploaded_by=to_member(helper),
            created_at=_now(),
        )

        await db.project_resources.insert_one(resource.model_dump(mode="json"))
        return resource
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.get("/projects/{project_id}/resources", response_model=list[ProjectResource])
async def list_project_resources(
    project_id: str,
    helper: AuthenticatedHelper = Depends(current_animateur),
):
    items = await db.project_resources.find(
        {"project_id": project_id},
        {"_id": 0, "storage_path": 0},
    ).to_list(200)
    return [ProjectResource(**item) for item in items]
