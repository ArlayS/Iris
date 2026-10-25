"""Tests hors-ligne : import des logs OasisBot (mute, durée, modérateur, fichiers) et fichiers des sanctions.

Aucun appel réseau : Discord, le CDN (httpx.MockTransport) et MongoDB (mongomock) sont simulés.
Lancer depuis backend/ : python -m pytest -q -p no:cacheprovider -n 0 tests/test_casier_ingest.py
"""
import security_harness as h  # noqa: I001  (doit être importé en premier)

import asyncio
import inspect
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord
import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import config
from services import (
    casier_attachments,
    casier_log_parser,
    casier_service,
    file_response_service,
    moderation_bot,
    storage_service,
)

MEMBER_ID = "1153638521786093582"
MOD_ID = "900000000000000001"
OASIS_BOT_ID = 800000000000000001
MUTE_CHANNEL_ID = 600000000000000005
LOG_MESSAGE_ID = 1299887766554433200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
VIEWER_STAFF = {"id": h.USER_IDS["staff"], "is_responsable": False}
VIEWER_OTHER = {"id": h.USER_IDS["admin"], "is_responsable": False}
VIEWER_RESPONSABLE = {"id": h.USER_IDS["responsable"], "is_responsable": True}
STAFF_AUTHOR = {"id": h.USER_IDS["staff"], "username": "test-staff", "display_name": "Inès (staff)"}


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    h.reset_db()
    h.reset_discord()
    root = tmp_path / "storage"
    monkeypatch.setattr(storage_service, "STORAGE_ROOT", root)
    return root


# --------------------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------------------

class FakeCdn:
    def __init__(self):
        self.requests: list[str] = []
        self.status = 200
        self.bodies: dict[str, bytes] = {}
        self.default_body = PNG

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if self.status != 200:
            return httpx.Response(self.status)
        body = self.bodies.get(request.url.path, self.default_body)

        async def stream():
            for start in range(0, len(body), 8):
                yield body[start:start + 8]

        return httpx.Response(200, content=stream())


@pytest.fixture
def fake_cdn(monkeypatch):
    cdn = FakeCdn()
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(cdn.handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(file_response_service.httpx, "AsyncClient", client_factory)
    return cdn


@pytest.fixture
def temp_spy(monkeypatch):
    """Mémorise les fichiers temporaires créés par le téléchargement (pour vérifier leur suppression)."""
    paths: list[str] = []
    real_download = file_response_service.download_to_temp_file

    async def spy(url, **kwargs):
        path = await real_download(url, **kwargs)
        paths.append(path)
        return path

    monkeypatch.setattr(file_response_service, "download_to_temp_file", spy)
    return paths


@pytest.fixture
def mirror_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(casier_attachments, "schedule_mirror", lambda c, s: calls.append((c, s)))
    return calls


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _cdn_url(attachment_id: str, filename: str = "capture.png", host: str = "cdn.discordapp.com") -> str:
    return f"https://{host}/attachments/{MUTE_CHANNEL_ID}/{attachment_id}/{filename}?ex=1&is=2&hm=3"


def _attachment(attachment_id: str = "1299887766554433221", *, filename: str = "capture.png", **overrides) -> dict:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    attachment = {
        "id": attachment_id,
        "origin": "discord",
        "filename": filename,
        "extension": extension,
        "content_type": "image/png" if extension == "png" else None,
        "size": None,
        "source_url": _cdn_url(attachment_id, filename),
        "status": "pending",
        "error": None,
        "created_at": _iso(datetime.now(timezone.utc)),
        "stored_at": None,
        "uploaded_by": None,
        "deleted_at": None,
        "deleted_by": None,
    }
    attachment.update(overrides)
    return attachment


def _upload_attachment(attachment_id: str | None = None, *, uploader: dict | None = None, **overrides) -> dict:
    attachment = _attachment(
        attachment_id or str(ObjectId()),
        origin="upload",
        source_url=None,
        status="stored",
        uploaded_by=uploader or STAFF_AUTHOR,
    )
    attachment.update(overrides)
    return attachment


def _sanction(sanction_id: str | None = None, *, attachments=None, source: bool = True, **overrides) -> dict:
    sanction = {
        "id": sanction_id or str(ObjectId()),
        "type": "mute",
        "reason": "Propos humiliants répétés.",
        "created_at": _iso(datetime.now(timezone.utc) - timedelta(minutes=30)),
        "created_by": dict(casier_service.BOT_AUTHOR),
        "moderator": None,
        "duration": "1 h",
        "duration_seconds": 3600,
        "expires_at": None,
        "source": {
            "channel_id": str(MUTE_CHANNEL_ID),
            "message_id": str(LOG_MESSAGE_ID),
            "message_url": f"https://discord.com/channels/1/{MUTE_CHANNEL_ID}/{LOG_MESSAGE_ID}",
        } if source else None,
        "attachments": list(attachments or []),
        "notes": [],
        "ai_flag_id": None,
    }
    sanction.update(overrides)
    return sanction


def _seed(*sanctions: dict) -> str:
    async def insert():
        result = await h.db.casiers.insert_one({
            "discord_id": MEMBER_ID,
            "created_at": _iso(datetime.now(timezone.utc) - timedelta(days=1)),
            "status": "vierge",
            "discord_member_snapshot": {"id": MEMBER_ID, "username": "mathis.b", "display_name": "mathis.b",
                                        "avatar_url": None},
            "created_by": dict(casier_service.BOT_AUTHOR),
            "is_prevention": False,
            "sanctions": list(sanctions),
            "fiches_s": [],
        })
        return str(result.inserted_id)

    return h.run(insert())


def _casier(casier_id: str) -> dict:
    return h.run(h.db.casiers.find_one({"_id": ObjectId(casier_id)}))


def _stored_sanction(casier_id: str, sanction_id: str) -> dict:
    return next(s for s in _casier(casier_id)["sanctions"] if s.get("id") == sanction_id)


def _stored_attachment(casier_id: str, sanction_id: str, attachment_id: str) -> dict:
    sanction = _stored_sanction(casier_id, sanction_id)
    return next(a for a in sanction["attachments"] if a["id"] == attachment_id)


def _disk_path(root, casier_id, sanction_id, attachment_id, extension):
    return root / casier_attachments.attachment_storage_path(casier_id, sanction_id, attachment_id, extension)


def _put_on_disk(casier_id, sanction_id, attachment_id, extension, data=PNG):
    path = casier_attachments.attachment_storage_path(casier_id, sanction_id, attachment_id, extension)
    storage_service.put_object_from_bytes(path, data, "application/octet-stream")


class FakeUpload:
    def __init__(self, filename, data: bytes = b"", *, content_type="text/html", generator=None):
        self.filename = filename
        self.content_type = content_type  # jamais utilisé : le type stocké vient de l'extension
        self._data = data
        self._offset = 0
        self._generator = generator
        self.reads = 0

    async def read(self, size: int = -1) -> bytes:
        self.reads += 1
        if self._generator is not None:
            return next(self._generator, b"")
        chunk = self._data[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


def _save(casier_id: str, sanction_id: str, upload, uploader=STAFF_AUTHOR) -> dict:
    return h.run(casier_attachments.save_upload(_casier(casier_id), sanction_id, upload, uploader))


def _http_error(callable_, *args, **kwargs) -> HTTPException:
    with pytest.raises(HTTPException) as caught:
        result = callable_(*args, **kwargs)
        if inspect.iscoroutine(result):
            h.run(result)
    return caught.value


# --------------------------------------------------------------------------------------
# Chemins de stockage
# --------------------------------------------------------------------------------------

def test_attachment_storage_path_layout():
    casier_id, sanction_id = str(ObjectId()), str(ObjectId())

    assert casier_attachments.attachment_storage_path(casier_id, sanction_id, "1299887766554433221", "PNG") == (
        f"iris/casiers/{casier_id}/{sanction_id}/1299887766554433221.png"
    )
    upload_id = str(ObjectId())
    assert casier_attachments.attachment_storage_path(casier_id, sanction_id, upload_id, "../../x").endswith(
        f"/{upload_id}.bin"
    )


@pytest.mark.parametrize(
    "casier_id, sanction_id, attachment_id",
    [
        ("6718f0c2a1b2c3d4e5f60718", "6718f0c2a1b2c3d4e5f60801", "../x"),
        ("6718f0c2a1b2c3d4e5f60718", "6718f0c2a1b2c3d4e5f60801", "1234"),
        ("6718f0c2a1b2c3d4e5f60718", "6718f0c2a1b2c3d4e5f60801", "1" * 21),
        ("6718f0c2a1b2c3d4e5f60718", "6718F0C2A1B2C3D4E5F60801", "1299887766554433221"),
        ("../../etc", "6718f0c2a1b2c3d4e5f60801", "1299887766554433221"),
        ("6718f0c2a1b2c3d4e5f60718", "6718f0c2a1b2c3d4e5f60801\n", "1299887766554433221"),
    ],
)
def test_attachment_storage_path_rejects_bad_ids(casier_id, sanction_id, attachment_id):
    with pytest.raises(ValueError):
        casier_attachments.attachment_storage_path(casier_id, sanction_id, attachment_id, "png")


# --------------------------------------------------------------------------------------
# Copie en tâche de fond
# --------------------------------------------------------------------------------------

def test_schedule_mirror_without_loop_leaves_files_pending(fake_cdn):
    sanction = _sanction(attachments=[_attachment()])
    casier_id = _seed(sanction)

    casier_attachments.schedule_mirror(casier_id, sanction["id"])

    assert _stored_attachment(casier_id, sanction["id"], "1299887766554433221")["status"] == "pending"
    assert fake_cdn.requests == []
    assert not casier_attachments._mirror_tasks


def test_schedule_mirror_runs_copy_in_background_task(fake_cdn, isolated_storage):
    sanction = _sanction(attachments=[_attachment()])
    casier_id = _seed(sanction)

    async def scenario():
        casier_attachments.schedule_mirror(casier_id, sanction["id"])
        tasks = list(casier_attachments._mirror_tasks)
        assert len(tasks) == 1
        await asyncio.gather(*tasks)
        await asyncio.sleep(0)  # rappels de fin de tâche
        return tasks[0].result()

    assert h.run(scenario()) == {"stored": 1, "failed": 0, "too_large": 0}
    assert not casier_attachments._mirror_tasks
    assert _stored_attachment(casier_id, sanction["id"], "1299887766554433221")["status"] == "stored"


def test_mirror_semaphore_is_created_per_event_loop():
    async def contend():
        semaphore = casier_attachments._mirror_semaphore()
        assert casier_attachments._mirror_semaphore() is semaphore

        async def hold():
            async with semaphore:
                await asyncio.sleep(0.01)

        # 5 détenteurs pour 3 places : le sémaphore se lie à la boucle en cours.
        await asyncio.gather(*(hold() for _ in range(5)))
        return semaphore

    first = h.run(contend())
    second = h.run(contend())  # une seconde boucle : aucune RuntimeError

    assert first is not second


def test_mirror_pending_copies_only_pending_cdn_files(fake_cdn, temp_spy, isolated_storage):
    fake_cdn.bodies[f"/attachments/{MUTE_CHANNEL_ID}/1299887766554433222/journal.txt"] = "Journal évènement".encode()
    stored_before = _attachment("1299887766554433223", status="stored", source_url=None, size=12)
    sanction = _sanction(attachments=[
        _attachment("1299887766554433221"),
        _attachment("1299887766554433222", filename="journal.txt"),
        stored_before,
        _attachment("1299887766554433224", status="too_large", error="Fichier trop volumineux (max 25 Mo)."),
        _attachment("1299887766554433225", deleted_at=_iso(datetime.now(timezone.utc))),
    ])
    other = _sanction(attachments=[_attachment("1299887766554433226")])
    casier_id = _seed(sanction, other)

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary == {"stored": 2, "failed": 0, "too_large": 0}
    assert len(fake_cdn.requests) == 2
    png = _stored_attachment(casier_id, sanction["id"], "1299887766554433221")
    assert png["status"] == "stored" and png["error"] is None
    assert png["size"] == len(PNG) and png["stored_at"]
    assert _disk_path(isolated_storage, casier_id, sanction["id"], png["id"], "png").read_bytes() == PNG
    text = _stored_attachment(casier_id, sanction["id"], "1299887766554433222")
    assert _disk_path(isolated_storage, casier_id, sanction["id"], text["id"], "txt").read_bytes() == (
        "Journal évènement".encode()
    )
    assert _stored_attachment(casier_id, sanction["id"], stored_before["id"]) == stored_before
    assert _stored_attachment(casier_id, sanction["id"], "1299887766554433224")["status"] == "too_large"
    assert _stored_attachment(casier_id, sanction["id"], "1299887766554433225")["status"] == "pending"
    assert _stored_attachment(casier_id, other["id"], "1299887766554433226")["status"] == "pending"
    assert _casier(casier_id).get("updated_at")
    assert temp_spy and not any(os.path.exists(path) for path in temp_spy)


def test_mirror_pending_works_on_media_proxy_and_legacy_attachment_without_extension(fake_cdn, isolated_storage):
    attachment = _attachment(source_url=_cdn_url("1299887766554433221", host="media.discordapp.net"))
    del attachment["extension"]
    sanction = _sanction(attachments=[attachment])
    casier_id = _seed(sanction)

    h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert _stored_attachment(casier_id, sanction["id"], attachment["id"])["status"] == "stored"
    assert _disk_path(isolated_storage, casier_id, sanction["id"], attachment["id"], "png").is_file()


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/attachments/1/2/capture.png",
        "http://cdn.discordapp.com/attachments/1/2/capture.png",
        "https://cdn.discordapp.com/avatars/1/abc.png",
        "https://cdn.discordapp.com.evil.example/attachments/1/2/capture.png",
        "https://user@cdn.discordapp.com/attachments/1/2/capture.png",
        "https://cdn.discordapp.com:8443/attachments/1/2/capture.png",
        "https://cdn.discordapp.com/attachments/1/%2e%2e/capture.png",
        "file:///etc/passwd",
        None,
    ],
)
def test_mirror_refuses_files_outside_discord_cdn_attachments(fake_cdn, url, isolated_storage):
    sanction = _sanction(attachments=[_attachment(source_url=url)])
    casier_id = _seed(sanction)

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary == {"stored": 0, "failed": 1, "too_large": 0}
    stored = _stored_attachment(casier_id, sanction["id"], "1299887766554433221")
    assert stored["status"] == "failed"
    assert stored["error"] == casier_attachments.MIRROR_ERROR_NOT_CDN
    assert fake_cdn.requests == []
    assert not (isolated_storage / "iris").exists()


def test_mirror_stream_over_limit_is_too_large_and_nothing_is_stored(fake_cdn, temp_spy, monkeypatch,
                                                                     isolated_storage):
    monkeypatch.setattr(config, "CASIER_ATTACHMENT_MAX_BYTES", 2 * 1024 * 1024)
    fake_cdn.default_body = b"x" * (2 * 1024 * 1024 + 1)
    sanction = _sanction(attachments=[_attachment(filename="video.mp4")])
    casier_id = _seed(sanction)

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary == {"stored": 0, "failed": 0, "too_large": 1}
    stored = _stored_attachment(casier_id, sanction["id"], "1299887766554433221")
    assert stored["status"] == "too_large"
    assert stored["error"] == "Fichier trop volumineux (max 2 Mo)."
    assert not (isolated_storage / "iris").exists()


def test_mirror_http_error_marks_file_failed(fake_cdn):
    fake_cdn.status = 404
    sanction = _sanction(attachments=[_attachment()])
    casier_id = _seed(sanction)

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary["failed"] == 1
    stored = _stored_attachment(casier_id, sanction["id"], "1299887766554433221")
    assert stored["status"] == "failed"
    assert stored["error"] == casier_attachments.MIRROR_ERROR_DOWNLOAD


def test_mirror_storage_error_marks_failed_without_raising(fake_cdn, temp_spy, monkeypatch, isolated_storage):
    def broken_storage(*args, **kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr(storage_service, "put_object_from_file", broken_storage)
    sanction = _sanction(attachments=[_attachment()])
    casier_id = _seed(sanction)

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary == {"stored": 0, "failed": 1, "too_large": 0}
    stored = _stored_attachment(casier_id, sanction["id"], "1299887766554433221")
    assert stored["status"] == "failed"
    assert stored["error"] == casier_attachments.MIRROR_ERROR_STORAGE
    assert temp_spy and not any(os.path.exists(path) for path in temp_spy)


def test_mirror_does_not_overwrite_a_status_changed_meanwhile(monkeypatch, tmp_path):
    sanction = _sanction(attachments=[_attachment()])
    casier_id = _seed(sanction)

    async def download_while_status_changes(url, *, max_bytes, **kwargs):
        await h.db.casiers.update_one(
            {"_id": ObjectId(casier_id)},
            {"$set": {"sanctions.0.attachments.0.status": "failed", "sanctions.0.attachments.0.error": "autre"}},
        )
        path = tmp_path / "telechargement.tmp"
        path.write_bytes(PNG)
        return str(path)

    monkeypatch.setattr(file_response_service, "download_to_temp_file", download_while_status_changes)

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary == {"stored": 0, "failed": 0, "too_large": 0}
    stored = _stored_attachment(casier_id, sanction["id"], "1299887766554433221")
    assert stored["status"] == "failed" and stored["error"] == "autre"
    assert not (tmp_path / "telechargement.tmp").exists()


def test_mirror_pending_never_raises(monkeypatch):
    empty = {"stored": 0, "failed": 0, "too_large": 0}
    assert h.run(casier_attachments.mirror_pending("../x", "y")) == empty
    assert h.run(casier_attachments.mirror_pending(str(ObjectId()), str(ObjectId()))) == empty

    class BrokenCollection:
        async def find_one(self, *args, **kwargs):
            raise RuntimeError("Mongo indisponible")

    monkeypatch.setattr(casier_attachments, "db", SimpleNamespace(casiers=BrokenCollection()))
    assert h.run(casier_attachments.mirror_pending(str(ObjectId()), str(ObjectId()))) == empty


# --------------------------------------------------------------------------------------
# Fichiers ajoutés à la main
# --------------------------------------------------------------------------------------

def test_upload_png_is_stored_with_type_from_extension(isolated_storage):
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)

    attachment = _save(casier_id, sanction["id"], FakeUpload("C:\\captures\\preuve MP.PNG", PNG))

    assert attachment["origin"] == "upload"
    assert attachment["filename"] == "preuve MP.PNG"
    assert attachment["extension"] == "png"
    assert attachment["content_type"] == "image/png"
    assert attachment["status"] == "stored" and attachment["size"] == len(PNG)
    assert attachment["uploaded_by"] == STAFF_AUTHOR and attachment["source_url"] is None
    assert len(attachment["id"]) == 24
    assert _stored_attachment(casier_id, sanction["id"], attachment["id"]) == attachment
    assert _disk_path(isolated_storage, casier_id, sanction["id"], attachment["id"], "png").read_bytes() == PNG
    assert _casier(casier_id).get("updated_at")


@pytest.mark.parametrize(
    "filename, data, content_type",
    [
        ("photo.jpg", b"\xff\xd8\xff\xe0jpeg", "image/jpeg"),
        ("photo.JPEG", b"\xff\xd8\xff\xe1jpeg", "image/jpeg"),
        ("anim.gif", b"GIF89a....", "image/gif"),
        ("vieux.gif", b"GIF87a....", "image/gif"),
        ("image.webp", b"RIFF\x10\x00\x00\x00WEBPVP8 ", "image/webp"),
        ("rapport.pdf", b"%PDF-1.7\n", "application/pdf"),
        ("notes.txt", "Échange en MP, captures à l'appui. 🔥".encode(), "text/plain"),
    ],
)
def test_upload_accepts_images_pdf_and_text(filename, data, content_type):
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)

    attachment = _save(casier_id, sanction["id"], FakeUpload(filename, data))

    assert attachment["content_type"] == content_type


@pytest.mark.parametrize("filename", ["page.html", "logo.svg", "sans-extension", "script.png.exe", "photo.bmp"])
def test_upload_rejects_formats_outside_the_list(filename):
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)

    error = _http_error(_save, casier_id, sanction["id"], FakeUpload(filename, PNG))

    assert (error.status_code, error.detail) == (422, "Format non autorisé (images, PDF ou TXT).")
    assert _stored_sanction(casier_id, sanction["id"])["attachments"] == []


@pytest.mark.parametrize(
    "filename, data",
    [
        ("capture.png", b"<html><script>alert(1)</script></html>"),
        ("capture.jpg", PNG),
        ("image.webp", b"RIFF\x10\x00\x00\x00WAVEfmt "),
        ("rapport.pdf", b"<svg onload=alert(1)>"),
        ("notes.txt", b"texte\x00binaire"),
        ("notes.txt", b"\xff\xfe\x00t\x00e"),
        ("notes.txt", "accentué".encode()[:-1]),
    ],
)
def test_upload_rejects_content_not_matching_extension(filename, data, isolated_storage):
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)

    error = _http_error(_save, casier_id, sanction["id"], FakeUpload(filename, data))

    assert (error.status_code, error.detail) == (422, "Le contenu du fichier ne correspond pas à son extension.")
    assert _stored_sanction(casier_id, sanction["id"])["attachments"] == []
    assert not (isolated_storage / "iris").exists()


def test_upload_empty_file_is_rejected():
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)

    error = _http_error(_save, casier_id, sanction["id"], FakeUpload("vide.txt", b""))

    assert (error.status_code, error.detail) == (422, "Le fichier est vide.")


def test_upload_too_large_interrupts_the_stream(monkeypatch, isolated_storage):
    monkeypatch.setattr(config, "CASIER_UPLOAD_MAX_BYTES", 2 * 1024 * 1024)
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)
    megabyte = b"\x00" * (1024 * 1024)
    upload = FakeUpload("gros.png", generator=iter([PNG] + [megabyte] * 20))

    error = _http_error(_save, casier_id, sanction["id"], upload)

    assert (error.status_code, error.detail) == (413, "Fichier trop volumineux (max 2 Mo).")
    assert upload.reads == 3  # 32 o + 1 Mo + 1 Mo : lecture arrêtée dès le dépassement
    assert _stored_sanction(casier_id, sanction["id"])["attachments"] == []
    assert not (isolated_storage / "iris").exists()


def test_upload_default_limit_message_follows_config():
    assert config.CASIER_UPLOAD_MAX_BYTES == 10 * 1024 * 1024
    assert casier_attachments._too_large_error(config.CASIER_UPLOAD_MAX_BYTES) == "Fichier trop volumineux (max 10 Mo)."


def test_upload_limit_of_ten_active_files():
    full = _sanction(source=False, attachments=[_upload_attachment() for _ in range(5)]
                     + [_attachment(f"12998877665544332{index:02d}") for index in range(5)])
    room = _sanction(source=False, attachments=[_upload_attachment() for _ in range(9)]
                     + [_upload_attachment(deleted_at=_iso(datetime.now(timezone.utc))) for _ in range(3)])
    casier_id = _seed(full, room)

    error = _http_error(_save, casier_id, full["id"], FakeUpload("onzieme.png", PNG))
    assert (error.status_code, error.detail) == (409, "Limite de 10 fichiers atteinte pour cette sanction.")
    assert len(_stored_sanction(casier_id, full["id"])["attachments"]) == 10

    _save(casier_id, room["id"], FakeUpload("dixieme.png", PNG))
    assert len(_stored_sanction(casier_id, room["id"])["attachments"]) == 13


def test_upload_on_legacy_sanction_without_attachments_key():
    sanction = _sanction(source=False)
    del sanction["attachments"]
    casier_id = _seed(sanction)

    attachment = _save(casier_id, sanction["id"], FakeUpload("preuve.png", PNG))

    assert _stored_sanction(casier_id, sanction["id"])["attachments"] == [attachment]


def test_upload_unknown_sanction_is_404():
    casier_id = _seed(_sanction())

    error = _http_error(_save, casier_id, str(ObjectId()), FakeUpload("preuve.png", PNG))

    assert (error.status_code, error.detail) == (404, "Sanction introuvable.")


def test_upload_storage_failure_is_500_and_nothing_recorded(monkeypatch):
    def broken_storage(*args, **kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr(storage_service, "put_object_from_file", broken_storage)
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)

    error = _http_error(_save, casier_id, sanction["id"], FakeUpload("preuve.png", PNG))

    assert (error.status_code, error.detail) == (500, "Enregistrement du fichier impossible.")
    assert _stored_sanction(casier_id, sanction["id"])["attachments"] == []


# --------------------------------------------------------------------------------------
# Retrait d'un fichier ajouté à la main
# --------------------------------------------------------------------------------------

def _delete(casier_id, sanction_id, attachment_id, viewer, deleted_by=STAFF_AUTHOR):
    return h.run(casier_attachments.delete_upload(_casier(casier_id), sanction_id, attachment_id, viewer, deleted_by))


def test_delete_upload_by_author_soft_deletes_and_erases_file(isolated_storage):
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)
    attachment = _save(casier_id, sanction["id"], FakeUpload("preuve.png", PNG))
    disk = _disk_path(isolated_storage, casier_id, sanction["id"], attachment["id"], "png")
    assert disk.is_file()

    removed = _delete(casier_id, sanction["id"], attachment["id"], VIEWER_STAFF)

    assert removed["deleted_at"] and removed["deleted_by"] == STAFF_AUTHOR
    stored = _stored_attachment(casier_id, sanction["id"], attachment["id"])
    assert stored["deleted_at"] == removed["deleted_at"]
    assert not disk.exists()
    assert casier_attachments.attachments_out(_stored_sanction(casier_id, sanction["id"]), casier_id,
                                              VIEWER_STAFF) == []
    error = _http_error(_delete, casier_id, sanction["id"], attachment["id"], VIEWER_STAFF)
    assert (error.status_code, error.detail) == (404, "Fichier introuvable.")


def test_delete_upload_rights(isolated_storage):
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)
    attachment = _save(casier_id, sanction["id"], FakeUpload("preuve.png", PNG))

    error = _http_error(_delete, casier_id, sanction["id"], attachment["id"], VIEWER_OTHER)
    assert (error.status_code, error.detail) == (403, "Seul l'auteur ou un Responsable peut retirer ce fichier.")
    assert _disk_path(isolated_storage, casier_id, sanction["id"], attachment["id"], "png").is_file()
    assert _stored_attachment(casier_id, sanction["id"], attachment["id"])["deleted_at"] is None

    removed = _delete(casier_id, sanction["id"], attachment["id"], VIEWER_RESPONSABLE)
    assert removed["deleted_at"]


def test_delete_discord_file_or_unknown_file_is_refused():
    discord_file = _attachment(status="stored")
    sanction = _sanction(attachments=[discord_file])
    casier_id = _seed(sanction)

    error = _http_error(_delete, casier_id, sanction["id"], discord_file["id"], VIEWER_RESPONSABLE)
    assert error.status_code == 409
    assert error.detail == "Les fichiers importés depuis Discord ne peuvent pas être retirés."

    error = _http_error(_delete, casier_id, sanction["id"], str(ObjectId()), VIEWER_RESPONSABLE)
    assert (error.status_code, error.detail) == (404, "Fichier introuvable.")

    error = _http_error(_delete, casier_id, str(ObjectId()), discord_file["id"], VIEWER_RESPONSABLE)
    assert (error.status_code, error.detail) == (404, "Sanction introuvable.")


# --------------------------------------------------------------------------------------
# « Récupérer les fichiers du log »
# --------------------------------------------------------------------------------------

def _log_raw_message(attachments: list[dict], *, moderator_id: str = MOD_ID, extra_components=()) -> dict:
    return {
        "id": str(LOG_MESSAGE_ID),
        "flags": 32768,
        "content": "",
        "embeds": [],
        "attachments": attachments,
        "components": [{
            "type": 17,
            "components": [
                {"type": 10, "content": (
                    f"<@{moderator_id}> a mit <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&3>.\n"
                    "### Raison de l'ajout : \n```Propos humiliants répétés.```"
                )},
                *extra_components,
            ],
        }],
    }


def _raw_attachment(attachment_id: str, filename: str = "capture.png", size: int = 1024) -> dict:
    return {
        "id": attachment_id,
        "filename": filename,
        "size": size,
        "url": _cdn_url(attachment_id, filename) + "&frais=1",
        "proxy_url": _cdn_url(attachment_id, filename, host="media.discordapp.net"),
        "content_type": "image/png" if filename.endswith(".png") else "text/plain",
    }


@pytest.fixture
def log_fetch(monkeypatch):
    state = {"calls": [], "message": _log_raw_message([]), "error": None}

    async def fake_fetch(channel_id, message_id):
        state["calls"].append((channel_id, message_id))
        if state["error"] is not None:
            raise state["error"]
        return state["message"]

    monkeypatch.setattr(moderation_bot, "fetch_raw_message", fake_fetch)
    return state


@pytest.fixture
def author_resolver():
    calls = []

    async def resolve(mod_id):
        calls.append(mod_id)
        return {"id": mod_id, "username": "ines", "display_name": "Inès (staff)"}

    resolve.calls = calls
    return resolve


def _resync(casier_id, sanction_id, resolve_author):
    casier = _casier(casier_id)
    sanction = next(s for s in casier["sanctions"] if s["id"] == sanction_id)
    return h.run(casier_attachments.resync_from_discord(casier, sanction, resolve_author=resolve_author))


def test_resync_adds_missing_files_requeues_failed_and_fills_moderator(
    log_fetch, author_resolver, fake_cdn, isolated_storage
):
    failed = _attachment("1299887766554433222", filename="journal.txt", status="failed",
                         error="Fichier inaccessible sur Discord.", source_url=_cdn_url("1299887766554433222", "x"))
    stored = _attachment("1299887766554433223", status="stored")
    too_large = _attachment("1299887766554433224", filename="video.mp4", status="too_large",
                            error="Fichier trop volumineux (max 25 Mo).")
    sanction = _sanction(attachments=[failed, stored, too_large])
    casier_id = _seed(sanction)
    _put_on_disk(casier_id, sanction["id"], stored["id"], "png")
    log_fetch["message"] = _log_raw_message([
        _raw_attachment("1299887766554433221"),
        _raw_attachment("1299887766554433222", "journal.txt"),
        _raw_attachment("1299887766554433223"),
        _raw_attachment("1299887766554433224", "video.mp4"),
    ])

    stats = _resync(casier_id, sanction["id"], author_resolver)

    assert stats == {"files_found": 4, "files_queued": 2, "moderator_filled": True}
    assert log_fetch["calls"] == [(MUTE_CHANNEL_ID, LOG_MESSAGE_ID)]
    assert author_resolver.calls == [MOD_ID]
    stored_sanction = _stored_sanction(casier_id, sanction["id"])
    assert stored_sanction["moderator"] == {"id": MOD_ID, "username": "ines", "display_name": "Inès (staff)"}
    assert [a["id"] for a in stored_sanction["attachments"]] == [
        "1299887766554433222", "1299887766554433223", "1299887766554433224", "1299887766554433221",
    ]
    requeued = stored_sanction["attachments"][0]
    assert requeued["status"] == "pending" and requeued["error"] is None
    assert requeued["source_url"].endswith("&frais=1") and requeued["queued_at"]
    assert stored_sanction["attachments"][1] == stored
    assert stored_sanction["attachments"][2] == too_large
    added = stored_sanction["attachments"][3]
    assert added["status"] == "pending" and added["origin"] == "discord" and added["size"] == 1024

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary == {"stored": 2, "failed": 0, "too_large": 0}
    statuses = {a["status"] for a in _stored_sanction(casier_id, sanction["id"])["attachments"]}
    assert statuses == {"stored", "too_large"}


def test_resync_on_legacy_sanction_without_attachments_key(log_fetch, author_resolver):
    sanction = _sanction(moderator={"id": MOD_ID, "username": None, "display_name": None})
    del sanction["attachments"]
    del sanction["moderator"]
    sanction["moderator"] = {"id": "900000000000000002", "username": "lou", "display_name": "Lou"}
    casier_id = _seed(sanction)
    log_fetch["message"] = _log_raw_message([_raw_attachment("1299887766554433221")])

    stats = _resync(casier_id, sanction["id"], author_resolver)

    assert stats == {"files_found": 1, "files_queued": 1, "moderator_filled": False}
    assert author_resolver.calls == []
    stored_sanction = _stored_sanction(casier_id, sanction["id"])
    assert [a["id"] for a in stored_sanction["attachments"]] == ["1299887766554433221"]
    assert stored_sanction["moderator"]["display_name"] == "Lou"


def test_resync_moderator_falls_back_to_id_when_name_is_unknown(log_fetch):
    sanction = _sanction()
    casier_id = _seed(sanction)

    async def failing_resolver(mod_id):
        raise HTTPException(status_code=502, detail="Discord indisponible.")

    stats = _resync(casier_id, sanction["id"], failing_resolver)

    assert stats == {"files_found": 0, "files_queued": 0, "moderator_filled": True}
    assert _stored_sanction(casier_id, sanction["id"])["moderator"] == {
        "id": MOD_ID, "username": None, "display_name": None,
    }


def test_resync_without_anything_new_writes_nothing(log_fetch, author_resolver):
    stored = _attachment(status="stored")
    sanction = _sanction(attachments=[stored], moderator=dict(STAFF_AUTHOR))
    casier_id = _seed(sanction)
    _put_on_disk(casier_id, sanction["id"], stored["id"], "png")
    log_fetch["message"] = _log_raw_message([_raw_attachment(stored["id"])])
    before = _casier(casier_id)

    stats = _resync(casier_id, sanction["id"], author_resolver)

    assert stats == {"files_found": 1, "files_queued": 0, "moderator_filled": False}
    assert _casier(casier_id) == before


def test_resync_requeues_stored_file_missing_from_disk(log_fetch, author_resolver):
    lost = _attachment(status="stored")
    sanction = _sanction(attachments=[lost], moderator=dict(STAFF_AUTHOR))
    casier_id = _seed(sanction)
    log_fetch["message"] = _log_raw_message([_raw_attachment(lost["id"])])

    stats = _resync(casier_id, sanction["id"], author_resolver)

    assert stats["files_queued"] == 1
    assert _stored_attachment(casier_id, sanction["id"], lost["id"])["status"] == "pending"


def test_resync_keeps_at_most_ten_discord_files(log_fetch, author_resolver):
    existing = [_attachment(f"12998877665544332{index:02d}", status="stored") for index in range(10)]
    sanction = _sanction(attachments=existing, moderator=dict(STAFF_AUTHOR))
    casier_id = _seed(sanction)
    for attachment in existing:
        _put_on_disk(casier_id, sanction["id"], attachment["id"], "png")
    log_fetch["message"] = _log_raw_message([_raw_attachment("1299887766554433299")])

    stats = _resync(casier_id, sanction["id"], author_resolver)

    assert stats["files_queued"] == 0
    assert len(_stored_sanction(casier_id, sanction["id"])["attachments"]) == 10


def test_resync_manual_sanction_is_409_without_fetch(log_fetch, author_resolver):
    sanction = _sanction(source=False)
    casier_id = _seed(sanction)

    error = _http_error(_resync, casier_id, sanction["id"], author_resolver)

    assert (error.status_code, error.detail) == (409, "Cette sanction n'a pas de message de log Discord.")
    assert log_fetch["calls"] == []


def test_resync_while_copy_in_progress_is_409(log_fetch, author_resolver):
    recent = _attachment(created_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=2)))
    sanction = _sanction(attachments=[recent])
    casier_id = _seed(sanction)

    error = _http_error(_resync, casier_id, sanction["id"], author_resolver)

    assert (error.status_code, error.detail) == (409, "Une copie des fichiers est déjà en cours.")
    assert log_fetch["calls"] == []


def test_resync_takes_over_a_stale_pending_copy(log_fetch, author_resolver):
    stale = _attachment(created_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=20)))
    sanction = _sanction(attachments=[stale], moderator=dict(STAFF_AUTHOR))
    casier_id = _seed(sanction)
    log_fetch["message"] = _log_raw_message([_raw_attachment(stale["id"])])

    stats = _resync(casier_id, sanction["id"], author_resolver)

    assert stats == {"files_found": 1, "files_queued": 1, "moderator_filled": False}
    requeued = _stored_attachment(casier_id, sanction["id"], stale["id"])
    assert requeued["status"] == "pending" and requeued["source_url"].endswith("&frais=1")
    # Remis en file à l'instant : une nouvelle demande est refusée.
    error = _http_error(_resync, casier_id, sanction["id"], author_resolver)
    assert error.status_code == 409


@pytest.mark.parametrize("failure", ["none", "raise"])
def test_resync_unreadable_log_is_502_without_any_write(log_fetch, author_resolver, failure):
    sanction = _sanction(attachments=[_attachment(status="failed")])
    casier_id = _seed(sanction)
    if failure == "none":
        log_fetch["message"] = None
    else:
        log_fetch["error"] = httpx.ConnectError("Discord injoignable")
    before = _casier(casier_id)

    error = _http_error(_resync, casier_id, sanction["id"], author_resolver)

    assert (error.status_code, error.detail) == (502, "Message de log introuvable ou inaccessible sur Discord.")
    assert _casier(casier_id) == before
    assert author_resolver.calls == []


# --------------------------------------------------------------------------------------
# Lecture : AttachmentOut et service des copies locales
# --------------------------------------------------------------------------------------

def test_to_out_never_exposes_internal_fields():
    casier_id, sanction_id = str(ObjectId()), str(ObjectId())
    stored = _attachment(status="stored", size=1696)

    out = casier_attachments.to_out(stored, casier_id, sanction_id, VIEWER_RESPONSABLE)

    assert out == {
        "id": stored["id"],
        "origin": "discord",
        "filename": "capture.png",
        "content_type": "image/png",
        "size": 1696,
        "status": "stored",
        "error": None,
        "inline": True,
        "download_url": f"/moderation/casiers/{casier_id}/sanctions/{sanction_id}/attachments/{stored['id']}",
        "created_at": stored["created_at"],
        "uploaded_by": None,
        "can_delete": False,
    }

    pending = casier_attachments.to_out(_attachment(), casier_id, sanction_id, VIEWER_STAFF)
    assert pending["download_url"] is None and pending["inline"] is False
    svg = casier_attachments.to_out(
        _attachment(filename="logo.svg", content_type="image/svg+xml", status="stored"), casier_id, sanction_id, None
    )
    assert svg["inline"] is False
    spoofed = casier_attachments.to_out(
        _attachment(filename="photo.png", content_type="text/html", status="stored"), casier_id, sanction_id, None
    )
    assert spoofed["inline"] is False


def test_attachments_out_hides_deleted_files_and_computes_can_delete():
    upload = _upload_attachment()
    deleted = _upload_attachment(deleted_at=_iso(datetime.now(timezone.utc)), deleted_by=STAFF_AUTHOR)
    discord_file = _attachment(status="stored")
    sanction = _sanction(attachments=[discord_file, upload, deleted, "pas un objet"])
    casier_id = str(ObjectId())

    def can_delete_for(viewer):
        return [a["can_delete"] for a in casier_attachments.attachments_out(sanction, casier_id, viewer)]

    assert [a["id"] for a in casier_attachments.attachments_out(sanction, casier_id, None)] == [
        discord_file["id"], upload["id"],
    ]
    assert can_delete_for(VIEWER_STAFF) == [False, True]
    assert can_delete_for(VIEWER_OTHER) == [False, False]
    assert can_delete_for(VIEWER_RESPONSABLE) == [False, True]
    assert can_delete_for(None) == [False, False]


@pytest.fixture
def file_client():
    casier_id, sanction_id = str(ObjectId()), str(ObjectId())
    files = {
        "png": _attachment("1299887766554433221", status="stored"),
        "svg": _attachment("1299887766554433222", filename="logo.svg", content_type="image/svg+xml",
                           status="stored"),
        "html": _attachment("1299887766554433223", filename="page.html", content_type="text/html",
                            status="stored"),
        "pdf": _upload_attachment(filename="rapport.pdf", extension="pdf", content_type="application/pdf"),
        "pending": _attachment("1299887766554433224"),
        "missing": _attachment("1299887766554433225", status="stored"),
        "deleted": _upload_attachment(deleted_at=_iso(datetime.now(timezone.utc))),
    }
    for name, attachment in files.items():
        if name not in {"pending", "missing"}:
            _put_on_disk(casier_id, sanction_id, attachment["id"], attachment["extension"],
                         PNG if name == "png" else b"<svg onload=alert(1)>")

    app = FastAPI()

    @app.get("/f/{name}")
    def serve(name: str, request: Request, download: bool = False):
        return casier_attachments.stream_attachment(request, casier_id, sanction_id, files.get(name),
                                                    download=download)

    return TestClient(app, raise_server_exceptions=False)


def test_stream_attachment_inline_only_for_raster_images(file_client):
    png = file_client.get("/f/png")
    assert png.status_code == 200 and png.content == PNG
    assert png.headers["content-type"] == "image/png"
    assert png.headers["content-disposition"].startswith("inline;")
    assert png.headers["x-content-type-options"] == "nosniff"
    assert png.headers["cache-control"] == "private, no-store"

    for name in ("svg", "html", "pdf"):
        response = file_client.get(f"/f/{name}")
        assert response.status_code == 200, name
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["content-disposition"].startswith("attachment;")

    forced = file_client.get("/f/png", params={"download": 1})
    assert forced.headers["content-disposition"].startswith("attachment;")


def test_stream_attachment_errors_and_range(file_client):
    for name, detail in (("pending", "Copie locale indisponible pour ce fichier."),
                         ("missing", "Copie locale indisponible pour ce fichier."),
                         ("deleted", "Fichier introuvable."),
                         ("inconnu", "Fichier introuvable.")):
        response = file_client.get(f"/f/{name}")
        assert (response.status_code, response.json()["detail"]) == (404, detail), name

    partial = file_client.get("/f/png", headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206 and partial.content == PNG[:4]


# --------------------------------------------------------------------------------------
# Bot : logs de mute, durée, modérateur réel, fichiers
# --------------------------------------------------------------------------------------

def _mute_log(*, duration_line: str = "### Durée : \n```1h30```", attachments=None, verb="a mit") -> dict:
    return {
        "flags": 32768,
        "content": "",
        "embeds": [],
        "attachments": attachments if attachments is not None else [_raw_attachment("1299887766554433221")],
        "components": [{
            "type": 17,
            "components": [
                {"type": 10, "content": (
                    f"<@{MOD_ID}> {verb} <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&3>.\n"
                    f"{duration_line}\n"
                    "### Raison de l'ajout : \n```Propos humiliants pendant 2 jours en vocal.```"
                )},
            ],
        }],
    }


def _bot_message(message_id: int = LOG_MESSAGE_ID, **extra):
    message = SimpleNamespace(
        id=message_id,
        channel=SimpleNamespace(id=MUTE_CHANNEL_ID),
        author=SimpleNamespace(id=OASIS_BOT_ID, bot=True),
        webhook_id=None,
        application_id=None,
        guild=None,
        jump_url=f"https://discord.com/channels/1/{MUTE_CHANNEL_ID}/{message_id}",
    )
    for key, value in extra.items():
        setattr(message, key, value)
    return message


@pytest.fixture
def bot_spy(monkeypatch):
    state = {"fetch": [], "sanctions": [], "raw": _mute_log()}

    async def fake_fetch(channel_id, message_id):
        state["fetch"].append((channel_id, message_id))
        return state["raw"]

    async def fake_add_sanction(**kwargs):
        state["sanctions"].append(kwargs)

    monkeypatch.setattr(moderation_bot, "fetch_raw_message", fake_fetch)
    monkeypatch.setattr(moderation_bot, "add_sanction", fake_add_sanction)
    monkeypatch.setattr(moderation_bot, "DISCORD_MODERATION_CHANNEL_TYPES", {MUTE_CHANNEL_ID: "mute"})
    monkeypatch.setattr(moderation_bot, "MODERATION_LOG_AUTHOR_IDS", set(), raising=False)
    return state


def _handle(message) -> None:
    h.run(moderation_bot.handle_sanction_log_message(message))


def test_mute_channel_is_accepted_in_config():
    assert config.parse_moderation_channels("mute:600000000000000005") == {600000000000000005: "mute"}
    assert config.parse_moderation_channels(" MUTE : 600000000000000005 ,kick:1") == {
        600000000000000005: "mute", 1: "kick",
    }
    assert "mute" in config.VALID_SANCTION_TYPES


def test_mute_log_records_duration_files_and_moderator(bot_spy):
    before = datetime.now(timezone.utc)
    _handle(_bot_message())

    assert len(bot_spy["sanctions"]) == 1
    call = bot_spy["sanctions"][0]
    assert call["discord_id"] == MEMBER_ID
    assert call["sanction_type"] == "mute"
    assert call["reason"] == "Propos humiliants pendant 2 jours en vocal."
    assert call["created_by"] is None
    assert call["dedupe_message_id"] == str(LOG_MESSAGE_ID)
    assert call["source"]["message_id"] == str(LOG_MESSAGE_ID)
    # La durée écrite dans le motif (« 2 jours ») n'est jamais prise.
    assert (call["duration"], call["duration_seconds"]) == ("1 h 30", 5400)
    expires_at = datetime.fromisoformat(call["expires_at"])
    assert before + timedelta(seconds=5399) <= expires_at <= datetime.now(timezone.utc) + timedelta(seconds=5401)
    assert call["moderator"] == {"id": MOD_ID, "username": None, "display_name": None}
    [attachment] = call["attachments"]
    assert attachment["id"] == "1299887766554433221"
    assert attachment["status"] == "pending" and attachment["origin"] == "discord"
    assert attachment["source_url"].startswith("https://cdn.discordapp.com/attachments/")


def test_mute_log_duration_uses_message_date(bot_spy):
    created = datetime(2026, 10, 25, 17, 0, tzinfo=timezone.utc)
    bot_spy["raw"] = _mute_log(duration_line="Durée : 1 h", attachments=[])

    _handle(_bot_message(created_at=created))

    call = bot_spy["sanctions"][0]
    assert (call["duration"], call["duration_seconds"]) == ("1 h", 3600)
    assert call["expires_at"] == "2026-10-25T18:00:00+00:00"
    assert call["attachments"] is None


def test_log_without_duration_or_files_still_passes_keywords_only(bot_spy):
    bot_spy["raw"] = _mute_log(duration_line="", attachments=[])

    _handle(_bot_message())

    call = bot_spy["sanctions"][0]
    assert (call["duration"], call["duration_seconds"], call["expires_at"]) == (None, None, None)
    assert call["attachments"] is None


def test_absurd_discord_timestamp_does_not_block_recording(bot_spy):
    bot_spy["raw"] = _mute_log(duration_line="Fin du mute : <t:999999999999:R>")

    _handle(_bot_message())

    assert len(bot_spy["sanctions"]) == 1
    assert bot_spy["sanctions"][0]["sanction_type"] == "mute"


def test_removal_log_is_still_ignored(bot_spy):
    bot_spy["raw"] = _mute_log(verb="a retiré")

    _handle(_bot_message())

    assert bot_spy["sanctions"] == []


class FakeMember(SimpleNamespace):
    pass


class FakeGuild:
    def __init__(self, cached=(), fetched=(), fetch_error=None):
        self.cached = {int(member.id): member for member in cached}
        self.fetched = {int(member.id): member for member in fetched}
        self.fetch_error = fetch_error
        self.fetch_calls: list[int] = []

    def get_member(self, member_id: int):
        return self.cached.get(member_id)

    async def fetch_member(self, member_id: int):
        self.fetch_calls.append(member_id)
        if member_id in self.fetched:
            return self.fetched[member_id]
        if self.fetch_error is not None:
            raise self.fetch_error
        raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Membre inconnu")


def _member(member_id: str, name: str, display_name: str) -> FakeMember:
    return FakeMember(id=int(member_id), name=name, display_name=display_name, display_avatar=None)


def test_moderator_name_is_resolved_from_guild_cache(bot_spy):
    guild = FakeGuild(cached=[_member(MOD_ID, "ines", "Inès (staff)"), _member(MEMBER_ID, "mathis.b", "Mathis")])

    _handle(_bot_message(guild=guild))

    call = bot_spy["sanctions"][0]
    assert call["moderator"] == {"id": MOD_ID, "username": "ines", "display_name": "Inès (staff)"}
    assert call["snapshot"]["display_name"] == "Mathis"
    assert guild.fetch_calls == []


def test_moderator_name_is_fetched_when_not_cached(bot_spy):
    guild = FakeGuild(cached=[_member(MEMBER_ID, "mathis.b", "Mathis")],
                      fetched=[_member(MOD_ID, "ines", "Inès (staff)")])

    _handle(_bot_message(guild=guild))

    assert bot_spy["sanctions"][0]["moderator"]["display_name"] == "Inès (staff)"
    assert guild.fetch_calls == [int(MOD_ID)]


@pytest.mark.parametrize(
    "fetch_error",
    [
        None,  # discord.NotFound
        asyncio.TimeoutError(),
        discord.HTTPException(SimpleNamespace(status=503, reason="Service Unavailable"), "indisponible"),
    ],
)
def test_moderator_unknown_to_guild_keeps_the_id(bot_spy, fetch_error):
    guild = FakeGuild(cached=[_member(MEMBER_ID, "mathis.b", "Mathis")], fetch_error=fetch_error)

    _handle(_bot_message(guild=guild))

    assert bot_spy["sanctions"][0]["moderator"] == {"id": MOD_ID, "username": None, "display_name": None}


def _boom(*args, **kwargs):
    raise RuntimeError("analyse impossible")


async def _async_boom(*args, **kwargs):
    raise RuntimeError("analyse impossible")


@pytest.mark.parametrize(
    "target, attribute, replacement, expected",
    [
        (casier_log_parser, "extract_duration", _boom,
         {"duration": None, "duration_seconds": None, "expires_at": None}),
        (casier_log_parser, "extract_message_files", _boom, {"attachments": None}),
        (casier_log_parser, "extract_moderator_id", _boom, {"moderator": None}),
        (moderation_bot, "resolve_log_moderator", _async_boom, {"moderator": None}),
    ],
)
def test_each_extraction_failure_never_blocks_recording(
    bot_spy, monkeypatch, target, attribute, replacement, expected
):
    monkeypatch.setattr(target, attribute, replacement)

    _handle(_bot_message())

    assert len(bot_spy["sanctions"]) == 1
    call = bot_spy["sanctions"][0]
    for key, value in expected.items():
        assert call[key] == value, key
    assert call["sanction_type"] == "mute" and call["reason"]
    if attribute != "extract_duration":
        assert call["duration_seconds"] == 5400
    if attribute != "extract_message_files":
        assert len(call["attachments"]) == 1


def _refonte_add_sanction_available() -> bool:
    parameters = inspect.signature(casier_service.add_sanction).parameters
    expected = {"sanction_id", "duration_seconds", "expires_at", "attachments", "moderator"}
    return expected <= set(parameters) and "mute" in getattr(casier_service, "SANCTION_TYPES", set())


@pytest.mark.skipif(not _refonte_add_sanction_available(),
                    reason="casier_service.add_sanction de la refonte pas encore disponible")
def test_bot_with_real_add_sanction_stores_then_mirrors_files(monkeypatch, mirror_calls, fake_cdn, isolated_storage):
    raw = _mute_log()

    async def fake_fetch(channel_id, message_id):
        return raw

    monkeypatch.setattr(moderation_bot, "fetch_raw_message", fake_fetch)
    monkeypatch.setattr(moderation_bot, "DISCORD_MODERATION_CHANNEL_TYPES", {MUTE_CHANNEL_ID: "mute"})
    monkeypatch.setattr(moderation_bot, "MODERATION_LOG_AUTHOR_IDS", set(), raising=False)

    _handle(_bot_message())
    _handle(_bot_message())  # même message retraité (reconnexion) : aucun doublon

    casier = h.run(h.db.casiers.find_one({"discord_id": MEMBER_ID}))
    [sanction] = casier["sanctions"]
    casier_id = str(casier["_id"])
    assert casier_attachments.HEX_ID_PATTERN.fullmatch(sanction["id"])
    assert sanction["type"] == "mute" and sanction["duration_seconds"] == 5400
    assert sanction["moderator"] == {"id": MOD_ID, "username": None, "display_name": None}
    assert [a["status"] for a in sanction["attachments"]] == ["pending"]
    assert mirror_calls == [(casier_id, sanction["id"])]

    summary = h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    assert summary == {"stored": 1, "failed": 0, "too_large": 0}
    stored = _stored_attachment(casier_id, sanction["id"], "1299887766554433221")
    assert stored["status"] == "stored"
    assert _disk_path(isolated_storage, casier_id, sanction["id"], stored["id"], "png").read_bytes() == PNG
