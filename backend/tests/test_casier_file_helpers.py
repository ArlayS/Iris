"""Tests hors-ligne des helpers de fichiers partagés (file_response_service) et des alias de channel_archives."""
import security_harness as h  # noqa: I001  (doit être importé en premier)

import asyncio
import os
import tempfile

import httpx
import pytest

from routers import channel_archives
from services import file_response_service, storage_service
from services.file_response_service import (
    ALLOWED_DISCORD_CDN_HOSTS,
    INLINE_IMAGE_TYPES,
    DownloadTooLarge,
    attachment_extension,
    download_to_temp_file,
    inline_image_type,
    is_discord_cdn_url,
)


CDN_URL = "https://cdn.discordapp.com/attachments/1/2/fichier.bin"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Fichiers temporaires et stockage confinés au dossier du test, pour vérifier le nettoyage."""
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
    monkeypatch.setattr(storage_service, "STORAGE_ROOT", tmp_path / "storage")
    return temp_dir


def _leftovers(temp_dir) -> list[str]:
    return sorted(path.name for path in temp_dir.iterdir())


class FakeCdn:
    def __init__(self, chunks=(b"contenu",), status_code=200, fail_after=None, error=None):
        self.requests: list[str] = []
        self.client_kwargs: list[dict] = []
        self.chunks = list(chunks)
        self.status_code = status_code
        self.fail_after = fail_after
        self.error = error or RuntimeError("connexion coupée")
        self.yielded = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))

        async def body():
            for index, chunk in enumerate(self.chunks):
                if self.fail_after is not None and index >= self.fail_after:
                    raise self.error
                self.yielded += 1
                yield chunk

        return httpx.Response(self.status_code, content=body())


@pytest.fixture
def fake_cdn(monkeypatch):
    cdn = FakeCdn()
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        cdn.client_kwargs.append(dict(kwargs))
        kwargs["transport"] = httpx.MockTransport(cdn.handler)
        return real_client(*args, **kwargs)

    # Remplacé sur le module partagé `httpx`, comme le font les tests des archives de salons.
    monkeypatch.setattr(file_response_service.httpx, "AsyncClient", client_factory)
    return cdn


# --------------------------------------------------------------------------------------
# Constantes et fonctions pures
# --------------------------------------------------------------------------------------
def test_shared_constants():
    assert ALLOWED_DISCORD_CDN_HOSTS == {"cdn.discordapp.com", "media.discordapp.net"}
    assert INLINE_IMAGE_TYPES == {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    assert issubclass(DownloadTooLarge, ValueError)


def test_channel_archives_aliases_point_to_shared_helpers():
    assert channel_archives.ALLOWED_ATTACHMENT_HOSTS is file_response_service.ALLOWED_DISCORD_CDN_HOSTS
    assert channel_archives.INLINE_IMAGE_TYPES is file_response_service.INLINE_IMAGE_TYPES
    assert channel_archives._attachment_extension is file_response_service.attachment_extension
    assert channel_archives._is_discord_cdn_url is file_response_service.is_discord_cdn_url
    assert channel_archives._inline_image_type is file_response_service.inline_image_type
    # Noms historiques conservés (tests et appelants existants).
    assert channel_archives.httpx is httpx
    assert channel_archives.MAX_ATTACHMENT_SIZE == 200 * 1024 * 1024
    assert channel_archives.DOWNLOAD_CHUNK_SIZE == 1024 * 1024
    assert asyncio.iscoroutinefunction(channel_archives._download_to_temp_file)
    assert asyncio.iscoroutinefunction(channel_archives._mirror_attachment)
    assert asyncio.iscoroutinefunction(channel_archives._run_import)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("photo.PNG", "PNG"),
        ("archive.tar.gz", "gz"),
        ("sans-extension", "bin"),
        ("", "bin"),
        ("x.y/../../../../escape", "/escape"),  # brut : assaini par storage_service
        (None, "bin"),
        (42, "bin"),
    ],
)
def test_attachment_extension(filename, expected):
    assert attachment_extension(filename) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.discordapp.com/attachments/1/2/photo.png",
        "https://media.discordapp.net/attachments/1/2/photo.png?ex=1&is=2&hm=3",
        "https://CDN.DiscordApp.com/attachments/1/2/photo.png",
        "https://cdn.discordapp.com:443/attachments/1/2/photo.png",
    ],
)
def test_is_discord_cdn_url_accepts_discord_cdn(url):
    assert is_discord_cdn_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/photo.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://cdn.discordapp.com/attachments/1/2/photo.png",  # pas de HTTPS
        "https://cdn.discordapp.com.evil.example/photo.png",
        "https://user@evil.example/cdn.discordapp.com/photo.png",
        "https://discordapp.com/attachments/1/2/photo.png",
        "https://images-ext-1.discordapp.net/external/abc/photo.png",
        "file:///etc/passwd",
        "attachment://photo.png",
        "https://[::1/photo.png",  # URL invalide : ValueError rattrapée
        "",
        None,
        12345,
        {"url": "https://cdn.discordapp.com/attachments/1/2/photo.png"},
    ],
)
def test_is_discord_cdn_url_rejects_everything_else(url):
    assert is_discord_cdn_url(url) is False


@pytest.mark.parametrize(
    ("content_type", "filename", "expected"),
    [
        ("image/png", "photo.png", "image/png"),
        ("image/png; charset=binary", "photo.PNG", "image/png"),
        ("image/jpeg", "photo.JPG", "image/jpeg"),
        ("image/jpg", "photo.jpg", "image/jpeg"),
        ("image/pjpeg", "photo.jpeg", "image/jpeg"),
        (None, "évaluation réunion.webp", "image/webp"),
        ("", "anim.gif", "image/gif"),
        ("text/html", "fake.png", None),
        ("image/svg+xml", "image.png", None),
        ("image/png", "image.svg", None),
        ("application/pdf", "rapport.pdf", None),
        ("text/plain", "notes.txt", None),
        ("image/png", "sans-extension", None),
        ("image/bmp", "photo.png", None),
    ],
)
def test_inline_image_type(content_type, filename, expected):
    assert inline_image_type(content_type, filename) == expected


# --------------------------------------------------------------------------------------
# download_to_temp_file
# --------------------------------------------------------------------------------------
def test_download_writes_temp_file(fake_cdn, isolated_dirs):
    fake_cdn.chunks = [b"premier-", b"second"]

    path = h.run(download_to_temp_file(CDN_URL, max_bytes=1024))

    try:
        assert os.path.dirname(path) == str(isolated_dirs)
        with open(path, "rb") as handle:
            assert handle.read() == b"premier-second"
    finally:
        os.unlink(path)
    assert fake_cdn.requests == [CDN_URL]
    assert fake_cdn.client_kwargs[0]["timeout"] == 60.0


def test_download_forwards_timeout(fake_cdn):
    path = h.run(download_to_temp_file(CDN_URL, max_bytes=1024, timeout=5.0))
    os.unlink(path)
    assert fake_cdn.client_kwargs[0]["timeout"] == 5.0


def test_download_accepts_exactly_max_bytes(fake_cdn):
    fake_cdn.chunks = [b"x" * 4, b"x" * 4]

    path = h.run(download_to_temp_file(CDN_URL, max_bytes=8, chunk_size=4))

    try:
        assert os.path.getsize(path) == 8
    finally:
        os.unlink(path)


def test_download_aborts_while_streaming_when_too_large(fake_cdn, isolated_dirs):
    fake_cdn.chunks = [b"x" * 8] * 5

    with pytest.raises(DownloadTooLarge) as error:
        h.run(download_to_temp_file(CDN_URL, max_bytes=10, chunk_size=8))

    assert isinstance(error.value, ValueError)
    assert str(error.value) == "Pièce jointe trop volumineuse pour être copiée localement."
    assert fake_cdn.yielded < len(fake_cdn.chunks)  # lecture interrompue avant la fin
    assert _leftovers(isolated_dirs) == []


def test_download_http_error_leaves_no_file(fake_cdn, isolated_dirs):
    fake_cdn.status_code = 404

    with pytest.raises(httpx.HTTPStatusError):
        h.run(download_to_temp_file(CDN_URL, max_bytes=1024))

    assert _leftovers(isolated_dirs) == []


def test_download_does_not_follow_redirects(fake_cdn, isolated_dirs):
    fake_cdn.status_code = 302

    with pytest.raises(httpx.HTTPStatusError):
        h.run(download_to_temp_file(CDN_URL, max_bytes=1024))

    assert fake_cdn.requests == [CDN_URL]
    assert _leftovers(isolated_dirs) == []


@pytest.mark.parametrize("error", [RuntimeError("connexion coupée"), asyncio.CancelledError()])
def test_download_removes_partial_file_on_stream_error(fake_cdn, isolated_dirs, error):
    fake_cdn.chunks = [b"debut", b"suite", b"fin"]
    fake_cdn.fail_after = 1
    fake_cdn.error = error

    with pytest.raises(type(error)):
        h.run(download_to_temp_file(CDN_URL, max_bytes=1024))

    assert fake_cdn.yielded == 1
    assert _leftovers(isolated_dirs) == []


def test_download_reads_async_client_at_call_time(monkeypatch):
    calls = []

    class RefusingClient:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("client remplacé")

    monkeypatch.setattr(httpx, "AsyncClient", RefusingClient)

    with pytest.raises(RuntimeError, match="client remplacé"):
        h.run(download_to_temp_file(CDN_URL, max_bytes=1024))
    assert calls == [{"timeout": 60.0}]


# --------------------------------------------------------------------------------------
# channel_archives : enveloppe et comportement inchangés
# --------------------------------------------------------------------------------------
def test_channel_archives_wrapper_reads_constants_at_call_time(monkeypatch):
    received = []

    async def fake_download(url, *, max_bytes, chunk_size=1024 * 1024, timeout=60.0):
        received.append((url, max_bytes, chunk_size, timeout))
        return "/chemin/temporaire"

    monkeypatch.setattr(file_response_service, "download_to_temp_file", fake_download)
    monkeypatch.setattr(channel_archives, "MAX_ATTACHMENT_SIZE", 123)
    monkeypatch.setattr(channel_archives, "DOWNLOAD_CHUNK_SIZE", 7)

    assert h.run(channel_archives._download_to_temp_file(CDN_URL)) == "/chemin/temporaire"
    assert received == [(CDN_URL, 123, 7, 60.0)]


def test_channel_archives_patch_on_its_httpx_reaches_shared_helper(monkeypatch, isolated_dirs):
    cdn = FakeCdn(chunks=[b"x" * 8] * 4)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(cdn.handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(channel_archives.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(channel_archives, "MAX_ATTACHMENT_SIZE", 10)
    monkeypatch.setattr(channel_archives, "DOWNLOAD_CHUNK_SIZE", 8)

    with pytest.raises(DownloadTooLarge):
        h.run(channel_archives._download_to_temp_file(CDN_URL))
    assert cdn.requests == [CDN_URL]
    assert cdn.yielded < len(cdn.chunks)
    assert _leftovers(isolated_dirs) == []


def test_mirror_attachment_still_swallows_download_too_large(monkeypatch):
    async def too_large(url, *, max_bytes, chunk_size=1024 * 1024, timeout=60.0):
        raise DownloadTooLarge("Pièce jointe trop volumineuse pour être copiée localement.")

    monkeypatch.setattr(file_response_service, "download_to_temp_file", too_large)
    url = "https://cdn.discordapp.com/attachments/1/2/gros.zip"

    result = h.run(channel_archives._mirror_attachment(
        "11111111-2222-3333-4444-555555555555",
        "500000000000000001",
        {"id": "800000000000000003", "filename": "gros.zip", "url": url, "content_type": "application/zip"},
    ))

    assert result.local_url is None
    assert result.url == url
