@router.post("/meetings", response_model=MeetingSummary, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingSummaryCreate,
    helper: AuthenticatedHelper = Depends(current_responsable),
) -> MeetingSummary:
    now = datetime.now(timezone.utc).isoformat()
    meeting = MeetingSummary(
        id=str(uuid4()),
        title=payload.title.strip(),
        content_markdown=payload.content_markdown,
        meeting_date=payload.meeting_date,
        author={
            "id": helper.id,
            "username": helper.username,
            "display_name": helper.global_name,
            "avatar_url": helper.avatar_url,
        },
        created_at=now,
        updated_at=now,
    )
    await db.meeting_summaries.insert_one(meeting.model_dump())
    return meeting


@router.put("/meetings/{meeting_id}", response_model=MeetingSummary)
async def update_meeting(
    meeting_id: str,
    payload: MeetingSummaryUpdate,
    _: AuthenticatedHelper = Depends(current_staff),
) -> MeetingSummary:
    existing = await db.meeting_summaries.find_one({"id": meeting_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Résumé introuvable.")
    updated_at = datetime.now(timezone.utc).isoformat()
    await db.meeting_summaries.update_one(
        {"id": meeting_id},
        {"$set": {
            "title": payload.title.strip(),
            "content_markdown": payload.content_markdown,
            "meeting_date": payload.meeting_date,
            "updated_at": updated_at,
        }},
    )
    existing.update(
        title=payload.title.strip(),
        content_markdown=payload.content_markdown,
        meeting_date=payload.meeting_date,
        updated_at=updated_at,
    )
    return existing
