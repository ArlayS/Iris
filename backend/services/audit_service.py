from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request

from database import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


async def log_auth_event(
    event_type: str,
    request: Request,
    helper=None,
    status_code: int | None = None,
    details: dict | None = None,
) -> None:
    await db.auth_logs.insert_one(
        {
            "id": str(uuid4()),
            "created_at": _now(),
            "event_type": event_type,
            "helper_id": getattr(helper, "id", None),
            "username": getattr(helper, "username", None),
            "ip": _client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "path": request.url.path,
            "method": request.method,
            "status_code": status_code,
            "details": details or {},
        }
    )
