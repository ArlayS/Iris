import os
import re
import shutil
from pathlib import Path


STORAGE_ROOT = Path(os.environ.get("IRIS_STORAGE_ROOT") or "/app/storage")
APP_NAME = "iris"

_SAFE_EXTENSION = re.compile(r"[a-z0-9]{1,10}")


def init_storage() -> str:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return "local"


def _resolve_inside_root(path: str) -> Path:
    # Refuse tout chemin qui sortirait du répertoire de stockage ("..", chemin absolu, lien...).
    root = STORAGE_ROOT.resolve()
    target = (root / path).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError(f"Chemin de stockage invalide : {path}")
    return target


def put_object_from_file(path: str, file_path: str, content_type: str) -> dict:
    init_storage()
    destination = _resolve_inside_root(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file_path, destination)
    size = destination.stat().st_size
    return {"path": path, "size": size}


def put_object_from_bytes(path: str, data: bytes, content_type: str) -> dict:
    init_storage()
    destination = _resolve_inside_root(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {"path": path, "size": len(data)}


def get_object(path: str) -> tuple[bytes, str]:
    try:
        source = _resolve_inside_root(path)
    except ValueError as error:
        raise FileNotFoundError(f"Ressource introuvable sur le disque : {path}") from error
    if not source.is_file():
        raise FileNotFoundError(f"Ressource introuvable sur le disque : {path}")
    content = source.read_bytes()
    return content, "application/octet-stream"


def sanitize_extension(extension: str | None) -> str:
    """Extension sûre pour un chemin de stockage : [a-z0-9]{1,10}, sinon "bin"."""
    candidate = (extension or "").strip().lower().lstrip(".")
    return candidate if _SAFE_EXTENSION.fullmatch(candidate) else "bin"


def resource_path(resource_id: str, extension: str) -> str:
    return f"{APP_NAME}/resources/{resource_id}.{sanitize_extension(extension)}"


def channel_archive_attachment_path(archive_id: str, message_id: str, attachment_id: str, extension: str) -> str:
    return f"{APP_NAME}/channel_archives/{archive_id}/{message_id}/{attachment_id}.{sanitize_extension(extension)}"


def extension_from_filename(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")
