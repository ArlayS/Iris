from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuthLog(BaseModel):
    id: str
    created_at: datetime
    event_type: str
    helper_id: str | None = None
    username: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    path: str | None = None
    method: str | None = None
    status_code: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
