"""Tests de sécurité hors-ligne : fichiers, archives de salons, ressources animateur, en-têtes HTTP."""
import security_harness as h  # noqa: I001  (doit être importé en premier)

import mimetypes
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server
from routers import animateur, channel_archives
from services import file_response_service, storage_service
from services.discord_service import DiscordService


BACKEND_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_ID = "11111111-2222-3333-4444-555555555555"
MESSAGE_ID = "500000000000000001"
CHANNEL_ID = "600000000000000001"
FRONT_ORIGIN = "https://iris.loasis.app"


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    h.reset_db()
    h.reset_discord()
    root = tmp_path / "storage"
    monkeypatch.setattr(storage_service, "STORAGE_ROOT", root)
    return root


def _grant(role: str, extra_role: str) -> None:
    h.fake_discord.member_roles[h.USER_IDS[role]].append(h.ROLE_IDS[extra_role])


def _identity(role: str) -> dict:
    return {"id": h.USER_IDS[role], "username": f"test-{role}", "display_name": f"Test {role}", "avatar_url": None}


# --------------------------------------------------------------------------------------
# Archives de salons : pièces jointes servies depuis le domaine de l'API (H3)
# --------------------------------------------------------------------------------------
ATTACHMENTS = [
    # (id, filename, content_type déclaré, contenu)
    ("700000000000000001", "evil.html", "text/html; charset=utf-8", b"<script>alert(document.cookie)</script>"),
    ("700000000000000002", "evil.svg", "image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>"),
    ("700000000000000003", "photo.png", "image/png", b"\x89PNG\r\n\x1a\nfake-png"),
    ("700000000000000004", "fake.png", "text/html", b"<script>alert(1)</script>"),
    ("700000000000000005", "rapport.pdf", "application/pdf", b"%PDF-1.4"),
    ("700000000000000006", "photo.JPG", "image/jpeg", b"\xff\xd8\xffjpeg"),
    ("700000000000000007", "notes.txt", "text/plain", b"texte"),
    ("700000000000000008", "évaluation réunion.webp", None, b"RIFFwebp"),
    ("700000000000000009", "page.png", "text/html", b"<html></html>"),
    ("700000000000000010", "image.svg", "image/png", b"<svg/>"),
]


def _seed_archive(attachments=ATTACHMENTS, write_files=True) -> None:
    transcript_attachments = []
    for attachment_id, filename, content_type, content in attachments:
        extension = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        if write_files:
            path = storage_service.channel_archive_attachment_path(ARCHIVE_ID, MESSAGE_ID, attachment_id, extension)
            storage_service.put_object_from_bytes(path, content, "application/octet-stream")
        transcript_attachments.append({
            "id": attachment_id,
            "filename": filename,
            "url": f"https://cdn.discordapp.com/attachments/1/{attachment_id}/{filename}",
            "local_url": f"/channel-archives/{ARCHIVE_ID}/messages/{MESSAGE_ID}/attachments/{attachment_id}",
            "content_type": content_type,
        })

    archive = {
        "id": ARCHIVE_ID,
        "title": "#salon",
        "channel_id": CHANNEL_ID,
        "channel_name": "salon",
        "status": "archived",
        "phase": "done",
        "message_count": 1,
        "local_attachment_count": len(transcript_attachments),
        "files_total": len(transcript_attachments),
        "error_message": None,
        "transcript": [{
            "id": MESSAGE_ID,
            "content": "pièces jointes",
            "timestamp": "2026-10-01T10:00:00+00:00",
            "author": {"id": "1", "username": "membre", "display_name": "membre", "avatar_url": None, "is_bot": False},
            "attachments": transcript_attachments,
            "embeds": [],
            "components": [],
        }],
        "created_by": h.USER_IDS["responsable"],
        "created_at": "2026-10-01T10:00:00+00:00",
        "updated_at": "2026-10-01T10:00:00+00:00",
        "last_synced_at": "2026-10-01T10:00:00+00:00",
    }
    h.run(h.db.channel_archives.insert_one(archive))


def _attachment_url(attachment_id: str) -> str:
    return f"/api/channel-archives/{ARCHIVE_ID}/messages/{MESSAGE_ID}/attachments/{attachment_id}"


@pytest.mark.parametrize(
    "attachment_id",
    [
        "700000000000000001",  # .html
        "700000000000000002",  # .svg
        "700000000000000004",  # .png annoncé text/html
        "700000000000000005",  # .pdf
        "700000000000000007",  # .txt
        "700000000000000009",  # .png annoncé text/html
        "700000000000000010",  # .svg annoncé image/png
    ],
)
def test_archived_active_content_is_downloaded_not_rendered(attachment_id):
    _seed_archive()
    client = h.make_client(channel_archives.router)

    response = client.get(_attachment_url(attachment_id), cookies=h.session_cookies("responsable"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    content_type = response.headers["content-type"]
    assert "html" not in content_type and "svg" not in content_type


@pytest.mark.parametrize(
    "attachment_id, expected_type",
    [
        ("700000000000000003", "image/png"),
        ("700000000000000006", "image/jpeg"),
        ("700000000000000008", "image/webp"),  # type absent : déduit de l'extension
    ],
)
def test_archived_raster_images_still_display_inline(attachment_id, expected_type):
    _seed_archive()
    client = h.make_client(channel_archives.router)

    response = client.get(_attachment_url(attachment_id), cookies=h.session_cookies("responsable"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == expected_type
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["x-content-type-options"] == "nosniff"
    expected = next(content for item_id, _, _, content in ATTACHMENTS if item_id == attachment_id)
    assert response.content == expected


def test_archived_attachment_non_latin_filename_and_range():
    _seed_archive()
    client = h.make_client(channel_archives.router)
    cookies = h.session_cookies("responsable")

    response = client.get(_attachment_url("700000000000000008"), cookies=cookies)
    assert response.status_code == 200
    assert quote("évaluation réunion.webp", safe="") in response.headers["content-disposition"]

    partial = client.get(_attachment_url("700000000000000003"), cookies=cookies, headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206
    assert partial.content == b"\x89PNG"


def test_archived_attachment_requires_responsable():
    _seed_archive()
    client = h.make_client(channel_archives.router)
    for role in ("helper", "staff", "animateur", "admin"):
        response = client.get(_attachment_url("700000000000000003"), cookies=h.session_cookies(role))
        assert response.status_code == 403, role
    assert client.get(_attachment_url("700000000000000003")).status_code == 401


def test_archived_attachment_legacy_extension_is_still_served(isolated_storage):
    # Avant l'assainissement, l'extension brute (ici "2_final") servait de suffixe sur le disque.
    attachment = ("700000000000000011", "rapport_v1.2_final", "text/html", b"ancien fichier")
    _seed_archive([attachment], write_files=False)
    legacy = isolated_storage / f"iris/channel_archives/{ARCHIVE_ID}/{MESSAGE_ID}/700000000000000011.2_final"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"ancien fichier")
    client = h.make_client(channel_archives.router)

    response = client.get(_attachment_url("700000000000000011"), cookies=h.session_cookies("responsable"))

    assert response.status_code == 200, response.text
    assert response.content == b"ancien fichier"
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_archived_attachment_missing_file_is_404():
    _seed_archive(write_files=False)
    client = h.make_client(channel_archives.router)
    response = client.get(_attachment_url("700000000000000003"), cookies=h.session_cookies("responsable"))
    assert response.status_code == 404


# --------------------------------------------------------------------------------------
# Mirroring des pièces jointes : hôtes autorisés, taille plafonnée en flux, extension
# --------------------------------------------------------------------------------------
class FakeCdn:
    def __init__(self, chunks=(b"contenu",)):
        self.requests: list[str] = []
        self.chunks = list(chunks)
        self.yielded = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))

        async def body():
            for chunk in self.chunks:
                self.yielded += 1
                yield chunk

        return httpx.Response(200, content=body())


@pytest.fixture
def fake_cdn(monkeypatch):
    cdn = FakeCdn()
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(cdn.handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(channel_archives.httpx, "AsyncClient", client_factory)
    return cdn


def _mirror(attachment: dict):
    return h.run(channel_archives._mirror_attachment(ARCHIVE_ID, MESSAGE_ID, attachment))


def test_mirror_discord_cdn_attachment(fake_cdn, isolated_storage):
    for host in ("cdn.discordapp.com", "media.discordapp.net"):
        result = _mirror({
            "id": "800000000000000001",
            "filename": "photo.PNG",
            "url": f"https://{host}/attachments/1/2/photo.PNG",
            "content_type": "image/png",
        })
        assert result.local_url == f"/channel-archives/{ARCHIVE_ID}/messages/{MESSAGE_ID}/attachments/800000000000000001"
        stored = isolated_storage / f"iris/channel_archives/{ARCHIVE_ID}/{MESSAGE_ID}/800000000000000001.png"
        assert stored.read_bytes() == b"contenu"
    assert len(fake_cdn.requests) == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/photo.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://cdn.discordapp.com/attachments/1/2/photo.png",  # pas de HTTPS
        "https://cdn.discordapp.com.evil.example/photo.png",
        "https://user@evil.example/cdn.discordapp.com/photo.png",
        "file:///etc/passwd",
    ],
)
def test_mirror_refuses_non_discord_hosts(fake_cdn, url):
    result = _mirror({"id": "800000000000000002", "filename": "photo.png", "url": url, "content_type": "image/png"})
    assert result.local_url is None
    assert result.url == url
    assert fake_cdn.requests == []


def test_mirror_aborts_oversized_download_while_streaming(fake_cdn, monkeypatch, isolated_storage):
    monkeypatch.setattr(channel_archives, "MAX_ATTACHMENT_SIZE", 10)
    fake_cdn.chunks = [b"x" * 8, b"x" * 8, b"x" * 8, b"x" * 8, b"x" * 8]
    monkeypatch.setattr(channel_archives, "DOWNLOAD_CHUNK_SIZE", 8)

    result = _mirror({
        "id": "800000000000000003",
        "filename": "gros.zip",
        "url": "https://cdn.discordapp.com/attachments/1/2/gros.zip",
        "content_type": "application/zip",
    })

    assert result.local_url is None
    assert fake_cdn.yielded < len(fake_cdn.chunks)  # lecture interrompue avant la fin
    assert not (isolated_storage / "iris").exists() or not any((isolated_storage / "iris").rglob("*.zip"))


def test_mirror_sanitizes_extension_from_discord_filename(fake_cdn, isolated_storage):
    result = _mirror({
        "id": "800000000000000004",
        "filename": "x.y/../../../../escape",
        "url": "https://cdn.discordapp.com/attachments/1/2/x",
        "content_type": None,
    })
    assert result.local_url is not None
    stored = isolated_storage / f"iris/channel_archives/{ARCHIVE_ID}/{MESSAGE_ID}/800000000000000004.bin"
    assert stored.read_bytes() == b"contenu"
    assert [path.name for path in isolated_storage.rglob("*") if path.is_file()] == ["800000000000000004.bin"]


def test_import_end_to_end_mirrors_and_serves_safely(fake_cdn):
    h.fake_discord.add_channel(CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="salon")
    h.fake_discord.messages[CHANNEL_ID] = [{
        "id": MESSAGE_ID,
        "content": "voici",
        "timestamp": "2026-10-01T10:00:00+00:00",
        "author": {"id": "1", "username": "membre"},
        "attachments": [
            {"id": "900000000000000001", "filename": "page.html", "url": "https://cdn.discordapp.com/a/page.html",
             "content_type": "text/html"},
            {"id": "900000000000000002", "filename": "photo.png", "url": "https://cdn.discordapp.com/a/photo.png",
             "content_type": "image/png"},
        ],
    }]
    h.run(h.db.channel_archives.insert_one({"id": ARCHIVE_ID, "channel_id": CHANNEL_ID}))

    h.run(channel_archives._run_import(ARCHIVE_ID, CHANNEL_ID))

    archive = h.run(h.db.channel_archives.find_one({"id": ARCHIVE_ID}, {"_id": 0}))
    assert archive["status"] == "archived", archive.get("error_message")
    assert archive["local_attachment_count"] == 2
    client = h.make_client(channel_archives.router)
    cookies = h.session_cookies("responsable")
    html = client.get(
        f"/api/channel-archives/{ARCHIVE_ID}/messages/{MESSAGE_ID}/attachments/900000000000000001", cookies=cookies
    )
    assert html.status_code == 200
    assert html.headers["content-type"] == "application/octet-stream"
    assert html.headers["content-disposition"].startswith("attachment;")
    image = client.get(
        f"/api/channel-archives/{ARCHIVE_ID}/messages/{MESSAGE_ID}/attachments/900000000000000002", cookies=cookies
    )
    assert image.headers["content-type"] == "image/png"
    assert image.headers["content-disposition"].startswith("inline;")


# --------------------------------------------------------------------------------------
# Messages d'erreur d'import (L7b)
# --------------------------------------------------------------------------------------
def test_import_failure_hides_internal_exception_text(monkeypatch):
    async def broken_history(self, channel_id, **kwargs):
        raise RuntimeError("mongodb://admin:motdepasse@10.0.0.5/ /app/storage/secret")
        yield  # pragma: no cover

    monkeypatch.setattr(DiscordService, "iter_channel_history", broken_history)
    h.run(h.db.channel_archives.insert_one({"id": ARCHIVE_ID, "channel_id": CHANNEL_ID}))

    h.run(channel_archives._run_import(ARCHIVE_ID, CHANNEL_ID))

    archive = h.run(h.db.channel_archives.find_one({"id": ARCHIVE_ID}, {"_id": 0}))
    assert archive["status"] == "failed"
    assert "motdepasse" not in archive["error_message"]
    assert "/app/storage" not in archive["error_message"]
    assert archive["error_message"] == "Erreur inattendue pendant l'import du salon."


def test_import_failure_keeps_http_exception_detail(monkeypatch):
    async def missing_channel(self, channel_id, **kwargs):
        raise HTTPException(status_code=404, detail="Salon Discord introuvable.")
        yield  # pragma: no cover

    monkeypatch.setattr(DiscordService, "iter_channel_history", missing_channel)
    h.run(h.db.channel_archives.insert_one({"id": ARCHIVE_ID, "channel_id": CHANNEL_ID}))

    h.run(channel_archives._run_import(ARCHIVE_ID, CHANNEL_ID))

    archive = h.run(h.db.channel_archives.find_one({"id": ARCHIVE_ID}, {"_id": 0}))
    assert archive["status"] == "failed"
    assert archive["error_message"] == "Salon Discord introuvable."


# --------------------------------------------------------------------------------------
# Service de stockage : confinement des chemins et extensions
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad_path", ["../evil.txt", "iris/../../evil.txt", "ABSOLU", "", "."])
def test_storage_refuses_paths_outside_root(isolated_storage, tmp_path, bad_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"x")
    if bad_path == "ABSOLU":
        bad_path = str(tmp_path / "evil.txt")

    with pytest.raises(ValueError):
        storage_service.put_object_from_bytes(bad_path, b"x", "text/plain")
    with pytest.raises(ValueError):
        storage_service.put_object_from_file(bad_path, str(source), "text/plain")
    with pytest.raises(FileNotFoundError):
        storage_service.get_object(bad_path)
    assert not (tmp_path / "evil.txt").exists()


def test_storage_get_object_refuses_traversal_to_existing_file(isolated_storage, tmp_path):
    (tmp_path / "secret.txt").write_bytes(b"secret")
    isolated_storage.mkdir(parents=True, exist_ok=True)
    with pytest.raises(FileNotFoundError):
        storage_service.get_object("../secret.txt")


def test_storage_refuses_symlink_escape(isolated_storage, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (isolated_storage / "iris").mkdir(parents=True)
    (isolated_storage / "iris" / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        storage_service.put_object_from_bytes("iris/link/evil.txt", b"x", "text/plain")
    assert not (outside / "evil.txt").exists()


def test_storage_legitimate_round_trip(isolated_storage):
    result = storage_service.put_object_from_bytes("iris/resources/abc.pdf", b"%PDF", "application/pdf")
    assert result == {"path": "iris/resources/abc.pdf", "size": 4}
    assert storage_service.get_object("iris/resources/abc.pdf") == (b"%PDF", "application/octet-stream")


@pytest.mark.parametrize(
    "extension, expected",
    [
        ("PDF", "pdf"),
        ("docx", "docx"),
        ("7z", "7z"),
        ("../../etc", "bin"),
        ("ph/p", "bin"),
        ("", "bin"),
        ("2_final", "bin"),
        ("averyveryverylongext", "bin"),
        ("été", "bin"),
    ],
)
def test_storage_paths_sanitize_extension(extension, expected):
    assert storage_service.resource_path("rid", extension) == f"iris/resources/rid.{expected}"
    assert storage_service.channel_archive_attachment_path("a", "m", "f", extension) == (
        f"iris/channel_archives/a/m/f.{expected}"
    )


def test_storage_root_env_override_and_default(tmp_path):
    code = "from services import storage_service as s; print(s.STORAGE_ROOT)"
    env = {key: value for key, value in os.environ.items() if key != "IRIS_STORAGE_ROOT"}
    default = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert default.stdout.strip() == "/app/storage", default.stderr

    env["IRIS_STORAGE_ROOT"] = str(tmp_path)
    override = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert override.stdout.strip() == str(tmp_path), override.stderr


def test_file_response_reads_storage_root_at_call_time(isolated_storage):
    storage_service.put_object_from_bytes("iris/x.txt", b"ok", "text/plain")
    assert file_response_service._resolve_file("iris/x.txt") == (isolated_storage / "iris/x.txt").resolve()


@pytest.mark.parametrize(
    "declared, expected",
    [
        ("text/html", "application/octet-stream"),
        ("TEXT/HTML; charset=utf-8", "application/octet-stream"),
        ("image/svg+xml", "application/octet-stream"),
        ("application/xhtml+xml", "application/octet-stream"),
        ("text/xml", "application/octet-stream"),
        ("application/javascript", "application/octet-stream"),
        ("text/javascript", "application/octet-stream"),
        (None, "application/octet-stream"),
        ("n'importe quoi", "application/octet-stream"),
        ("application/pdf", "application/pdf"),
        ("image/png", "image/png"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_safe_content_type(declared, expected):
    assert file_response_service.safe_content_type(declared) == expected


# --------------------------------------------------------------------------------------
# Projets animateur : uploads, téléchargements et droits (M6, L1)
# --------------------------------------------------------------------------------------
PROJECT_ID = "proj-1"
TASK_ID = "task-1"


def _seed_project(members=("animateur",), creator="staff") -> None:
    h.run(h.db.projects.insert_one({
        "id": PROJECT_ID,
        "title": "Projet",
        "description": "",
        "content_markdown": "",
        "status": "en_cours",
        "start_date": "2026-10-01",
        "end_date": None,
        "members": [_identity(role) for role in members],
        "created_by": _identity(creator),
        "created_at": "2026-10-01T10:00:00+00:00",
        "updated_at": "2026-10-01T10:00:00+00:00",
    }))


def _seed_task(assignee="animateur") -> None:
    h.run(h.db.project_tasks.insert_one({
        "id": TASK_ID,
        "project_id": PROJECT_ID,
        "title": "Tâche",
        "description": "",
        "due_date": "2026-11-01",
        "assignee": _identity(assignee),
        "status": "a_faire",
        "submission_note": "",
        "created_at": "2026-10-01T10:00:00+00:00",
        "updated_at": "2026-10-01T10:00:00+00:00",
    }))


def _animateur_client():
    return h.make_client(animateur.router, animateur.tasks_router, animateur.resources_router)


def _stored_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()] if root.exists() else []


def test_upload_resource_too_large_returns_413(monkeypatch, isolated_storage):
    monkeypatch.setattr(animateur, "MAX_UPLOAD_SIZE", 2 * 1024 * 1024)
    _seed_project()
    client = _animateur_client()

    response = client.post(
        f"/api/animateur/projects/{PROJECT_ID}/resources",
        data={"title": "gros"},
        files={"file": ("gros.zip", b"x" * (3 * 1024 * 1024), "application/zip")},
        cookies=h.session_cookies("staff"),
    )

    assert response.status_code == 413
    assert _stored_files(isolated_storage) == []
    assert h.run(h.db.project_resources.count_documents({})) == 0


def test_submit_task_too_large_returns_413(monkeypatch, isolated_storage):
    monkeypatch.setattr(animateur, "MAX_UPLOAD_SIZE", 1024 * 1024)
    _grant("animateur", "staff")
    _seed_project()
    _seed_task()
    client = _animateur_client()

    response = client.put(
        f"/api/animateur/tasks/{TASK_ID}/submit",
        data={"submission_content": "rendu"},
        files={"file": ("gros.bin", b"x" * (2 * 1024 * 1024), "application/octet-stream")},
        cookies=h.session_cookies("animateur"),
    )

    assert response.status_code == 413
    assert _stored_files(isolated_storage) == []
    task = h.run(h.db.project_tasks.find_one({"id": TASK_ID}))
    assert task["status"] == "a_faire"


@pytest.mark.parametrize(
    "raw, expected",
    [(None, 100), ("250", 250), ("abc", 100), ("0", 100), ("-5", 100)],
)
def test_upload_limit_env_var(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("ANIMATEUR_MAX_UPLOAD_MB", raising=False)
    else:
        monkeypatch.setenv("ANIMATEUR_MAX_UPLOAD_MB", raw)
    assert animateur._upload_limit_mb() == expected


def test_default_upload_limit_is_100_mb():
    if "ANIMATEUR_MAX_UPLOAD_MB" not in os.environ:
        assert animateur.MAX_UPLOAD_SIZE == 100 * 1024 * 1024


@pytest.mark.parametrize(
    "filename, client_type, expected_ext, expected_type",
    [
        ("evil.html", "text/html", "html", "application/octet-stream"),
        ("evil.svg", "image/svg+xml", "svg", "application/octet-stream"),
        ("evil.js", "text/javascript", "js", "application/octet-stream"),
        ("faux.pdf", "text/html", "pdf", "application/pdf"),
        ("evil.<script>", "text/html", "bin", "application/octet-stream"),
        ("sans_extension", "text/html", "bin", "application/octet-stream"),
        ("Compte.DOCX", "application/octet-stream", "docx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("Budget.xlsx", "application/octet-stream", "xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("affiche.webp", "image/webp", "webp", "image/webp"),
        ("Rapport.PDF", "text/html", "pdf", "application/pdf"),
    ],
)
@pytest.mark.parametrize("builtin_table_only", [False, True], ids=["table-systeme", "table-integree"])
def test_upload_resource_stores_safe_extension_and_type(monkeypatch, isolated_storage, builtin_table_only, filename,
                                                        client_type, expected_ext, expected_type):
    if builtin_table_only:
        # Image python:3.11-slim sans /etc/mime.types : seule la table intégrée de Python est connue.
        monkeypatch.setattr(animateur, "mimetypes", mimetypes.MimeTypes())
    _seed_project()
    client = _animateur_client()

    response = client.post(
        f"/api/animateur/projects/{PROJECT_ID}/resources",
        data={"title": "doc"},
        files={"file": (filename, b"contenu", client_type)},
        cookies=h.session_cookies("staff"),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == expected_type
    assert body["storage_path"].endswith(f".{expected_ext}")
    assert body["original_filename"] == filename
    assert body["size"] == len(b"contenu")
    assert (isolated_storage / body["storage_path"]).read_bytes() == b"contenu"


def test_upload_resource_unknown_project_is_404(isolated_storage):
    client = _animateur_client()
    response = client.post(
        "/api/animateur/projects/inexistant/resources",
        data={"title": "doc"},
        files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
        cookies=h.session_cookies("staff"),
    )
    assert response.status_code == 404
    assert _stored_files(isolated_storage) == []


def test_resource_download_streams_attachment_with_non_latin_name(isolated_storage):
    _grant("animateur", "staff")
    _seed_project(members=("animateur",))
    client = _animateur_client()
    filename = "compte-rendu-réunion.pdf"
    uploaded = client.post(
        f"/api/animateur/projects/{PROJECT_ID}/resources",
        data={"title": "CR"},
        files={"file": (filename, b"%PDF-1.4 contenu", "application/pdf")},
        cookies=h.session_cookies("animateur"),
    ).json()

    response = client.get(f"/api/animateur/resources/{uploaded['id']}/download", cookies=h.session_cookies("animateur"))

    assert response.status_code == 200, response.text
    assert response.content == b"%PDF-1.4 contenu"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_legacy_html_resource_is_downloaded_as_octet_stream(isolated_storage):
    _seed_project(members=("animateur",))
    storage_service.put_object_from_bytes("iris/project-resources/old.html", b"<script>1</script>", "text/html")
    h.run(h.db.project_resources.insert_one({
        "id": "res-old", "project_id": PROJECT_ID, "title": "ancien", "original_filename": "page.html",
        "content_type": "text/html", "size": 18, "storage_path": "iris/project-resources/old.html",
        "uploaded_by": _identity("animateur"), "created_at": "2026-10-01T10:00:00+00:00",
    }))
    client = _animateur_client()

    response = client.get("/api/animateur/resources/res-old/download", cookies=h.session_cookies("animateur"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_resource_download_restricted_to_members_and_responsables(isolated_storage):
    other = "400000000000000077"
    h.fake_discord.member_roles[other] = [h.ROLE_IDS["animateur"]]
    _seed_project(members=("animateur",))
    storage_service.put_object_from_bytes("iris/project-resources/r.pdf", b"%PDF", "application/pdf")
    h.run(h.db.project_resources.insert_one({
        "id": "res-1", "project_id": PROJECT_ID, "title": "doc", "original_filename": "doc.pdf",
        "content_type": "application/pdf", "size": 4, "storage_path": "iris/project-resources/r.pdf",
        "uploaded_by": _identity("animateur"), "created_at": "2026-10-01T10:00:00+00:00",
    }))
    client = _animateur_client()
    from models.ticket import AuthenticatedHelper
    from services import auth_service

    outsider = {auth_service.SESSION_COOKIE: auth_service.create_session(
        AuthenticatedHelper(id=other, username="autre", global_name="Autre")
    )}

    assert client.get("/api/animateur/resources/res-1/download", cookies=outsider).status_code == 403
    assert client.get("/api/animateur/resources/res-1/download", cookies=h.session_cookies("animateur")).status_code == 200
    assert client.get("/api/animateur/resources/res-1/download",
                      cookies=h.session_cookies("responsable")).status_code == 200
    # Ni animateur ni responsable : refusé comme avant.
    assert client.get("/api/animateur/resources/res-1/download", cookies=h.session_cookies("staff")).status_code == 403


def test_submit_task_only_by_assignee_or_responsable(isolated_storage):
    _grant("animateur", "staff")
    _grant("responsable", "staff")
    _seed_project(members=("animateur",))
    _seed_task(assignee="animateur")
    client = _animateur_client()

    other_staff = client.put(
        f"/api/animateur/tasks/{TASK_ID}/submit",
        data={"submission_content": "écrasé"},
        files={"file": ("pirate.html", b"<script>1</script>", "text/html")},
        cookies=h.session_cookies("staff"),
    )
    assert other_staff.status_code == 403
    task = h.run(h.db.project_tasks.find_one({"id": TASK_ID}))
    assert task["status"] == "a_faire"
    assert task.get("submission_file") is None
    assert _stored_files(isolated_storage) == []

    assignee = client.put(
        f"/api/animateur/tasks/{TASK_ID}/submit",
        data={"submission_content": "mon rendu"},
        files={"file": ("rendu final é.pdf", b"%PDF rendu", "application/pdf")},
        cookies=h.session_cookies("animateur"),
    )
    assert assignee.status_code == 200, assignee.text
    body = assignee.json()
    assert body["status"] == "rendu"
    assert body["submission_file"]["content_type"] == "application/pdf"
    assert body["submission_file"]["size"] == len(b"%PDF rendu")

    download = client.get(f"/api/animateur/tasks/{TASK_ID}/submission/download", cookies=h.session_cookies("staff"))
    assert download.status_code == 200
    assert download.content == b"%PDF rendu"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert quote("rendu final é.pdf", safe="") in download.headers["content-disposition"]

    responsable = client.put(
        f"/api/animateur/tasks/{TASK_ID}/submit",
        data={"submission_content": "rendu corrigé"},
        cookies=h.session_cookies("responsable"),
    )
    assert responsable.status_code == 200, responsable.text


def test_submit_task_html_file_is_stored_as_octet_stream(isolated_storage):
    _grant("animateur", "staff")
    _seed_project(members=("animateur",))
    _seed_task(assignee="animateur")
    client = _animateur_client()

    response = client.put(
        f"/api/animateur/tasks/{TASK_ID}/submit",
        data={"submission_content": ""},
        files={"file": ("rendu.html", b"<script>1</script>", "text/html")},
        cookies=h.session_cookies("animateur"),
    )

    assert response.status_code == 200
    assert response.json()["submission_file"]["content_type"] == "application/octet-stream"
    download = client.get(f"/api/animateur/tasks/{TASK_ID}/submission/download", cookies=h.session_cookies("staff"))
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["content-disposition"].startswith("attachment;")


def _put_project(client, cookies):
    return client.put(
        f"/api/animateur/projects/{PROJECT_ID}",
        json={"title": "Nouveau titre", "description": "d", "content_markdown": "c", "end_date": None},
        cookies=cookies,
    )


def test_update_project_restricted_to_members_creator_and_responsables():
    other = "400000000000000078"
    h.fake_discord.member_roles[other] = [h.ROLE_IDS["animateur"]]
    _grant("staff", "animateur")  # créateur du projet
    _seed_project(members=("animateur",), creator="staff")
    client = _animateur_client()
    from models.ticket import AuthenticatedHelper
    from services import auth_service

    outsider = {auth_service.SESSION_COOKIE: auth_service.create_session(
        AuthenticatedHelper(id=other, username="autre", global_name="Autre")
    )}

    assert _put_project(client, outsider).status_code == 403
    assert h.run(h.db.projects.find_one({"id": PROJECT_ID}))["title"] == "Projet"

    assert _put_project(client, h.session_cookies("animateur")).status_code == 200
    assert _put_project(client, h.session_cookies("staff")).status_code == 200
    assert _put_project(client, h.session_cookies("responsable")).status_code == 200
    assert h.run(h.db.projects.find_one({"id": PROJECT_ID}))["title"] == "Nouveau titre"


def test_update_unknown_project_is_still_404():
    client = _animateur_client()
    response = client.put(
        "/api/animateur/projects/inexistant",
        json={"title": "x", "description": "", "content_markdown": "", "end_date": None},
        cookies=h.session_cookies("animateur"),
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------------------
# En-têtes de sécurité globaux (H3b)
# --------------------------------------------------------------------------------------
EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; sandbox",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def _assert_security_headers(response):
    for name, value in EXPECTED_HEADERS.items():
        assert response.headers.get(name) == value, name
        assert len(response.headers.get_list(name)) == 1, name
    assert "cross-origin-resource-policy" not in response.headers


def test_security_headers_on_api_responses():
    client = h.make_client(include_app_middlewares=True)
    _assert_security_headers(client.get("/api/"))
    _assert_security_headers(client.get("/api/channel-archives"))  # 401
    _assert_security_headers(client.get("/api/route-inexistante"))  # 404


def test_security_headers_on_streamed_file_without_duplicates():
    _seed_archive()
    client = h.make_client(include_app_middlewares=True)
    response = client.get(_attachment_url("700000000000000003"), cookies=h.session_cookies("responsable"))
    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n\x1a\nfake-png"
    _assert_security_headers(response)


def test_cors_still_works_with_security_headers():
    client = h.make_client(include_app_middlewares=True)
    preflight = client.options(
        "/api/channel-archives",
        headers={
            "Origin": FRONT_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == FRONT_ORIGIN
    assert preflight.headers["access-control-allow-credentials"] == "true"

    _seed_archive()
    response = client.get(
        _attachment_url("700000000000000003"), headers={"Origin": FRONT_ORIGIN}, cookies=h.session_cookies("responsable")
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONT_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    _assert_security_headers(response)


def test_docs_page_keeps_working_without_csp():
    client = h.make_client(include_app_middlewares=True)
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_security_middleware_keeps_sse_streaming_intact():
    app = FastAPI()

    @app.get("/stream")
    async def stream():
        async def events():
            for index in range(3):
                yield f"data: morceau {index}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    app.add_middleware(server.SecurityHeadersMiddleware)
    client = TestClient(app)

    with client.stream("GET", "/stream") as response:
        chunks = list(response.iter_text())

    assert "".join(chunks) == "data: morceau 0\n\ndata: morceau 1\n\ndata: morceau 2\n\n"
    assert response.headers["content-type"].startswith("text/event-stream")
    _assert_security_headers(response)


def test_security_middleware_does_not_break_websocket():
    client = h.make_client(include_app_middlewares=True)
    # Jeton invalide : la route ferme proprement la connexion (code 4403) au lieu de planter.
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/api/activity/ws?t=invalide&instance_id=x") as websocket:
            websocket.receive_json()
    assert closed.value.code == 4403


def test_security_middleware_does_not_override_existing_headers():
    app = FastAPI()

    @app.get("/custom")
    async def custom():
        from fastapi.responses import Response

        return Response("ok", headers={"Referrer-Policy": "same-origin"})

    app.add_middleware(server.SecurityHeadersMiddleware)
    response = TestClient(app).get("/custom")
    assert response.headers.get_list("referrer-policy") == ["same-origin"]
    assert response.headers["x-frame-options"] == "DENY"
