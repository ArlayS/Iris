"""Router pour les evenements du calendrier animateur."""
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from database import client

router = APIRouter(prefix="/animateur/calendar-events", tags=["animateur-calendar"])

db = client.get_default_database()
projects_collection = db["projects"]
tasks_collection = db["project_tasks"]


class CalendarProject(BaseModel):
    id: str
    title: str
    start_date: str
    end_date: str | None = None


class CalendarTaskAssignee(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_url: str | None = None


class CalendarTask(BaseModel):
    id: str
    project_id: str
    title: str
    due_date: str
    status: str = "a_faire"
    assignee: CalendarTaskAssignee


class CalendarEventsResponse(BaseModel):
    projects: list[CalendarProject] = Field(default_factory=list)
    tasks: list[CalendarTask] = Field(default_factory=list)


def _to_iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value)[:10]


@router.get("", response_model=CalendarEventsResponse)
async def list_calendar_events():
    projects_out: list[CalendarProject] = []
    projects_cursor = projects_collection.find({})
    async for project in projects_cursor:
        projects_out.append(
            CalendarProject(
                id=str(project["_id"]),
                title=project.get("title", ""),
                start_date=_to_iso(project.get("start_date")),
                end_date=_to_iso(project.get("end_date")),
            )
        )

    tasks_out: list[CalendarTask] = []
    tasks_cursor = tasks_collection.find({})
    async for task in tasks_cursor:
        assignee = task.get("assignee") or {}
        tasks_out.append(
            CalendarTask(
                id=str(task["_id"]),
                project_id=str(task.get("project_id", "")),
                title=task.get("title", ""),
                due_date=_to_iso(task.get("due_date")),
                status=task.get("status", "a_faire"),
                assignee=CalendarTaskAssignee(
                    id=str(assignee.get("id", "")),
                    username=assignee.get("username", ""),
                    display_name=assignee.get("display_name", ""),
                    avatar_url=assignee.get("avatar_url"),
                ),
            )
        )

    return CalendarEventsResponse(projects=projects_out, tasks=tasks_out)
