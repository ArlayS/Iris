from fastapi import APIRouter, Depends, Query

from database import db
from models.audit import AuthLogListResponse
from models.ticket import AuthenticatedHelper
from services.auth_service import current_responsable

router = APIRouter(prefix="/responsable", tags=["responsable"])


@router.get("/auth-logs", response_model=AuthLogListResponse)
async def list_auth_logs(
    _: AuthenticatedHelper = Depends(current_responsable),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    event_type: str | None = Query(None),
    helper_id: str | None = Query(None),
):
    filters = {}
    if event_type:
        filters["event_type"] = event_type
    if helper_id:
        filters["helper_id"] = helper_id

    total = await db.auth_logs.count_documents(filters)
    items = (
        await db.auth_logs
        .find(filters, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    return {"total": total, "items": items}
