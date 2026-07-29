"""Modeles Pydantic pour la gestion des projets."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProjectMemberAdd(BaseModel):
    member_id: str = Field(pattern=r"\d{15,22}")
    role: Literal["membre", "responsable"] = "membre"


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
    status: str | None = None


class Project(BaseModel):
    id: str
    title: str
    description: str
    content_markdown: str = ""
    status: Literal["en_cours", "termine", "archive"] = "en_cours"
    start_date: date
    end_date: date | None = None
    members: list[ProjectMember] = Field(default_factory=list)
    created_by: ProjectMember
    created_at: datetime
    updated_at: datetime


class ProjectTaskCreate(BaseModel):
    project_id: str
    assignee_id: str
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    due_date: date


class ProjectTask(BaseModel):
    id: str
    project_id: str
    title: str
    description: str = ""
    due_date: date
    assignee: ProjectMember
    status: Literal["a_faire", "en_cours", "rendu", "valide"] = "a_faire"
    submission_note: str = ""
    submission_file_url: str | None = None
    sub
