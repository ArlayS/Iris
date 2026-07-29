# models/project.py
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field
from typing import Literal
from pydantic import BaseModel, Field

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
    title: str
    description: str = ""
    start_date: date
    end_date: date | None = None

class ProjectUpdate(BaseModel):
    title: str
    description: str
    content_markdown: str  # contenu de l'éditeur Tiptap du projet
    end_date: date | None = None

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
    created_at: str
    updated_at: str

class ProjectTaskCreate(BaseModel):
    project_id: str
    assignee_id: str
    title: str
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
    submitted_at: str | None = None
    created_at: str
    updated_at: str

class ProjectResource(BaseModel):
    id: str
    project_id: str
    title: str
    original_filename: str
    content_type: str
    size: int
    storage_path: str
    uploaded_by: ProjectMember
    created_at: str
