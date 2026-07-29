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
    return {"projects": projects, "tasks": tasks}
