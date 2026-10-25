from fastapi import APIRouter, Depends, Path

from models.ticket import AuthenticatedHelper, DiscordMember
from services.auth_service import current_ticket_helper
from services.discord_service import DiscordService


router = APIRouter(prefix="/members", tags=["members"])


@router.get("/{member_id}", response_model=DiscordMember)
async def get_member(
    member_id: str = Path(pattern=r"^[0-9]{15,22}$"),
    _: AuthenticatedHelper = Depends(current_ticket_helper),
) -> DiscordMember:
    return await DiscordService().fetch_member(member_id)
