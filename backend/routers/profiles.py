from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from database import db
from models.ticket import AuthenticatedHelper, HelperProfile, HelperProfileUpdate
from services.auth_service import current_helper


router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=HelperProfile)
async def get_my_profile(
    helper: AuthenticatedHelper = Depends(current_helper),
) -> HelperProfile:
    profile = await db.helper_profiles.find_one({"helper_id": helper.id}, {"_id": 0})
    if not profile:
        return HelperProfile(helper_id=helper.id)
    return profile


@router.put("/me", response_model=HelperProfile)
async def update_my_profile(
    input_data: HelperProfileUpdate,
    helper: AuthenticatedHelper = Depends(current_helper),
) -> HelperProfile:
    profile = HelperProfile(
        helper_id=helper.id,
        triggers=input_data.triggers.strip(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    await db.helper_profiles.update_one(
        {"helper_id": helper.id},
        {"$set": profile.model_dump()},
        upsert=True,
    )
    return profile