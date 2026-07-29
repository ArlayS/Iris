# routers/projects.py
import asyncio, os, tempfile
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from database import db
from models.project import (
    Project, ProjectCreate, ProjectUpdate, ProjectTask, ProjectTaskCreate,
    ProjectResource, ProjectMember,
)
from models.ticket import AuthenticatedHelper
from services.authservice import current_animateur, current_responsable_projet
from services.storageservice import extension_from_filename, putobject_from_file

router = APIRouter(prefix="/animateur", tags=["animateur"])

def to_member(helper: AuthenticatedHelper, role="membre") -> ProjectMember:
    return ProjectMember(
        id=helper.id, username=helper.username,
        display_name=helper.globalname, avatar_url=helper.avatarurl, role=role,
    )

@router.get("/projects", response_model=list[Project])
async def list_projects(helper: AuthenticatedHelper = Depends(current_animateur)):
    return await db.projects.find({}, {"_id": 0}).sort("start_date", -1).to_list(500)

@router.post("/projects", response_model=Project, status_code=201)
async def create_project(payload: ProjectCreate, helper: AuthenticatedHelper = Depends(current_animateur)):
    now = datetime.now(timezone.utc).isoformat()
    creator = to_member(helper, role="responsable")
    project = Project(
        id=str(uuid4()), title=payload.title.strip(), description=payload.description.strip(),
        start_date=payload.start_date, end_date=payload.end_date,
        members=[creator], created_by=creator, created_at=now, updated_at=now,
    )
    await db.projects.insert_one(project.model_dump(mode="json"))
    return project

@router.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str, helper: AuthenticatedHelper = Depends(current_animateur)):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(404, "Projet introuvable.")
    return project

@router.put("/projects/{project_id}", response_model=Project)
async def update_project(project_id: str, payload: ProjectUpdate, helper: AuthenticatedHelper = Depends(current_animateur)):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Projet introuvable.")
    updated_at = datetime.now(timezone.utc).isoformat()
    update_fields = {
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "content_markdown": payload.content_markdown,
        "end_date": payload.end_date,
        "updated_at": updated_at,
    }
    if payload.status is not None:
        update_fields["status"] = payload.status

    await db.projects.update_one({"id": project_id}, {"$set": update_fields})
    existing.update(update_fields)
    return existing

@router.post("/projects/{project_id}/members/{helper_id}", response_model=Project)
async def add_member(project_id: str, helper_id: str, username: str, display_name: str,
                      avatar_url: str | None = None, helper: AuthenticatedHelper = Depends(current_responsable_projet)):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Projet introuvable.")
    if any(m["id"] == helper_id for m in existing["members"]):
        raise HTTPException(409, "Déjà inscrit au projet.")
    member = ProjectMember(id=helper_id, username=username, display_name=display_name, avatar_url=avatar_url)
    existing["members"].append(member.model_dump())
    await db.projects.update_one({"id": project_id}, {"$set": {"members": existing["members"]}})
    return existing

@router.delete("/projects/{project_id}/members/{helper_id}", response_model=Project)
async def remove_member(project_id: str, helper_id: str, helper: AuthenticatedHelper = Depends(current_responsable_projet)):
    existing = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Projet introuvable.")
    existing["members"] = [m for m in existing["members"] if m["id"] != helper_id]
    await db.projects.update_one({"id": project_id}, {"$set": {"members": existing["members"]}})
    return existing
    
# routers/animateur.py
@router.get("/calendar-events")
async def project_calendar_events(helper: AuthenticatedHelper = Depends(current_staff)):
    projects = await db.projects.find(
        {}, {"_id": 0, "id": 1, "title": 1, "start_date": 1, "end_date": 1, "status": 1}
    ).to_list(500)
    tasks = await db.project_tasks.find(
        {}, {"_id": 0, "id": 1, "title": 1, "due_date": 1, "project_id": 1, "status": 1, "assignee": 1}
    ).to_list(500)
    return {"projects": projects, "tasks": tasks}
@router.get("/projects/{project_id}/tasks", response_model=list[ProjectTask])
async def list_tasks(project_id: str, helper: AuthenticatedHelper = Depends(current_animateur)):
    return await db.project_tasks.find({"project_id": project_id}, {"_id": 0}).sort("due_date", 1).to_list(500)

@router.post("/projects/{project_id}/tasks", response_model=ProjectTask, status_code=201)
async def create_task(project_id: str, payload: ProjectTaskCreate, helper: AuthenticatedHelper = Depends(current_responsable_projet)):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    assignee_data = next((m for m in project["members"] if m["id"] == payload.assignee_id), None)
    if not assignee_data:
        raise HTTPException(422, "Ce membre n'est pas inscrit au projet.")
    now = datetime.now(timezone.utc).isoformat()
    task = ProjectTask(
        id=str(uuid4()), project_id=project_id, title=payload.title.strip(),
        description=payload.description.strip(), due_date=payload.due_date,
        assignee=ProjectMember(**assignee_data), created_at=now, updated_at=now,
    )
    await db.project_tasks.insert_one(task.model_dump(mode="json"))
    return task

@router.put("/tasks/{task_id}/submit", response_model=ProjectTask)
async def submit_task(task_id: str, submission_note: str = "", helper: AuthenticatedHelper = Depends(current_animateur)):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Tâche introuvable.")
    if existing["assignee"]["id"] != helper.id:
        raise HTTPException(403, "Seul l'assigné peut rendre cette tâche.")
    updated_at = datetime.now(timezone.utc).isoformat()
    await db.project_tasks.update_one({"id": task_id}, {"$set": {
        "status": "rendu", "submission_note": submission_note.strip(),
        "submitted_at": updated_at, "updated_at": updated_at,
    }})
    existing.update(status="rendu", submission_note=submission_note.strip(), submitted_at=updated_at, updated_at=updated_at)
    return existing

@router.put("/tasks/{task_id}/validate", response_model=ProjectTask)
async def validate_task(task_id: str, helper: AuthenticatedHelper = Depends(current_responsable_projet)):
    existing = await db.project_tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Tâche introuvable.")
    updated_at = datetime.now(timezone.utc).isoformat()
    await db.project_tasks.update_one({"id": task_id}, {"$set": {"status": "valide", "updated_at": updated_at}})
    existing.update(status="valide", updated_at=updated_at)
    return existing
    
async def current_project_responsable(project_id: str, helper: AuthenticatedHelper = Depends(current_animateur)) -> AuthenticatedHelper:
    project = await db.projects.find_one({"id": project_id}, {"_id": 0, "created_by": 1})
    if not project:
        raise HTTPException(404, "Projet introuvable.")
    is_creator = project["created_by"]["id"] == helper.id
    is_global_responsable = await is_responsable_helper(helper.id)
    if not (is_creator or is_global_responsable):
        raise HTTPException(403, "Seul le responsable du projet peut effectuer cette action.")
    return helper
    
@router.post("/projects/{project_id}/resources", response_model=ProjectResource, status_code=201)
async def upload_project_resource(project_id: str, title: str, file: UploadFile = File(...),
                                    helper: AuthenticatedHelper = Depends(current_animateur)):
    extension = extension_from_filename(file.filename)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name
            while chunk := await file.read(1024 * 1024):
                tmp.write(chunk)
        resource_id = str(uuid4())
        storage_path = f"iris/project-resources/{resource_id}.{extension}"
        result = await asyncio.to_thread(putobject_from_file, storage_path, temp_path, file.content_type)
        resource = ProjectResource(
            id=resource_id, project_id=project_id, title=title.strip(),
            original_filename=file.filename, content_type=file.content_type,
            size=result.get("size", 0), storage_path=storage_path,
            uploaded_by=to_member(helper), created_at=datetime.now(timezone.utc).isoformat(),
        )
        await db.project_resources.insert_one(resource.model_dump())
        return resource
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

@router.get("/projects/{project_id}/resources", response_model=list[ProjectResource])
async def list_project_resources(project_id: str, helper: AuthenticatedHelper = Depends(current_animateur)):
    return await db.project_resources.find({"project_id": project_id}, {"_id": 0, "storage_path": 0}).to_list(200)
