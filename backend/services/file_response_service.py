import mimetypes
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

# Module importé tel quel : `httpx.AsyncClient` est lu à chaque téléchargement, pour que les
# tests puissent le remplacer.
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from services import storage_service


CHUNK_SIZE = 256 * 1024


def safe_content_type(content_type: str | None) -> str:
    """Type MIME servable depuis le domaine de l'API : jamais de HTML, SVG, XML ni JavaScript."""
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if "/" not in media_type:
        return "application/octet-stream"
    subtype = media_type.split("/", 1)[1]
    if (
        media_type in {"text/html", "application/xhtml+xml"}
        or subtype == "xml"
        or subtype.endswith("+xml")
        or "svg" in subtype
        or "javascript" in subtype
        or "ecmascript" in subtype
    ):
        return "application/octet-stream"
    return media_type


def _resolve_file(storage_path: str) -> Path:
    # Lu à chaque appel : la racine peut être redéfinie (IRIS_STORAGE_ROOT, tests).
    root = storage_service.STORAGE_ROOT.resolve()
    source = (root / storage_path).resolve()

    try:
        source.relative_to(root)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail="Fichier introuvable.",
        ) from error

    if not source.is_file():
        raise HTTPException(
            status_code=404,
            detail="Fichier introuvable.",
        )

    return source


def _file_chunks(source: Path, start: int, length: int):
    # Générateur synchrone : lecture exécutée hors de la boucle async
    # par StreamingResponse.
    with source.open("rb") as file:
        file.seek(start)
        remaining = length

        while remaining > 0:
            chunk = file.read(min(CHUNK_SIZE, remaining))

            if not chunk:
                break

            remaining -= len(chunk)
            yield chunk


def _range_not_satisfiable(size: int):
    raise HTTPException(
        status_code=416,
        detail="Plage demandée invalide.",
        headers={
            "Content-Range": f"bytes */{size}",
            "Accept-Ranges": "bytes",
        },
    )


def stream_local_file(
    request: Request,
    storage_path: str,
    content_type: str | None = None,
    filename: str | None = None,
    attachment: bool = False,
) -> StreamingResponse:
    source = _resolve_file(storage_path)
    size = source.stat().st_size

    start = 0
    end = size - 1
    status_code = 200

    range_header = request.headers.get("range")

    # Sans gestion d'ETag/Last-Modified ici, un If-Range provoque
    # volontairement une réponse complète.
    if range_header and not request.headers.get("if-range"):
        # Les unités inconnues, plages multiples ou en-têtes mal formés
        # sont ignorés : réponse complète en 200.
        match = re.fullmatch(
            r"bytes=(\d*)-(\d*)",
            range_header.strip(),
            flags=re.IGNORECASE,
        )

        if match:
            raw_start, raw_end = match.groups()

            if raw_start or raw_end:
                try:
                    if raw_start:
                        start = int(raw_start)
                        end = int(raw_end) if raw_end else size - 1

                        if start >= size or end < start:
                            _range_not_satisfiable(size)

                        end = min(end, size - 1)
                    else:
                        suffix = int(raw_end)

                        if suffix <= 0 or size == 0:
                            _range_not_satisfiable(size)

                        start = max(0, size - suffix)
                        end = size - 1

                    status_code = 206
                except ValueError:
                    _range_not_satisfiable(size)

    length = max(0, end - start + 1)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }

    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    if filename is not None:
        # Ne jamais injecter directement un nom fourni par l'utilisateur
        # dans les en-têtes HTTP.
        safe_name = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
        safe_name = safe_name.replace("\r", "").replace("\n", "")

        disposition = "attachment" if attachment else "inline"
        encoded_name = quote(safe_name or "fichier", safe="")

        headers["Content-Disposition"] = (
            f"{disposition}; filename*=UTF-8''{encoded_name}"
        )

    media_type = safe_content_type(
        content_type or mimetypes.guess_type(source.name)[0]
    )

    return StreamingResponse(
        _file_chunks(source, start, length),
        status_code=status_code,
        media_type=media_type,
        headers=headers,
    )


# --------------------------------------------------------------------------------------
# Pièces jointes Discord (archives de salons, casiers)
# --------------------------------------------------------------------------------------

# Seuls les fichiers hébergés par le CDN Discord sont copiés localement.
ALLOWED_DISCORD_CDN_HOSTS = {"cdn.discordapp.com", "media.discordapp.net"}

# Seules ces images matricielles peuvent s'afficher dans le navigateur ; tout le reste
# (HTML, SVG, PDF, texte...) est servi en téléchargement.
INLINE_IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
_CONTENT_TYPE_ALIASES = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}


class DownloadTooLarge(ValueError):
    """Téléchargement interrompu : la taille maximale autorisée est dépassée."""


def attachment_extension(filename: str) -> str:
    """Extension brute du nom de fichier (à assainir avant tout chemin disque), « bin » sinon."""
    if not isinstance(filename, str):
        return "bin"
    return filename.rsplit(".", 1)[-1] if "." in filename else "bin"


def is_discord_cdn_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme == "https" and (parts.hostname or "").lower() in ALLOWED_DISCORD_CDN_HOSTS


def inline_image_type(content_type: str | None, filename: str) -> str | None:
    """Type image sûr si l'extension ET le type déclaré désignent une image matricielle."""
    by_extension = INLINE_IMAGE_TYPES.get(attachment_extension(filename).lower())
    if not by_extension:
        return None
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    declared = _CONTENT_TYPE_ALIASES.get(declared, declared)
    if not declared:
        return by_extension
    return declared if declared in INLINE_IMAGE_TYPES.values() else None


async def download_to_temp_file(
    url: str,
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
    timeout: float = 60.0,
) -> str:
    """Télécharge en flux vers un fichier temporaire, en s'arrêtant dès que `max_bytes` est dépassé.

    Retourne le chemin du fichier temporaire, à supprimer par l'appelant. Ne vérifie pas l'hôte :
    l'appelant passe d'abord par `is_discord_cdn_url`. En cas d'erreur (HTTP, réseau,
    `DownloadTooLarge`, annulation), le fichier partiel est supprimé et l'exception remonte.
    """
    temp_path = None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                total_size = 0
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_path = temp_file.name
                    async for chunk in response.aiter_bytes(chunk_size):
                        total_size += len(chunk)
                        if total_size > max_bytes:
                            raise DownloadTooLarge("Pièce jointe trop volumineuse pour être copiée localement.")
                        temp_file.write(chunk)
        return temp_path
    except BaseException:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
