"""
Fichiers joints aux sanctions du casier.

- Fichiers des logs OasisBot : extraits à l'import (statut `pending`) puis copiés depuis le CDN Discord
  en tâche de fond (`schedule_mirror` → `mirror_pending`), car les URL signées expirent (~24 h).
- Fichiers ajoutés à la main par le staff : `save_upload`, `delete_upload` (suppression douce).
- « Récupérer les fichiers du log » : `resync_from_discord` relit le message et remet en file les
  fichiers manquants ou en échec ; le router lance ensuite la copie avec `schedule_mirror`.
- Lecture : `to_out` / `attachments_out` (jamais `source_url`), `stream_attachment` (copie locale).

Stockage : `iris/casiers/{casier_id}/{sanction_id}/{attachment_id}.{extension}` sous `IRIS_STORAGE_ROOT`.
Les sanctions et leurs fichiers ne sont jamais retirés des tableaux : toutes les écritures sont gardées par
index et par id (contrainte mongomock, spec section 2.5).
"""

import asyncio
import codecs
import logging
import os
import re
import tempfile
import weakref
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, Request

import config
from database import db
from services import casier_log_parser, file_response_service, storage_service

logger = logging.getLogger(__name__)

MAX_ATTACHMENTS_PER_SANCTION = 10
# Extensions acceptées pour un ajout manuel, avec le type enregistré (jamais celui du navigateur).
UPLOAD_EXTENSIONS = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "txt": "text/plain",
}
MIRROR_CONCURRENCY = 3
# Au-delà, un fichier `pending` est considéré comme abandonné (tâche perdue) et peut être relancé.
PENDING_STALE_AFTER = timedelta(minutes=15)
UPLOAD_CHUNK_SIZE = 1024 * 1024
DEFAULT_FILENAME = "fichier"

HEX_ID_PATTERN = re.compile(r"[0-9a-f]{24}")
ATTACHMENT_ID_PATTERN = re.compile(r"(?:[0-9]{17,20}|[0-9a-f]{24})")
_DISCORD_ID_PATTERN = re.compile(r"[0-9]{1,20}")

_SIGNATURES = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "pdf": (b"%PDF-",),
}
_SIGNATURE_LENGTH = 16

SANCTION_NOT_FOUND = "Sanction introuvable."
FILE_NOT_FOUND = "Fichier introuvable."
CASIER_CHANGED = "Le casier a changé, réessayez."
LOCAL_COPY_UNAVAILABLE = "Copie locale indisponible pour ce fichier."
FORMAT_NOT_ALLOWED = "Format non autorisé (images, PDF ou TXT)."
SIGNATURE_MISMATCH = "Le contenu du fichier ne correspond pas à son extension."
EMPTY_FILE = "Le fichier est vide."
UPLOAD_STORAGE_FAILED = "Enregistrement du fichier impossible."
DISCORD_FILE_NOT_REMOVABLE = "Les fichiers importés depuis Discord ne peuvent pas être retirés."
DELETE_FORBIDDEN = "Seul l'auteur ou un Responsable peut retirer ce fichier."
NO_LOG_MESSAGE = "Cette sanction n'a pas de message de log Discord."
COPY_IN_PROGRESS = "Une copie des fichiers est déjà en cours."
LOG_MESSAGE_UNAVAILABLE = "Message de log introuvable ou inaccessible sur Discord."

MIRROR_ERROR_NOT_CDN = "Adresse refusée : le fichier n'est pas une pièce jointe du CDN Discord."
MIRROR_ERROR_DOWNLOAD = (
    "Fichier inaccessible sur Discord (lien expiré ?). Utilisez « Récupérer les fichiers du log »."
)
MIRROR_ERROR_STORAGE = "Copie locale impossible (stockage indisponible)."
MIRROR_ERROR_UNEXPECTED = "Copie impossible. Utilisez « Récupérer les fichiers du log »."


# --------------------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _object_id(value) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


def _items(container, key: str) -> list:
    value = container.get(key) if isinstance(container, dict) else None
    return value if isinstance(value, list) else []


def _megabytes(max_bytes: int) -> str:
    megabytes = max_bytes / (1024 * 1024)
    return f"{megabytes:.0f}" if megabytes.is_integer() else f"{megabytes:.1f}".replace(".", ",")


def _too_large_error(max_bytes: int) -> str:
    return f"Fichier trop volumineux (max {_megabytes(max_bytes)} Mo)."


def _remove_quietly(path: str | None) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Fichier temporaire %s non supprimé.", path, exc_info=True)


def _sanction_position(casier, sanction_id: str) -> tuple[int, dict] | None:
    for index, sanction in enumerate(_items(casier, "sanctions")):
        if isinstance(sanction, dict) and sanction.get("id") and sanction.get("id") == sanction_id:
            return index, sanction
    return None


def _attachment_position(sanction, attachment_id: str) -> tuple[int, dict] | None:
    for index, attachment in enumerate(_items(sanction, "attachments")):
        if isinstance(attachment, dict) and attachment.get("id") and str(attachment["id"]) == attachment_id:
            return index, attachment
    return None


def _is_active(attachment) -> bool:
    return isinstance(attachment, dict) and not attachment.get("deleted_at")


def _active_count(sanction, origin: str | None = None) -> int:
    return sum(
        1
        for attachment in _items(sanction, "attachments")
        if _is_active(attachment) and (origin is None or (attachment.get("origin") or "discord") == origin)
    )


def _extension_of(attachment: dict) -> str:
    extension = attachment.get("extension")
    if not isinstance(extension, str) or not extension:
        extension = file_response_service.attachment_extension(attachment.get("filename") or "")
    return storage_service.sanitize_extension(extension)


def _is_cdn_attachment_url(url) -> bool:
    """URL https du CDN Discord sous `/attachments/` (ni avatar, ni emoji, ni autre hôte)."""
    if not file_response_service.is_discord_cdn_url(url):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.username is not None or parts.password is not None or port is not None:
        return False
    decoded = unquote(parts.path)
    if not parts.path.startswith("/attachments/") or "\\" in decoded:
        return False
    return not any(segment in {".", ".."} for segment in decoded.split("/"))


def attachment_storage_path(casier_id: str, sanction_id: str, attachment_id: str, extension: str | None) -> str:
    """Chemin relatif sous IRIS_STORAGE_ROOT ; `ValueError` si un identifiant n'a pas la forme attendue."""
    casier_id, sanction_id, attachment_id = str(casier_id), str(sanction_id), str(attachment_id)
    if not HEX_ID_PATTERN.fullmatch(casier_id) or not HEX_ID_PATTERN.fullmatch(sanction_id):
        raise ValueError("Identifiant de casier ou de sanction invalide.")
    if not ATTACHMENT_ID_PATTERN.fullmatch(attachment_id):
        raise ValueError("Identifiant de fichier invalide.")
    extension = storage_service.sanitize_extension(extension)
    return f"{storage_service.APP_NAME}/casiers/{casier_id}/{sanction_id}/{attachment_id}.{extension}"


def _remove_stored_file(storage_path: str) -> None:
    try:
        storage_service._resolve_inside_root(storage_path).unlink(missing_ok=True)
    except (OSError, ValueError):
        logger.warning("Fichier %s non effacé du disque.", storage_path, exc_info=True)


def _stored_file_exists(casier_id: str, sanction_id: str, attachment: dict) -> bool:
    try:
        path = attachment_storage_path(casier_id, sanction_id, attachment.get("id"), _extension_of(attachment))
        return storage_service._resolve_inside_root(path).is_file()
    except (OSError, ValueError):
        return False


async def _guarded_update(casier_oid: ObjectId, sanction_id: str, make_update) -> str:
    """Écriture gardée par index (spec 2.5) sur une sanction relue juste avant.

    `make_update(index, sanction)` renvoie `(garde, mise_a_jour)` ou None (rien à écrire). Si la garde
    échoue, le document est relu et l'écriture retentée une fois. Retourne "updated", "skipped",
    "missing" (sanction absente) ou "conflict" (deux échecs de garde).
    """
    for _ in range(2):
        casier = await db.casiers.find_one({"_id": casier_oid}, {"sanctions": 1})
        position = _sanction_position(casier, sanction_id)
        if position is None:
            return "missing"
        index, sanction = position
        built = make_update(index, sanction)
        if built is None:
            return "skipped"
        guard, update = built
        result = await db.casiers.update_one(
            {"_id": casier_oid, f"sanctions.{index}.id": sanction_id, **guard},
            update,
        )
        if result.matched_count:
            return "updated"
    return "conflict"


async def _update_attachment(
    casier_oid: ObjectId,
    sanction_id: str,
    attachment_id: str,
    fields: dict,
    expected: dict | None = None,
) -> str:
    """`$set` de champs d'un fichier, gardé par son id et par les valeurs `expected` (ex. statut)."""
    expected = expected or {}

    def make_update(index: int, sanction: dict):
        position = _attachment_position(sanction, attachment_id)
        if position is None:
            return None
        k, current = position
        if any(current.get(key) != value for key, value in expected.items()):
            return None
        prefix = f"sanctions.{index}.attachments.{k}"
        guard = {f"{prefix}.id": current["id"]}
        guard.update({f"{prefix}.{key}": value for key, value in expected.items()})
        update = {f"{prefix}.{key}": value for key, value in fields.items()}
        update["updated_at"] = now_iso()
        return guard, {"$set": update}

    return await _guarded_update(casier_oid, sanction_id, make_update)


# --------------------------------------------------------------------------------------
# Copie en tâche de fond des fichiers des logs Discord
# --------------------------------------------------------------------------------------

# Références fortes : une tâche sans référence peut être ramassée avant la fin.
_mirror_tasks: set[asyncio.Task] = set()
# Un sémaphore par boucle : un sémaphore lié à une boucle lève RuntimeError depuis une autre.
_mirror_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)
_strong_mirror_semaphores: dict = {}


def _mirror_semaphore() -> asyncio.Semaphore:
    """Sémaphore de copie (3 téléchargements simultanés) de la boucle en cours, créé à la demande."""
    loop = asyncio.get_running_loop()
    try:
        semaphore = _mirror_semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(MIRROR_CONCURRENCY)
            _mirror_semaphores[loop] = semaphore
    except TypeError:
        # Boucle sans référence faible possible : une seule boucle vit alors tout le processus.
        semaphore = _strong_mirror_semaphores.get(loop)
        if semaphore is None:
            semaphore = asyncio.Semaphore(MIRROR_CONCURRENCY)
            _strong_mirror_semaphores[loop] = semaphore
    return semaphore


def schedule_mirror(casier_id: str, sanction_id: str) -> None:
    """Lance sans attendre la copie des fichiers `pending` d'une sanction.

    Sans boucle asyncio en cours, rien n'est lancé : les fichiers restent `pending` (la migration de
    démarrage ou « Récupérer les fichiers du log » les reprendra).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "Copie des fichiers non lancée (aucune boucle asyncio) : casier %s, sanction %s.",
            casier_id,
            sanction_id,
        )
        return
    task = loop.create_task(mirror_pending(str(casier_id), str(sanction_id)))
    _mirror_tasks.add(task)
    task.add_done_callback(_mirror_tasks.discard)


async def _download_and_store(casier_id: str, sanction_id: str, attachment: dict) -> dict:
    """Champs à écrire sur le fichier après une tentative de copie (jamais d'exception)."""
    url = attachment.get("source_url")
    if not _is_cdn_attachment_url(url):
        return {"status": "failed", "error": MIRROR_ERROR_NOT_CDN}

    storage_path = attachment_storage_path(casier_id, sanction_id, attachment["id"], _extension_of(attachment))
    max_bytes = config.CASIER_ATTACHMENT_MAX_BYTES
    temp_path = None
    try:
        async with _mirror_semaphore():
            try:
                temp_path = await file_response_service.download_to_temp_file(url, max_bytes=max_bytes)
            except file_response_service.DownloadTooLarge:
                return {"status": "too_large", "error": _too_large_error(max_bytes)}
            except Exception:
                logger.warning("Téléchargement impossible pour le fichier %s.", attachment["id"], exc_info=True)
                return {"status": "failed", "error": MIRROR_ERROR_DOWNLOAD}

            try:
                stored = await asyncio.to_thread(
                    storage_service.put_object_from_file,
                    storage_path,
                    temp_path,
                    attachment.get("content_type") or "application/octet-stream",
                )
            except Exception:
                logger.exception("Enregistrement local impossible pour le fichier %s.", attachment["id"])
                _remove_stored_file(storage_path)
                return {"status": "failed", "error": MIRROR_ERROR_STORAGE}
    finally:
        _remove_quietly(temp_path)

    return {"status": "stored", "error": None, "size": stored.get("size"), "stored_at": now_iso()}


async def _mirror_one(casier_id: str, sanction_id: str, attachment: dict) -> str | None:
    try:
        fields = await _download_and_store(casier_id, sanction_id, attachment)
    except Exception:
        logger.exception("Copie impossible pour le fichier %s.", attachment.get("id"))
        fields = {"status": "failed", "error": MIRROR_ERROR_UNEXPECTED}
    try:
        outcome = await _update_attachment(
            ObjectId(casier_id), sanction_id, str(attachment["id"]), fields, expected={"status": "pending"}
        )
    except Exception:
        logger.exception("Statut du fichier %s non enregistré.", attachment.get("id"))
        return None
    return fields["status"] if outcome == "updated" else None


async def mirror_pending(casier_id: str, sanction_id: str) -> dict:
    """Copie localement les fichiers `pending` d'une sanction ; ne lève jamais (sauf annulation).

    Retourne le nombre de fichiers par statut écrit : {"stored": n, "failed": n, "too_large": n}.
    """
    summary = {"stored": 0, "failed": 0, "too_large": 0}
    casier_id, sanction_id = str(casier_id), str(sanction_id)
    try:
        if not HEX_ID_PATTERN.fullmatch(casier_id) or not HEX_ID_PATTERN.fullmatch(sanction_id):
            logger.warning("Copie ignorée : identifiants invalides (casier %r, sanction %r).", casier_id, sanction_id)
            return summary
        casier = await db.casiers.find_one({"_id": ObjectId(casier_id)}, {"sanctions": 1})
        position = _sanction_position(casier, sanction_id)
        if position is None:
            logger.warning("Copie ignorée : sanction %s introuvable dans le casier %s.", sanction_id, casier_id)
            return summary
        pending = [
            attachment
            for attachment in _items(position[1], "attachments")
            if _is_active(attachment)
            and attachment.get("status") == "pending"
            and ATTACHMENT_ID_PATTERN.fullmatch(str(attachment.get("id") or ""))
        ]
        results = await asyncio.gather(
            *(_mirror_one(casier_id, sanction_id, attachment) for attachment in pending),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Copie interrompue (casier %s, sanction %s) : %r", casier_id, sanction_id, result)
            elif result in summary:
                summary[result] += 1
    except Exception:
        logger.exception("Copie des fichiers impossible (casier %s, sanction %s).", casier_id, sanction_id)
    return summary


# --------------------------------------------------------------------------------------
# Fichiers ajoutés à la main
# --------------------------------------------------------------------------------------

def _signature_matches(extension: str, head: bytes) -> bool:
    if extension == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if extension == "txt":
        return True  # vérifié pendant la lecture : UTF-8 valide, sans octet nul
    return any(head.startswith(signature) for signature in _SIGNATURES.get(extension, ()))


async def _receive_upload(upload, extension: str, max_bytes: int) -> tuple[str, int]:
    """Lit l'envoi par morceaux vers un fichier temporaire (à supprimer par l'appelant), contrôles compris."""
    decoder = codecs.getincrementaldecoder("utf-8")() if extension == "txt" else None
    head = b""
    total = 0
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            temp_path = handle.name
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=_too_large_error(max_bytes))
                if len(head) < _SIGNATURE_LENGTH:
                    head += chunk[: _SIGNATURE_LENGTH - len(head)]
                if decoder is not None:
                    if b"\x00" in chunk:
                        raise HTTPException(status_code=422, detail=SIGNATURE_MISMATCH)
                    try:
                        decoder.decode(chunk)
                    except UnicodeDecodeError as error:
                        raise HTTPException(status_code=422, detail=SIGNATURE_MISMATCH) from error
                handle.write(chunk)
        if total == 0:
            raise HTTPException(status_code=422, detail=EMPTY_FILE)
        if decoder is not None:
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError as error:
                raise HTTPException(status_code=422, detail=SIGNATURE_MISMATCH) from error
        if not _signature_matches(extension, head):
            raise HTTPException(status_code=422, detail=SIGNATURE_MISMATCH)
        return temp_path, total
    except BaseException:
        _remove_quietly(temp_path)
        raise


async def save_upload(casier: dict, sanction_id: str, upload, uploaded_by: dict | None) -> dict:
    """Ajoute à une sanction un fichier envoyé par un membre du staff et retourne l'Attachment enregistré.

    `upload` : `UploadFile` (ou tout objet avec `filename` et `async read(n)`). Erreurs (avant écriture) :
    404 sanction, 422 format/contenu/vide, 409 limite de fichiers, 413 taille ; 409 si le casier change
    deux fois pendant l'écriture (le fichier copié est alors effacé).
    """
    casier_id = str(casier.get("_id"))
    position = _sanction_position(casier, sanction_id)
    if position is None:
        raise HTTPException(status_code=404, detail=SANCTION_NOT_FOUND)
    sanction = position[1]

    filename = casier_log_parser.clean_filename(getattr(upload, "filename", None))
    extension = file_response_service.attachment_extension(filename).strip().lower()
    if extension not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=422, detail=FORMAT_NOT_ALLOWED)
    if _active_count(sanction) >= MAX_ATTACHMENTS_PER_SANCTION:
        raise HTTPException(status_code=409, detail=_limit_reached())

    attachment_id = str(ObjectId())
    storage_path = attachment_storage_path(casier_id, sanction_id, attachment_id, extension)
    content_type = UPLOAD_EXTENSIONS[extension]
    temp_path = None
    try:
        temp_path, size = await _receive_upload(upload, extension, config.CASIER_UPLOAD_MAX_BYTES)
        try:
            stored = await asyncio.to_thread(
                storage_service.put_object_from_file, storage_path, temp_path, content_type
            )
        except Exception as error:
            logger.exception("Enregistrement du fichier ajouté %s impossible.", attachment_id)
            _remove_stored_file(storage_path)
            raise HTTPException(status_code=500, detail=UPLOAD_STORAGE_FAILED) from error
    finally:
        _remove_quietly(temp_path)

    now = now_iso()
    attachment = {
        "id": attachment_id,
        "origin": "upload",
        "filename": filename,
        "extension": extension,
        "content_type": content_type,
        "size": stored.get("size", size),
        "source_url": None,
        "status": "stored",
        "error": None,
        "created_at": now,
        "stored_at": now,
        "uploaded_by": uploaded_by,
        "deleted_at": None,
        "deleted_by": None,
    }

    limit_reached = False

    def make_update(index: int, current: dict):
        nonlocal limit_reached
        if _active_count(current) >= MAX_ATTACHMENTS_PER_SANCTION:
            limit_reached = True
            return None
        return {}, {
            "$push": {f"sanctions.{index}.attachments": attachment},
            "$set": {"updated_at": now},
        }

    try:
        outcome = await _guarded_update(_object_id(casier.get("_id")), sanction_id, make_update)
    except BaseException:
        _remove_stored_file(storage_path)
        raise
    if outcome != "updated":
        _remove_stored_file(storage_path)
        if outcome == "missing":
            raise HTTPException(status_code=404, detail=SANCTION_NOT_FOUND)
        if limit_reached:
            raise HTTPException(status_code=409, detail=_limit_reached())
        raise HTTPException(status_code=409, detail=CASIER_CHANGED)
    return attachment


def _limit_reached() -> str:
    return f"Limite de {MAX_ATTACHMENTS_PER_SANCTION} fichiers atteinte pour cette sanction."


def can_delete(attachment, viewer: dict | None) -> bool:
    """Retrait possible : fichier ajouté à la main, non retiré, par son auteur ou un Responsable."""
    if not _is_active(attachment) or attachment.get("origin") != "upload" or not viewer:
        return False
    if viewer.get("is_responsable"):
        return True
    uploader_id = (attachment.get("uploaded_by") or {}).get("id")
    return bool(uploader_id) and str(uploader_id) == str(viewer.get("id"))


async def delete_upload(
    casier: dict,
    sanction_id: str,
    attachment_id: str,
    viewer: dict | None,
    deleted_by: dict | None,
) -> dict:
    """Retrait (suppression douce) d'un fichier ajouté à la main, puis effacement de la copie disque.

    `viewer` = {"id", "is_responsable"} ; `deleted_by` = Author. Retourne le fichier tel qu'avant le
    retrait, complété de `deleted_at` / `deleted_by`. Erreurs : 404, 409 (fichier Discord ou casier
    changé), 403.
    """
    casier_id = str(casier.get("_id"))
    position = _sanction_position(casier, sanction_id)
    if position is None:
        raise HTTPException(status_code=404, detail=SANCTION_NOT_FOUND)
    found = _attachment_position(position[1], str(attachment_id))
    if found is None or not _is_active(found[1]):
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)
    attachment = found[1]
    if attachment.get("origin") != "upload":
        raise HTTPException(status_code=409, detail=DISCORD_FILE_NOT_REMOVABLE)
    if not can_delete(attachment, viewer):
        raise HTTPException(status_code=403, detail=DELETE_FORBIDDEN)

    fields = {"deleted_at": now_iso(), "deleted_by": deleted_by}
    outcome = await _update_attachment(
        _object_id(casier.get("_id")), sanction_id, str(attachment_id), fields, expected={"deleted_at": None}
    )
    if outcome == "missing":
        raise HTTPException(status_code=404, detail=SANCTION_NOT_FOUND)
    if outcome == "skipped":
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)
    if outcome == "conflict":
        raise HTTPException(status_code=409, detail=CASIER_CHANGED)

    try:
        _remove_stored_file(
            attachment_storage_path(casier_id, sanction_id, attachment["id"], _extension_of(attachment))
        )
    except ValueError:
        logger.warning("Chemin du fichier %s invalide : rien à effacer.", attachment.get("id"))
    return {**attachment, **fields}


# --------------------------------------------------------------------------------------
# « Récupérer les fichiers du log »
# --------------------------------------------------------------------------------------

def _pending_since(attachment: dict) -> datetime | None:
    return _parse_datetime(attachment.get("queued_at")) or _parse_datetime(attachment.get("created_at"))


def _copy_in_progress(sanction: dict, now: datetime) -> bool:
    for attachment in _items(sanction, "attachments"):
        if not _is_active(attachment) or attachment.get("status") != "pending":
            continue
        since = _pending_since(attachment)
        if since is not None and now - since < PENDING_STALE_AFTER:
            return True
    return False


def _needs_requeue(casier_id: str, sanction_id: str, attachment: dict, now: datetime) -> bool:
    status = attachment.get("status")
    if status == "failed":
        return True
    if status == "pending":
        since = _pending_since(attachment)
        return since is None or now - since >= PENDING_STALE_AFTER
    if status == "stored":
        # Copie perdue (volume non persistant, restauration partielle) : on la refait.
        return not _stored_file_exists(casier_id, sanction_id, attachment)
    return False


def _plan_resync(casier_id: str, sanction_id: str, sanction: dict, files: list[dict], now: datetime):
    """(remises en file {position: champs}, nouveaux fichiers) pour les fichiers lus dans le log."""
    now_text = now.isoformat()
    attachments = _items(sanction, "attachments")
    positions = {
        str(attachment["id"]): index
        for index, attachment in enumerate(attachments)
        if isinstance(attachment, dict) and attachment.get("id")
    }
    discord_count = _active_count(sanction, origin="discord")
    requeue: dict[int, dict] = {}
    new_files: list[dict] = []
    for file in files:
        index = positions.get(str(file.get("id")))
        if index is None:
            if discord_count >= MAX_ATTACHMENTS_PER_SANCTION:
                continue
            entry = {**file, "created_at": now_text}
            if entry.get("status") == "pending":
                entry["queued_at"] = now_text
            new_files.append(entry)
            positions[str(file.get("id"))] = -1
            discord_count += 1
            continue
        if index < 0 or index in requeue:
            continue
        current = attachments[index]
        if (current.get("origin") or "discord") != "discord" or not _is_active(current):
            continue
        if not _needs_requeue(casier_id, sanction_id, current, now):
            continue
        fields = {
            "source_url": file.get("source_url"),
            "status": file.get("status"),
            "error": file.get("error"),
            "stored_at": None,
            "queued_at": now_text,
        }
        if file.get("size") is not None:
            fields["size"] = file["size"]
        if not current.get("content_type") and file.get("content_type"):
            fields["content_type"] = file["content_type"]
        if not current.get("extension"):
            fields["extension"] = file.get("extension")
        requeue[index] = fields
    return requeue, new_files


def _has_moderator(sanction: dict) -> bool:
    moderator = sanction.get("moderator")
    return isinstance(moderator, dict) and bool(moderator.get("id"))


async def _log_moderator(raw_message: dict, member_id, resolve_author) -> dict | None:
    from services import moderation_bot  # import local : le bot importe le service des casiers

    try:
        full_text = moderation_bot.raw_message_full_text(raw_message)
        mod_id = casier_log_parser.extract_moderator_id(full_text, member_id)
    except Exception:
        logger.exception("Modérateur illisible dans le message de log.")
        return None
    if not mod_id:
        return None
    moderator = {"id": str(mod_id), "username": None, "display_name": None}
    try:
        resolved = await resolve_author(str(mod_id))
    except Exception:
        logger.warning("Nom du modérateur %s non résolu.", mod_id, exc_info=True)
        return moderator
    if isinstance(resolved, dict):
        moderator["username"] = resolved.get("username")
        moderator["display_name"] = resolved.get("display_name")
    return moderator


async def resync_from_discord(casier: dict, sanction: dict, *, resolve_author) -> dict:
    """Relit le message de log d'une sanction et prépare la copie de ses fichiers.

    Ajoute les fichiers absents (`pending`), remet en file ceux en échec (URL fraîche), et complète
    `moderator` s'il manque (`await resolve_author(mod_id)` -> Author, best-effort). Ne lance pas la
    copie : l'appelant appelle ensuite `schedule_mirror` si `files_queued > 0`.
    Erreurs, toutes avant écriture : 409 sans message de log, 409 copie déjà en cours, 502 message
    illisible. Retourne {"files_found", "files_queued", "moderator_filled"}.
    """
    casier_oid = _object_id(casier.get("_id"))
    casier_id = str(casier_oid)
    sanction_id = str(sanction.get("id") or "")
    source = sanction.get("source") if isinstance(sanction.get("source"), dict) else {}
    channel_id = str(source.get("channel_id") or "").strip()
    message_id = str(source.get("message_id") or "").strip()
    if not _DISCORD_ID_PATTERN.fullmatch(channel_id) or not _DISCORD_ID_PATTERN.fullmatch(message_id):
        raise HTTPException(status_code=409, detail=NO_LOG_MESSAGE)

    now = datetime.now(timezone.utc)
    if _copy_in_progress(sanction, now):
        raise HTTPException(status_code=409, detail=COPY_IN_PROGRESS)

    from services import moderation_bot  # import local : le bot importe le service des casiers

    try:
        raw_message = await moderation_bot.fetch_raw_message(int(channel_id), int(message_id))
    except Exception:
        logger.warning("Message de log %s/%s illisible.", channel_id, message_id, exc_info=True)
        raw_message = None
    if not isinstance(raw_message, dict):
        raise HTTPException(status_code=502, detail=LOG_MESSAGE_UNAVAILABLE)

    try:
        files = casier_log_parser.extract_message_files(raw_message, now=now)
    except Exception:
        logger.exception("Fichiers illisibles dans le message de log %s.", message_id)
        files = []

    moderator = None
    if not _has_moderator(sanction):
        moderator = await _log_moderator(raw_message, casier.get("discord_id"), resolve_author)

    stats = {"files_found": len(files), "files_queued": 0, "moderator_filled": False}
    planned: dict = {}

    def make_set(index: int, current: dict):
        requeue, new_files = _plan_resync(casier_id, sanction_id, current, files, now)
        planned["new_files"] = new_files
        planned["requeued"] = sum(1 for fields in requeue.values() if fields.get("status") == "pending")
        update, guard = {}, {}
        for position, fields in requeue.items():
            prefix = f"sanctions.{index}.attachments.{position}"
            guard[f"{prefix}.id"] = current["attachments"][position]["id"]
            update.update({f"{prefix}.{key}": value for key, value in fields.items()})
        planned["moderator"] = moderator is not None and not _has_moderator(current)
        if planned["moderator"]:
            update[f"sanctions.{index}.moderator"] = moderator
        if not update:
            return None
        update["updated_at"] = now_iso()
        return guard, {"$set": update}

    outcome = await _guarded_update(casier_oid, sanction_id, make_set)
    _raise_for_outcome(outcome)
    if outcome == "updated":
        stats["files_queued"] += planned.get("requeued", 0)
        stats["moderator_filled"] = planned.get("moderator", False)

    if planned.get("new_files"):
        pushed: dict = {}

        def make_push(index: int, current: dict):
            # Relu après la première écriture : seuls les fichiers toujours absents sont ajoutés.
            _, new_files = _plan_resync(casier_id, sanction_id, current, files, now)
            pushed["new_files"] = new_files
            if not new_files:
                return None
            return {}, {
                "$push": {f"sanctions.{index}.attachments": {"$each": new_files}},
                "$set": {"updated_at": now_iso()},
            }

        outcome = await _guarded_update(casier_oid, sanction_id, make_push)
        _raise_for_outcome(outcome)
        if outcome == "updated":
            stats["files_queued"] += sum(1 for file in pushed["new_files"] if file.get("status") == "pending")

    return stats


def _raise_for_outcome(outcome: str) -> None:
    if outcome == "missing":
        raise HTTPException(status_code=404, detail=SANCTION_NOT_FOUND)
    if outcome == "conflict":
        raise HTTPException(status_code=409, detail=CASIER_CHANGED)


# --------------------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------------------

def find_attachment(sanction: dict, attachment_id: str) -> dict | None:
    """Fichier non retiré de la sanction, ou None."""
    found = _attachment_position(sanction, str(attachment_id))
    return found[1] if found and _is_active(found[1]) else None


def to_out(attachment: dict, casier_id: str, sanction_id: str, viewer: dict | None) -> dict:
    """Format AttachmentOut (sans `source_url` ni champs internes). `viewer` = {"id", "is_responsable"}."""
    attachment_id = str(attachment.get("id") or "")
    filename = attachment.get("filename") if isinstance(attachment.get("filename"), str) else ""
    filename = filename or DEFAULT_FILENAME
    content_type = attachment.get("content_type") if isinstance(attachment.get("content_type"), str) else None
    status = attachment.get("status") if isinstance(attachment.get("status"), str) else "failed"
    size = attachment.get("size")
    stored = status == "stored"
    return {
        "id": attachment_id,
        "origin": attachment.get("origin") or "discord",
        "filename": filename,
        "content_type": content_type,
        "size": size if isinstance(size, int) and not isinstance(size, bool) else None,
        "status": status,
        "error": attachment.get("error"),
        "inline": stored and file_response_service.inline_image_type(content_type, filename) is not None,
        "download_url": (
            f"/moderation/casiers/{casier_id}/sanctions/{sanction_id}/attachments/{attachment_id}"
            if stored
            else None
        ),
        "created_at": attachment.get("created_at"),
        "uploaded_by": attachment.get("uploaded_by"),
        "can_delete": can_delete(attachment, viewer),
    }


def attachments_out(sanction: dict, casier_id: str, viewer: dict | None) -> list[dict]:
    """Fichiers non retirés d'une sanction, dans l'ordre d'ajout, au format AttachmentOut."""
    sanction_id = str(sanction.get("id") or "")
    return [
        to_out(attachment, casier_id, sanction_id, viewer)
        for attachment in _items(sanction, "attachments")
        if _is_active(attachment) and attachment.get("id")
    ]


def stream_attachment(
    request: Request,
    casier_id: str,
    sanction_id: str,
    attachment: dict | None,
    *,
    download: bool = False,
):
    """Sert la copie locale : inline seulement pour png/jpeg/gif/webp (extension ET type), sinon téléchargement."""
    if not _is_active(attachment):
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)
    if attachment.get("status") != "stored":
        raise HTTPException(status_code=404, detail=LOCAL_COPY_UNAVAILABLE)
    filename = attachment.get("filename") if isinstance(attachment.get("filename"), str) else ""
    filename = filename or DEFAULT_FILENAME
    try:
        storage_path = attachment_storage_path(casier_id, sanction_id, attachment.get("id"), _extension_of(attachment))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=LOCAL_COPY_UNAVAILABLE) from error
    inline_type = file_response_service.inline_image_type(attachment.get("content_type"), filename)
    try:
        return file_response_service.stream_local_file(
            request,
            storage_path,
            content_type=inline_type or "application/octet-stream",
            filename=filename,
            attachment=inline_type is None or download,
        )
    except HTTPException as error:
        if error.status_code == 404:
            raise HTTPException(status_code=404, detail=LOCAL_COPY_UNAVAILABLE) from error
        raise
