from config import DISCORD_HELPER_ROLE_ID, DISCORD_HELPER_ROLE2_ID
from services.discord_service import DiscordService

@router.get("/members/search")
async def search_available_members(
    _: AuthenticatedHelper = Depends(current_animateur),
) -> list[dict]:
    discord = DiscordService()
    helpers = await discord.fetch_helpers(DISCORD_HELPER_ROLE_ID)
    if DISCORD_HELPER_ROLE2_ID:
        extra = await discord.fetch_helpers(DISCORD_HELPER_ROLE2_ID)
        seen_ids = {h.id for h in helpers}
        helpers.extend(h for h in extra if h.id not in seen_ids)
    return [h.model_dump() for h in helpers]


@router.post("/projects/{project_id}/members", response_model=ProjectDocument)
async def add_project_member(
    project_id: str,
    payload: ProjectMemberAdd,
    helper: AuthenticatedHelper = Depends(current_animateur),
) -> ProjectDocument:
    project = await project_or_404(project_id)
    is_creator = project["created_by"]["id"] == helper.id
    if not is_creator and not await is_responsable_helper(helper.id):
        raise HTTPException(403, "Seul le responsable du projet peut ajouter des membres.")

    if any(member["id"] == payload.member_id for member in project["members"]):
        raise HTTPException(409, "Ce membre fait déjà partie du projet.")

    discord = DiscordService()
    discord_member = await discord.fetch_member(payload.member_id)
    new_member = {
        "id": discord_member.id,
        "username": discord_member.username,
        "display_name": discord_member.display_name,
        "avatar_url": discord_member.avatar_url,
        "role": payload.role,
    }
    project["members"].append(new_member)
    await db.projects.update_one({"id": project_id}, {"$set": {"members": project["members"]}})
    return project


@router.delete("/projects/{project_id}/members/{member_id}", response_model=ProjectDocument)
async def remove_project_member(
    project_id: str,
    member_id: str,
    helper: AuthenticatedHelper = Depends(current_animateur),
) -> ProjectDocument:
    project = await project_or_404(project_id)
    is_creator = project["created_by"]["id"] == helper.id
    if not is_creator and not await is_responsable_helper(helper.id):
        raise HTTPException(403, "Seul le responsable du projet peut retirer des membres.")
    if member_id == project["created_by"]["id"]:
        raise HTTPException(400, "Impossible de retirer le créateur du projet.")

    project["members"] = [m for m in project["members"] if m["id"] != member_id]
    await db.projects.update_one({"id": project_id}, {"$set": {"members": project["members"]}})
    return project


@router.get("/resources/{resource_id}/download")
async def download_project_resource(
    resource_id: str,
    _: AuthenticatedHelper = Depends(current_animateur),
) -> StreamingResponse:
    resource = await db.project_resources.find_one({"id": resource_id}, {"_id": 0})
    if not resource:
        raise HTTPException(404, "Ressource introuvable.")
    try:
        content, content_type = await asyncio.to_thread(get_object, resource["storage_path"])
    except Exception as error:
        raise HTTPException(502, "Le document est temporairement indisponible.") from error
    headers = {
        "Content-Disposition": f'attachment; filename="{resource["original_filename"]}"',
        "Content-Length": str(len(content)),
    }
    return StreamingResponse(BytesIO(content), media_type=resource.get("content_type", content_type), headers=headers)
