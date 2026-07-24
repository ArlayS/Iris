from fastapi import APIRouter, Depends

from models.ticket import AuthenticatedHelper, DiscordMember
from services.auth_service import current_helper
from services.discord_service import DiscordService


router = APIRouter(prefix="/members", tags=["members"])


@router.get("/{member_id}", response_model=DiscordMember)
async def get_member(
    member_id: str,
    _: AuthenticatedHelper = Depends(current_helper),
) -> DiscordMember:
    return await DiscordService().fetch_member(member_id)