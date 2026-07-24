from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DiscordAuthor(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class DiscordAttachment(BaseModel):
    id: str
    filename: str
    url: str
    content_type: str | None = None


class TranscriptMessage(BaseModel):
    id: str
    content: str
    timestamp: str
    author: DiscordAuthor
    attachments: list[DiscordAttachment] = Field(default_factory=list)


class DiscordMember(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    joined_at: str | None = None


class TicketCreate(BaseModel):
    member_id: str = Field(pattern=r"^\d{15,22}$")
    channel_id: str = Field(pattern=r"^\d{15,22}$")
    title: str | None = Field(default=None, max_length=120)


class TicketUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=25000)
    vocal_summary: str | None = Field(default=None, max_length=25000)
    status: Literal["active", "archived"] | None = None


class TicketSummary(BaseModel):
    id: str
    title: str
    member: DiscordMember
    channel_id: str
    channel_name: str
    status: Literal["active", "archived"]
    message_count: int
    updated_at: str
    created_at: str


class TicketDetail(TicketSummary):
    transcript: list[TranscriptMessage] = Field(default_factory=list)
    notes: str = ""
    vocal_summary: str = ""
    last_synced_at: str | None = None
    created_by: str


class TicketStats(BaseModel):
    active_count: int
    archived_count: int
    total_messages: int


class AuthenticatedHelper(BaseModel):
    id: str
    username: str
    global_name: str | None = None
    avatar_url: str | None = None


class AuthSession(BaseModel):
    authenticated: bool
    helper: AuthenticatedHelper | None = None