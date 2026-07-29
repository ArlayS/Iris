"""Router pour la gestion des projets animateur (version complete).

MongoDB / Motor. Inclut projets, taches et ressources associees,
alignes sur ProjectDetailPage.jsx et ProjectsListPage.jsx.
"""
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from database import client
from services.storage_service import (
    extension_from_filename,
    get_object,
    put_object_from_file,
    resource_path,
)

router = APIRouter(prefix="/animateur/projects", tags=["animateur-projects"])
tasks_router = APIRouter(prefix="/animateur/tasks", tags=["animateur-tasks"])
resources_router = APIRouter(prefix="/animateur/resources", tags=["animateur-resources"])

db = client.get_default_database()
projects_collection = db["projects"]
tasks_collection = db["project_tasks"]
resources_collection = db["project_resources"]
members_collection = db["members"]


# ---------- Schemas ----------

class ProjectMember(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_url: str | None = None
    role: Literal["responsable", "membre"] = "membre"


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    start_date: date
    end_date: date | None = None

    @field_validator("end_date")
    @classmethod
    def check_end_date(cls, end_date, info):
        start_date = info.data.get("start_date")
        if end_date and start_date and end_date < start_date:
            raise ValueError("end_date doit etre posterieure ou egale a start_date")
        return end_date


class ProjectUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    content_markdown: str = ""
    end_date: date | None = None


class ProjectOut(BaseModel):
    id: str
    title: str
    description: str = ""
    content_markdown: str = ""
    status: Literal["en_cours", "termine", "archive"] = "en_cours"
    start_date: str
    end_date: str | None = None
    members: list[ProjectMember] = Field(default_factory=list)
    created_by: ProjectMember
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    project_id: str
    assignee_id: str
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    due_date: date


class TaskOut(BaseModel):
    id: str
    project_id: str
    title: str
    description: str = ""
    due_date: str
    assignee: ProjectMember
    status: Literal["a_faire", "en_cours", "rendu", "valide"] = "a_faire"
    submission_note: str = ""
    submission_file_url: str | None = None
    submitted_at: str | None = None
    created_at: datetime
    updated_at: datetime


class ResourceOut(BaseModel):
    id: str
    project_id: str
    title: str
    original_filename: str
    content_type: str
    size: int
    uploaded_by: ProjectMember
    created_at: datetime


# ---------- Helpers ----------

def _to_iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value)[:10]


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=404, detail="Ressource introuvable")


async def _get_member(member_id: str) -> ProjectMember:
    document = await members_collection.find_one({"_id": _oid(member_id)}) if ObjectId.is_valid(member_id) else None
    if not document:
        document = await members_collection.find_one({"discord_id": member_id})
    if not document:
        return ProjectMember(id=member_id, username="inconnu", display_name="Membre inconnu", role="membre")
    return ProjectMember(
        id=str(document.get("_id", member_id)),
        username=document.get("username", ""),
        display_name=document.get("display_name", document.get("username", "")),
        avatar_url=document.get("avatar_url"),
        role=document.get("project_role", "membre"),
    )


def _serialize_project(document: dict, created_by: ProjectMember, members: list[ProjectMember]) -> ProjectOut:
    return ProjectOut(
        id=str(document["_id"]),
        title=document.get("title", ""),
        description=document.get("description", ""),
        content_markdown=document.get("content_markdown", ""),
        status=document.get("status", "en_cours"),
        start_date=_to_iso(document.get("start_date")),
        end_date=_to_iso(document.get("end_date")),
        members=members,
        created_by=created_by,
        created_at=document.get("created_at", datetime.utcnow()),
        updated_at=document.get("updated_at", datetime.utcnow()),
    )


async def _load_project_out(document: dict) -> ProjectOut:
    created_by = await _get_member(str(document.get("created_by_id", "")))
    members = [await _get_member(m) for m in document.get("member_ids", [])]
    return _serialize_project(document, created_by, members)


async def _serialize_task(document: dict) -> TaskOut:
    assignee = await _get_member(str(document.get("assignee_id", "")))
    return TaskOut(
        id=str(document["_id"]),
        project_id=str(document.get("project_id", "")),
        title=document.get("title", ""),
        description=document.get("description", ""),
        due_date=_to_iso(document.get("due_date")),
        assignee=assignee,
        status=document.get("status", "a_faire"),
        submission_note=document.get("submission_note", ""),
        submission_file_url=document.get("submission_file_url"),
        submitted_at=_to_iso(document.get("submitted_at")) if document.get("submitted_at") else None,
        created_at=document.get("created_at", datetime.utcnow()),
        updated_at=document.get("updated_at", datetime.utcnow()),
    )


async def _serialize_resource(document: dict) -> ResourceOut:
    uploaded_by = await _get_member(str(document.get("uploaded_by_id", "")))
    return ResourceOut(
        id=str(document["_id"]),
        project_id=str(document.get("project_id", "")),
        title=document.get("title", ""),
        original_filename=document.get("original_filename", ""),
        content_type=document.get("content_type", "application/octet-stream"),
        size=document.get("size", 0),
        uploaded_by=uploaded_by,
        created_at=document.get("created_at", datetime.utcnow()),
    )


async def _get_project_or_404(project_id: str) -> dict:
    document = await projects_collection.find_one({"_id": _oid(project_id)})
    if not document:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return document


# ---------- Projects ----------

@router.get("", response_model=list[ProjectOut])
async def list_projects():
    cursor = projects_collection.find({}).sort("created_at", -1)
    return [await _load_project_out(document) async for document in cursor]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str):
    document = await _get_project_or_404(project_id)
    return await _load_project_out(document)


@router.post("", response_model=ProjectOut)
async def create_project(project: ProjectCreate, created_by_id: str = ""):
    now = datetime.utcnow()
    document = {
        "title": project.title,
        "description": project.description,
        "content_markdown": "",
        "status": "en_cours",
        "start_date": project.start_date.isoformat(),
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "member_ids": [created_by_id] if created_by_id else [],
        "created_by_id": created_by_id,
        "created_at": now,
        "updated_at": now,
    }
    result = await projects_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return await _load_project_out(document)


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, payload: ProjectUpdate):
    object_id = _oid(project_id)
    await projects_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "title": payload.title,
                "description": payload.description,
                "content_markdown": payload.content_markdown,
                "end_date": payload.end_date.isoformat() if payload.end_date else None,
                "updated_at": datetime.utcnow(),
            }
        },
    )
    document = await _get_project_or_404(project_id)
    return await _load_project_out(document)


@router.delete("/{project_id}/members/{member_id}", response_model=ProjectOut)
async def remove_member(project_id: str, member_id: str):
    object_id = _oid(project_id)
    await projects_collection.update_one(
        {"_id": object_id},
        {"$pull": {"member_ids": member_id}, "$set": {"updated_at": datetime.utcnow()}},
    )
    document = await _get_project_or_404(project_id)
    return await _load_project_out(document)


class AddMemberPayload(BaseModel):
    member_id: str


@router.post("/{project_id}/members", response_model=ProjectOut)
async def add_member(project_id: str, payload: AddMemberPayload):
    object_id = _oid(project_id)
    await projects_collection.update_one(
        {"_id": object_id},
        {"$addToSet": {"member_ids": payload.member_id}, "$set": {"updated_at": datetime.utcnow()}},
    )
    document = await _get_project_or_404(project_id)
    return await _load_project_out(document)


# ---------- Tasks ----------

@router.get("/{project_id}/tasks", response_model=list[TaskOut])
async def list_tasks(project_id: str):
    cursor = tasks_collection.find({"project_id": project_id}).sort("due_date", 1)
    return [await _serialize_task(document) async for document in cursor]


@router.post("/{project_id}/tasks", response_model=TaskOut)
async def create_task(project_id: str, payload: TaskCreate):
    now = datetime.utcnow()
    document = {
        "project_id": project_id,
        "assignee_id": payload.assignee_id,
        "title": payload.title,
        "description": payload.description,
        "due_date": payload.due_date.isoformat(),
        "status": "a_faire",
        "submission_note": "",
        "submission_file_url": None,
        "submitted_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await tasks_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return await _serialize_task(document)


@tasks_router.put("/{task_id}/submit", response_model=TaskOut)
async def submit_task(task_id: str, submission_note: str = ""):
    object_id = _oid(task_id)
    await tasks_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "rendu",
                "submission_note": submission_note,
                "submitted_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        },
    )
    document = await tasks_collection.find_one({"_id": object_id})
    if not document:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    return await _serialize_task(document)


@tasks_router.put("/{task_id}/validate", response_model=TaskOut)
async def validate_task(task_id: str):
    object_id = _oid(task_id)
    await tasks_collection.update_one(
        {"_id": object_id},
        {"$set": {"status": "valide", "updated_at": datetime.utcnow()}},
    )
    document = await tasks_collection.find_one({"_id": object_id})
    if not document:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    return await _serialize_task(document)


@tasks_router.delete("/{task_id}")
async def delete_task(task_id: str):
    object_id = _oid(task_id)
    result = await tasks_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    return {"ok": True}


# ---------- Resources ----------

@router.get("/{project_id}/resources", response_model=list[ResourceOut])
async def list_resources(project_id: str):
    cursor = resources_collection.find({"project_id": project_id}).sort("created_at", -1)
    return [await _serialize_resource(document) async for document in cursor]


@router.post("/{project_id}/resources", response_model=ResourceOut)
async def upload_resource(
    project_id: str,
    title: str = Form(...),
    file: UploadFile = File(...),
    uploaded_by_id: str = Form(""),
):
    now = datetime.utcnow()
    resource_id = ObjectId()
    extension = extension_from_filename(file.filename) or "bin"
    storage_key = resource_path(str(resource_id), extension)

    tmp_path = Path(tempfile.gettempdir()) / f"upload-{resource_id}"
    content = await file.read()
    tmp_path.write_bytes(content)
    try:
        stored = put_object_from_file(storage_key, str(tmp_path), file.content_type or "application/octet-stream")
    finally:
        tmp_path.unlink(missing_ok=True)

    document = {
        "_id": resource_id,
        "project_id": project_id,
        "title": title,
        "original_filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": stored["size"],
        "storage_path": stored["path"],
        "uploaded_by_id": uploaded_by_id,
        "created_at": now,
    }
    await resources_collection.insert_one(document)
    return await _serialize_resource(document)


@resources_router.get("/{resource_id}/download")
async def download_resource(resource_id: str):
    object_id = _oid(resource_id)
    document = await resources_collection.find_one({"_id": object_id})
    if not document:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    try:
        content, _ = get_object(document["storage_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque")
    return Response(
        content=content,
        media_type=document.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{document.get("original_filename", "fichier")}"'},
    )


@resources_router.delete("/{resource_id}")
async def delete_resource(resource_id: str):
    object_id = _oid(resource_id)
    result = await resources_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    return {"ok": True}
