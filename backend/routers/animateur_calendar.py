"""Router pour les evenements du calendrier animateur."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(prefix="/animateur/calendar-events", tags=["animateur-calendar"])


class CalendarEvent(BaseModel):
    id: str
    title: str
    date: date
    type: Literal["project_start", "project_end", "task_due"]
    project_id: str
    project_title: str

    class Config:
        orm_mode = True


@router.get("", response_model=list[CalendarEvent])
def list_calendar_events(db: Session = Depends(get_db)):
    events: list[CalendarEvent] = []

    projects = db.query(models.Project).all()
    project_titles = {project.id: project.title for project in projects}

    for project in projects:
        events.append(
            CalendarEvent(
                id=f"project-start-{project.id}",
                title=f"Debut : {project.title}",
                date=project.start_date,
                type="project_start",
                project_id=str(project.id),
                project_title=project.title,
            )
        )
        if project.end_date:
            events.append(
                CalendarEvent(
                    id=f"project-end-{project.id}",
                    title=f"Fin : {project.title}",
                    date=project.end_date,
                    type="project_end",
                    project_id=str(project.id),
                    project_title=project.title,
                )
            )

    tasks = db.query(models.ProjectTask).all()
    for task in tasks:
        events.append(
            CalendarEvent(
                id=f"task-due-{task.id}",
                title=f"Echeance : {task.title}",
                date=task.due_date,
                type="task_due",
                project_id=str(task.project_id),
                project_title=project_titles.get(task.project_id, ""),
            )
        )

    return sorted(events, key=lambda event: event.date)
