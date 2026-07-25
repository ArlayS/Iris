import asyncio
import os
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from database import db
from models.resource import ResourceDocument, ResourceListResponse
from models.ticket import AuthenticatedHelper
from services.auth_service import current_admin, current_helper
from services.storage_service import (
    extension_from_filename,
    get_object,
    put_object_from_file,
    resource_path,
)


router = APIRouter(prefix="/resources", tags=["resources"])
MAX_RESOURCE_SIZE = 250 * 1024 * 1024
ALLOWED_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "txt": "text/plain",
}


async def resource_or_404(resource_id: str) -> dict:
    resource = await db.resources.find_one(
        {"id": resource_id, "is_deleted": False},
        {"_id": 0},
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Ressource introuvable.")
    return resource


@router.get("", response_model=ResourceListResponse)
async def list_resources(
    _: AuthenticatedHelper = Depends(current_helper),
) -> ResourceListResponse:
    resources = await db.resources.find(
        {"is_deleted": False},
        {"_id": 0, "storage_path": 0},
    ).sort("created_at", -1).to_list(1000)
    return ResourceListResponse(resources=resources)


@router.post("", response_model=ResourceDocument, status_code=status.HTTP_201_CREATED)
async def upload_resource(
    title: str = Form(..., max_length=160),
    description: str = Form("", max_length=2000),
    category: str = Form("Général", max_length=60),
    file: UploadFile = File(...),
    helper: AuthenticatedHelper = Depends(current_admin),
) -> ResourceDocument:
    if not file.filename:
        raise HTTPException(status_code=422, detail="Choisissez un fichier à publier.")
    extension = extension_from_filename(file.filename)
    if extension not in ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail="Format non autorisé.")

    temp_path: str | None = None
    total_size = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > MAX_RESOURCE_SIZE:
                    raise HTTPException(status_code=413, detail="La taille maximale est de 250 Mo.")
                temp_file.write(chunk)
        resource_id = str(uuid4())
        content_type = ALLOWED_TYPES[extension]
        storage_result = await asyncio.to_thread(
            put_object_from_file,
            resource_path(resource_id, extension),
            temp_path,
            content_type,
        )
        resource = ResourceDocument(
            id=resource_id,
            title=title.strip(),
            description=description.strip(),
            category=category.strip() or "Général",
            original_filename=file.filename,
            content_type=content_type,
            size=storage_result.get("size", total_size),
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by={
                "id": helper.id,
                "username": helper.username,
                "display_name": helper.global_name,
                "avatar_url": helper.avatar_url,
            },
        )
        document = resource.model_dump()
        document["storage_path"] = storage_result["path"]
        document["is_deleted"] = False
        await db.resources.insert_one(document)
        return resource
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.get("/{resource_id}/download")
async def download_resource(
    resource_id: str,
    _: AuthenticatedHelper = Depends(current_helper),
) -> StreamingResponse:
    resource = await resource_or_404(resource_id)
    try:
        content, content_type = await asyncio.to_thread(get_object, resource["storage_path"])
    except Exception as error:
        raise HTTPException(status_code=502, detail="Le document est temporairement indisponible.") from error
    headers = {
        "Content-Disposition": f'attachment; filename="{resource["original_filename"]}"',
        "Content-Length": str(len(content)),
    }
    return StreamingResponse(BytesIO(content), media_type=resource.get("content_type", content_type), headers=headers)


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: str,
    _: AuthenticatedHelper = Depends(current_admin),
) -> None:
    await resource_or_404(resource_id)
    await db.resources.update_one(
        {"id": resource_id, "is_deleted": False},
        {"$set": {"is_deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat()}},
    )