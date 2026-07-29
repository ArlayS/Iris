"""Router pour les evenements du calendrier animateur."""
from fastapi import APIRouter, Depends

from database import db
from models.ticket import AuthenticatedHelper
from services.auth_service import current_staff

router = APIRouter(prefix="/animateur/calendar-events", tags=["animateur-calendar"])


@router.get("")
async def list_calendar_events(_: AuthenticatedHelper = Depends(current_staff)):
    projects = await db.projects.find({}, {"_id": 0}).to_list(500)
    tasks = await db.project_tasks.find({}, {"_id": 0}).to_list(1000)
    return {"projects": projects, "tasks": tasks}    tasks_out: list[CalendarTask] = []
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
