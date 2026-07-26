import shutil
from pathlib import Path


STORAGE_ROOT = Path("/app/storage")
APP_NAME = "iris"


def init_storage() -> str:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return "local"


def put_object_from_file(path: str, file_path: str, content_type: str) -> dict:
    init_storage()
    destination = STORAGE_ROOT / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file_path, destination)
    size = destination.stat().st_size
    return {"path": path, "size": size}


def get_object(path: str) -> tuple[bytes, str]:
    source = STORAGE_ROOT / path
    if not source.exists():
        raise FileNotFoundError(f"Ressource introuvable sur le disque : {path}")
    content = source.read_bytes()
    return content, "application/octet-stream"


def resource_path(resource_id: str, extension: str) -> str:
    return f"{APP_NAME}/resources/{resource_id}.{extension.lower()}"


def extension_from_filename(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")
