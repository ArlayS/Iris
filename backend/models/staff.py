from typing import Literal

from pydantic import BaseModel, Field

from models.ticket import HelperIdentity


class AbsenceEntry(BaseModel):
    id: str
    helper: HelperIdentity
    start_date: str
    end_date: str
    reason: str = ""
    created_at: str


class AbsenceCreate(BaseModel):
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reason: str = Field(default="", max_length=500)


MeetingStatus = Literal["en_attente_resume", "redige"]


class MeetingSummary(BaseModel):
    id: str
    title: str
    agenda: str = ""
    content_markdown: str = ""
    status: MeetingStatus = "en_attente_resume"
    meeting_date: str
    author: HelperIdentity
    created_at: str
    updated_at: str


class MeetingSummaryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    agenda: str = Field(default="", max_length=4000)
    content_markdown: str = Field(default="", max_length=50000)
    meeting_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class MeetingSummaryUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    agenda: str = Field(default="", max_length=4000)
    content_markdown: str = Field(default="", max_length=50000)
