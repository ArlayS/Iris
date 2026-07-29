"""Router pour la gestion des projets animateur."""
from datetime import date, datetime
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from database import client

router = APIRouter(prefix="/animateur/projects", tags=["animateur-projects"])

db = client.get_default_database()
projects_collection = db["projects"]


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


class ProjectOut(BaseModel):
    id: str
    title: str
    description: str = ""
    content_markdown: str = ""
    status: Literal["en_cours", "termine", "archive"] = "en_cours"
    start_date: date
    end_date: date | None = None
    members: list[ProjectMember] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


def _to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _serialize(document: dict) -> ProjectOut:
    return ProjectOut(
        id=str(document["_id"]),
        title=document.get("title", ""),
        description=document.get("description", ""),
        content_markdown=document.get("content_markdown", ""),
        status=document.get("status", "en_cours"),
        start_date=_to_date(document.get("start_date")),
        end_date=_to_date(document.get("end_date")),
        members=[ProjectMember(**member) for member in document.get("members", [])],
        created_at=document.get("created_at", datetime.utcnow()),
        updated_at=document.get("updated_at", datetime.utcnow()),
    )


@router.get("", response_model=list[ProjectOut])
async def list_projects():
    cursor = projects_collection.find({}).sort("created_at", -1)
    return [_serialize(document) async for document in cursor]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str):
    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    document = await projects_collection.find_one({"_id": object_id})
    if not document:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return _serialize(document)


@router.post("", response_model=ProjectOut)
async def create_project(project: ProjectCreate):
    now = datetime.utcnow()
    document = {
        "title": project.title,
        "description": project.description,
        "content_markdown": "",
        "status": "en_cours",
        "start_date": project.start_date.isoformat(),
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "members": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await projects_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return _serialize(document)
