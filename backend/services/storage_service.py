import os
from pathlib import Path

import requests

from config import EMERGENT_LLM_KEY


STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "iris"
storage_key: str | None = None


def init_storage() -> str:
    global storage_key
    if storage_key:
        return storage_key
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("Clé de stockage Emergent absente.")
    response = requests.post(
        f"{STORAGE_URL}/init",
        json={"emergent_key": EMERGENT_LLM_KEY},
        timeout=30,
    )
    response.raise_for_status()
    storage_key = response.json()["storage_key"]
    return storage_key


def put_object_from_file(path: str, file_path: str, content_type: str) -> dict:
    global storage_key
    key = init_storage()
    with open(file_path, "rb") as file_handle:
        response = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=file_handle,
            timeout=900,
        )
    if response.status_code == 403:
        storage_key = None
        return put_object_from_file(path, file_path, content_type)
    response.raise_for_status()
    return response.json()


def get_object(path: str) -> tuple[bytes, str]:
    global storage_key
    key = init_storage()
    response = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key},
        timeout=180,
    )
    if response.status_code == 403:
        storage_key = None
        return get_object(path)
    response.raise_for_status()
    return response.content, response.headers.get("Content-Type", "application/octet-stream")


def resource_path(resource_id: str, extension: str) -> str:
    return f"{APP_NAME}/resources/{resource_id}.{extension.lower()}"


def extension_from_filename(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")