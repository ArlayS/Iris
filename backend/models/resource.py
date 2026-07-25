from pydantic import BaseModel, Field

from models.ticket import HelperIdentity


class ResourceDocument(BaseModel):
    id: str
    title: str
    description: str = ""
    category: str
    original_filename: str
    content_type: str
    size: int
    created_at: str
    created_by: HelperIdentity


class ResourceListResponse(BaseModel):
    resources: list[ResourceDocument] = Field(default_factory=list)