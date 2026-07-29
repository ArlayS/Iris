"""Router pour les evenements du calendrier animateur."""
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from database import client

router = APIRouter(prefix="/animateur/calendar-events", tags=["animateur-calendar"])

db = client.get_default_database()
projects_collection = db["projects"]
tasks_collection = db["project_tasks"]


class CalendarEvent(BaseModel):
    id: str
    title: str
    date: date
    type: Literal["project_start", "project_end", "task_due"]
    project_id: str
    project_title: str


def _to_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


@router.get("", response_model=list[CalendarEvent])
async def list_calendar_events():
    events: list[CalendarEvent] = []

    projects_cursor = projects_collection.find({})
    projects = [project async for project in projects_cursor]
    project_titles = {str(project["_id"]): project.get("title", "") for project in projects}

    for project in projects:
        project_id = str(project["_id"])
        title = project.get("title", "")

        start_date = project.get("start_date")
        if start_date:
            events.append(
                CalendarEvent(
                    id=f"project-start-{project_id}",
                    title=f"Debut : {title}",
                    date=_to_date(start_date),
                    type="project_start",
                    project_id=project_id,
                    project_title=title,
                )
            )

        end_date = project.get("end_date")
        if end_date:
            events.append(
                CalendarEvent(
                    id=f"project-end-{project_id}",
                    title=f"Fin : {title}",
                    date=_to_date(end_date),
                    type="project_end",
                    project_id=project_id,
                    project_title=title,
                )
            )

    tasks_cursor = tasks_collection.find({})
    async for task in tasks_cursor:
        due_date = task.get("due_date")
        if not due_date:
            continue
        project_id = str(task.get("project_id", ""))
        events.append(
            CalendarEvent(
                id=f"task-due-{task['_id']}",
                title=f"Echeance : {task.get('title', '')}",
                date=_to_date(due_date),
                type="task_due",
                project_id=project_id,
                project_title=project_titles.get(project_id, ""),
            )
        )

    return sorted(events, key=lambda event: event.date)
