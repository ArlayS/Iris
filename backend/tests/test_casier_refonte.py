"""Tests hors-ligne de l'API des casiers après la refonte (routers/casier.py, services/casier_search.py).

Aucun appel réseau : Discord (httpx du router), le CDN et MongoDB sont simulés, le stockage est isolé.
Lancer depuis backend/ : python -m pytest -q -p no:cacheprovider -n 0 tests/test_casier_refonte.py
"""
import security_harness as h  # noqa: I001  (doit être importé en premier)

import itertools
import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from bson import ObjectId
from fastapi import HTTPException

import config
from routers import casier
from services import (
    audit_service,
    casier_attachments,
    casier_search,
    casier_service,
    casier_text,
    file_response_service,
    moderation_bot,
    storage_service,
)

BASE = "/api/moderation/casiers"
HEX_ID = re.compile(r"[0-9a-f]{24}")

ELOISE = "1153638521786093580"
INES_MEMBER = "1153638521786093581"
MATHIS = "1153638521786093582"
NOVA = "1153638521786093583"
PIXEL = "1153638521786093584"
OTHER = "1153638521786093585"

INES = {"id": h.USER_IDS["staff"], "username": "staff", "display_name": "Inès (staff)"}
LOU = {"id": h.USER_IDS["responsable"], "username": "lou", "display_name": "Lou"}
BOT = dict(casier_service.BOT_AUTHOR)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
CHANNEL_ID = "600000000000000004"
LOG_MESSAGE_ID = "1299887766554433200"

_snowflakes = itertools.count(1300000000000000000)


# --------------------------------------------------------------------------------------
# Banc de test
# --------------------------------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def casier_http(monkeypatch, tmp_path):
    """Base vide, stockage isolé et httpx du router remplacé : aucune requête Discord réelle."""
    h.reset_db()
    h.reset_discord()
    monkeypatch.setattr(storage_service, "STORAGE_ROOT", tmp_path / "storage")
    state = {"urls": [], "members": {}, "status": None}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            state["urls"].append(url)
            if state["status"] is not None:
                return _FakeHttpResponse(state["status"])
            member_id = url.rsplit("/", 1)[-1]
            if member_id in state["members"]:
                return _FakeHttpResponse(200, state["members"][member_id])
            return _FakeHttpResponse(404)

    monkeypatch.setattr(casier, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient, HTTPError=httpx.HTTPError))
    yield state


@pytest.fixture
def mirror_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(casier_attachments, "schedule_mirror", lambda c, s: calls.append((c, s)))
    return calls


class FakeCdn:
    def __init__(self, chunks=(PNG,)):
        self.requests: list[str] = []
        self.chunks = list(chunks)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))

        async def body():
            for chunk in self.chunks:
                yield chunk

        return httpx.Response(200, content=body())


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
def bot_key(monkeypatch):
    monkeypatch.setattr(casier, "GHOST_BOT_API_KEY", "cle-bot-de-test")
    return {"X-API-Key": "cle-bot-de-test"}


def _grant(role: str, *extra_roles: str) -> None:
    for extra in extra_roles:
        h.fake_discord.member_roles[h.USER_IDS[role]].append(h.ROLE_IDS[extra])


@pytest.fixture
def responsable():
    """Utilisateur Staff + Responsable."""
    _grant("responsable", "staff")
    return "responsable"


@pytest.fixture
def other_staff():
    """Second membre du staff (ni auteur, ni Responsable)."""
    _grant("admin", "staff")
    return "admin"


def _client(role: str | None = "staff"):
    client = h.make_client(casier.router)
    if role:
        client.cookies.update(h.session_cookies(role))
    return client


def _ago(**delta) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def _sanction(type_="avertissement", reason="Motif.", *, created_by=INES, minutes_ago=60, **extra) -> dict:
    sanction = {
        "id": str(ObjectId()),
        "type": type_,
        "reason": reason,
        "created_at": _ago(minutes=minutes_ago),
        "created_by": created_by,
        "moderator": None,
        "duration": None,
        "duration_seconds": None,
        "expires_at": None,
        "source": None,
        "attachments": [],
        "notes": [],
        "ai_flag_id": None,
    }
    sanction.update(extra)
    return sanction


def _note(content, *, created_by=INES, minutes_ago=30, **extra) -> dict:
    note = {
        "id": str(ObjectId()),
        "content": content,
        "created_at": _ago(minutes=minutes_ago),
        "created_by": created_by,
        "updated_at": None,
        "updated_by": None,
        "deleted_at": None,
        "deleted_by": None,
    }
    note.update(extra)
    return note


def _fiche(title="Fiche", content="Texte de la fiche.", *, created_by=INES, active=True, minutes_ago=50, **extra):
    fiche = {
        "id": str(ObjectId()),
        "title": title,
        "content": content,
        "content_text": casier_text.content_to_text(content),
        "created_at": _ago(minutes=minutes_ago),
        "created_by": created_by,
        "updated_at": None,
        "updated_by": None,
        "active": active,
        "closed_at": None if active else _ago(minutes=minutes_ago - 1),
        "closed_by": None if active else created_by,
        "revisions": [],
    }
    fiche.update(extra)
    return fiche


def _attachment(attachment_id=None, filename="capture.png", *, origin="discord", status="stored",
                content_type="image/png", uploaded_by=None, **extra) -> dict:
    attachment = {
        "id": attachment_id or str(next(_snowflakes)),
        "origin": origin,
        "filename": filename,
        "extension": storage_service.sanitize_extension(file_response_service.attachment_extension(filename)),
        "content_type": content_type,
        "size": len(PNG),
        "source_url": None,
        "status": status,
        "error": None,
        "created_at": _ago(minutes=59),
        "stored_at": _ago(minutes=59) if status == "stored" else None,
        "uploaded_by": uploaded_by,
        "deleted_at": None,
        "deleted_by": None,
    }
    attachment.update(extra)
    return attachment


def _insert_casier(discord_id=ELOISE, *, name="Éloïse", username=None, sanctions=(), fiches=(),
                   is_prevention=False, created_minutes_ago=600, refreshed=True, **extra) -> str:
    document = {
        "discord_id": discord_id,
        "created_at": _ago(minutes=created_minutes_ago),
        "created_by": INES,
        "status": "vierge",
        "discord_member_snapshot": {
            "id": discord_id,
            "username": username or name.lower(),
            "display_name": name,
            "avatar_url": None,
        },
        "is_prevention": is_prevention,
        "sanctions": list(sanctions),
        "fiches_s": list(fiches),
    }
    if refreshed:
        document["member_refreshed_at"] = _ago(seconds=5)
    document.update(extra)
    return str(h.run(h.db.casiers.insert_one(document)).inserted_id)


def _stored(casier_id: str) -> dict:
    return h.run(h.db.casiers.find_one({"_id": ObjectId(casier_id)}))


def _insert_flag(discord_id=MATHIS, *, review="a_traiter", kind="violation", gravite=2, categorie="insulte",
                 content="t'es vraiment nul", raison="Insulte dirigée", sanction=None, minutes_ago=10,
                 author_name="mathis.b") -> str:
    flag_id = str(ObjectId())
    message_id = str(next(_snowflakes))
    created = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    h.run(h.db.ai_moderation_flags.insert_one({
        "id": flag_id,
        "created_at": created,
        "discord_id": discord_id,
        "author": {"id": discord_id, "username": author_name, "display_name": author_name, "avatar_url": None},
        "guild_id": h.GUILD_ID,
        "channel": {"id": "600000000000000101", "name": "général", "parent_id": None, "category_id": None},
        "message": {"id": message_id, "content": content, "content_redacted": False,
                    "created_at": created.isoformat(),
                    "jump_url": f"https://discord.com/channels/{h.GUILD_ID}/600000000000000101/{message_id}"},
        "kind": kind,
        "verdict": {"violation": True, "categorie": categorie, "gravite": gravite, "confiance": 0.9,
                    "raison": raison, "sanction": "Avertissement"} if kind == "violation" else None,
        "mode": "log",
        "planned_action": "alert",
        "executed": [],
        "alert": {"posted": True, "channel_id": None, "message_id": None, "jump_url": None, "pinged": False},
        "model": "claude-haiku-5-5",
        "review": {"status": review, "comment": None, "reviewed_at": None, "reviewed_by": None},
        "sanction": sanction,
    }))
    return flag_id


def _flag(flag_id: str) -> dict:
    return h.run(h.db.ai_moderation_flags.find_one({"id": flag_id}))


def _logs(prefix: str = "casier.") -> list[dict]:
    logs = h.run(h.db.auth_logs.find({}).to_list(length=None))
    return [log for log in logs if str(log.get("event_type", "")).startswith(prefix)]


def _write_file(casier_id: str, sanction_id: str, attachment: dict, data: bytes = PNG) -> None:
    path = casier_attachments.attachment_storage_path(casier_id, sanction_id, attachment["id"], attachment["extension"])
    storage_service.put_object_from_bytes(path, data, attachment["content_type"] or "application/octet-stream")


def _detail(casier_id: str, role: str = "staff") -> dict:
    response = _client(role).get(f"{BASE}/{casier_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _list(role: str = "staff", **params) -> list[dict]:
    response = _client(role).get(BASE, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _names(items: list[dict]) -> list[str]:
    return [item["member"]["display_name"] for item in items]


# --------------------------------------------------------------------------------------
# 1. Statut (pire sanction) et ordre des routes
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("types", "active_fiche", "expected"),
    [
        ((), False, "vierge"),
        (("rappel_a_lordre",), False, "vierge"),
        ((), True, "vierge"),
        (("avertissement",), False, "averti"),
        (("avertissement", "mute"), False, "mute"),
        (("mute", "kick"), False, "kick"),
        (("rappel_a_lordre", "avertissement", "mute", "kick", "bannissement"), True, "banni"),
        (("type_inconnu",), False, "vierge"),
    ],
)
def test_status_is_worst_sanction_in_list_and_detail(types, active_fiche, expected):
    fiches = [_fiche()] if active_fiche else []
    casier_id = _insert_casier(sanctions=[_sanction(t) for t in types], fiches=fiches)

    assert _detail(casier_id)["status"] == expected
    assert _list()[0]["status"] == expected


def test_casier_without_sanctions_key_is_readable():
    oid = h.run(h.db.casiers.insert_one({
        "discord_id": ELOISE, "created_at": _ago(hours=1), "member_refreshed_at": _ago(seconds=1),
        "discord_member_snapshot": {"id": ELOISE, "username": "eloise", "display_name": "Éloïse"},
    })).inserted_id

    detail = _detail(str(oid))
    assert detail["status"] == "vierge"
    assert detail["sanctions"] == [] and detail["fiches_s"] == []
    assert _list()[0]["sanctions_count"] == 0


def test_static_routes_are_declared_before_casier_id():
    paths = [route.path for route in casier.router.routes]
    detail_index = paths.index("/moderation/casiers/{casier_id}")
    for static in ("/search-members", "/bot/{discord_id}", "/ai-flags", "/ai-flags/{flag_id}", ""):
        assert paths.index(f"/moderation/casiers{static}") < detail_index, static


# --------------------------------------------------------------------------------------
# 2. Route Ghost Bot
# --------------------------------------------------------------------------------------

BOT_KEYS = {"discord_id", "status", "sanctions_count", "has_active_fiche_s", "sanctions_markdown"}


def _bot(discord_id, headers, **params):
    return h.make_client(casier.router).get(f"{BASE}/bot/{discord_id}", headers=headers, params=params)


def test_bot_route_empty_answer_is_unchanged(bot_key):
    response = _bot(ELOISE, bot_key)
    assert response.status_code == 200
    assert response.json() == {
        "discord_id": ELOISE,
        "status": "vierge",
        "sanctions_count": 0,
        "has_active_fiche_s": False,
        "sanctions_markdown": "*Aucune sanction enregistrée.*",
    }


def test_bot_route_uses_legacy_values_by_default(bot_key):
    _insert_casier(ELOISE, sanctions=[_sanction("avertissement"), _sanction("bannissement")])
    _insert_casier(MATHIS, name="mathis.b", sanctions=[
        _sanction("rappel_a_lordre"), _sanction("avertissement"),
        _sanction("mute", "Récidive.", duration="1 h", duration_seconds=3600, minutes_ago=5),
    ])
    _insert_casier(PIXEL, name="pixel_renard", fiches=[_fiche()])
    _insert_casier(OTHER, name="autre", sanctions=[_sanction("rappel_a_lordre")])

    assert _bot(ELOISE, bot_key).json()["status"] == "bloque"
    mathis = _bot(MATHIS, bot_key).json()
    assert mathis["status"] == "sanctionne"
    assert set(mathis) == BOT_KEYS
    assert mathis["sanctions_count"] == 3
    assert "🔇 Mute" in mathis["sanctions_markdown"] and "(1 h)" in mathis["sanctions_markdown"]
    assert _bot(PIXEL, bot_key).json()["status"] == "surveillance"
    assert _bot(PIXEL, bot_key).json()["has_active_fiche_s"] is True
    assert _bot(OTHER, bot_key).json()["status"] == "vigilance"


def test_bot_route_v2_values_on_demand(bot_key, monkeypatch):
    _insert_casier(ELOISE, sanctions=[_sanction("bannissement")])
    _insert_casier(MATHIS, name="mathis.b", sanctions=[_sanction("mute")])
    _insert_casier(PIXEL, name="pixel_renard", fiches=[_fiche()])

    assert _bot(ELOISE, bot_key, status_format="v2").json()["status"] == "banni"
    assert _bot(MATHIS, bot_key, status_format="v2").json()["status"] == "mute"
    assert _bot(PIXEL, bot_key, status_format="v2").json()["status"] == "vierge"

    monkeypatch.setattr(casier, "GHOST_BOT_STATUS_FORMAT", "v2")
    assert _bot(ELOISE, bot_key).json()["status"] == "banni"
    assert _bot(ELOISE, bot_key, status_format="legacy").json()["status"] == "bloque"

    response = _bot(ELOISE, bot_key, status_format="autre")
    assert response.status_code == 422
    assert response.json()["detail"] == "Format de statut inconnu (legacy ou v2)."
    assert set(_bot(ELOISE, bot_key, status_format="v2").json()) == BOT_KEYS


# --------------------------------------------------------------------------------------
# 3. Identifiants stables et migration paresseuse
# --------------------------------------------------------------------------------------


def test_legacy_items_receive_persistent_ids_on_detail():
    legacy_sanctions = [_sanction("avertissement", "Sans clé"), _sanction("kick", "Id null"), _sanction("mute", "Id vide")]
    del legacy_sanctions[0]["id"]
    legacy_sanctions[1]["id"] = None
    legacy_sanctions[2]["id"] = ""
    legacy_fiche = {"title": "Ancienne fiche", "content": "Texte brut ancien.", "created_at": _ago(days=3),
                    "created_by": INES, "active": True, "closed_at": None, "closed_by": None}
    casier_id = _insert_casier(sanctions=legacy_sanctions, fiches=[legacy_fiche])

    first = _detail(casier_id)
    ids = [s["id"] for s in first["sanctions"]] + [f["id"] for f in first["fiches_s"]]
    assert len(ids) == 4 and all(HEX_ID.fullmatch(item) for item in ids)
    assert first["fiches_s"][0]["content_format"] == "text"
    assert first["fiches_s"][0]["content_text"] == "Texte brut ancien."

    stored = _stored(casier_id)
    assert sorted(s["id"] for s in stored["sanctions"]) == sorted(s["id"] for s in first["sanctions"])
    second = _detail(casier_id)
    assert [s["id"] for s in second["sanctions"]] == [s["id"] for s in first["sanctions"]]
    assert [f["id"] for f in second["fiches_s"]] == [f["id"] for f in first["fiches_s"]]


def test_add_sanction_always_assigns_an_id_and_list_matches_use_it():
    snapshot = {"id": ELOISE, "username": "eloise", "display_name": "Éloïse", "avatar_url": None}
    h.run(casier_service.add_sanction(ELOISE, "avertissement", "Lien de phishing (seed)", snapshot, INES))
    h.run(casier_service.add_sanction(
        discord_id=ELOISE, sanction_type="kick", reason="Phishing importé", snapshot=snapshot, created_by=None,
        source={"channel_id": CHANNEL_ID, "message_id": LOG_MESSAGE_ID, "message_url": None},
        dedupe_message_id=LOG_MESSAGE_ID,
    ))

    stored = h.run(h.db.casiers.find_one({"discord_id": ELOISE}))
    assert all(HEX_ID.fullmatch(s.get("id") or "") for s in stored["sanctions"])

    item = _list(q="phishing")[0]
    assert {m["sanction_id"] for m in item["matches"] if m["kind"] == "sanction"} == {
        s["id"] for s in stored["sanctions"]
    }


def test_list_search_assigns_missing_ids_before_matching():
    legacy = _sanction("avertissement", "Arnaque au phishing")
    del legacy["id"]
    casier_id = _insert_casier(sanctions=[legacy])

    item = _list(q="phishing")[0]

    stored_id = _stored(casier_id)["sanctions"][0]["id"]
    assert HEX_ID.fullmatch(stored_id)
    assert item["matches"][0]["sanction_id"] == stored_id


# --------------------------------------------------------------------------------------
# 4. Création de sanction
# --------------------------------------------------------------------------------------


def _post_sanction(casier_id, role="staff", **payload):
    body = {"type": "avertissement", "reason": "Propos humiliants."}
    body.update(payload)
    return _client(role).post(f"{BASE}/{casier_id}/sanctions", json=body)


def test_mute_with_duration_is_parsed_and_active():
    casier_id = _insert_casier()

    response = _post_sanction(casier_id, type="mute", reason="  Propos humiliants en vocal.  ", duration="1h30")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "mute"
    sanction = body["sanctions"][0]
    assert HEX_ID.fullmatch(sanction["id"])
    assert sanction["reason"] == "Propos humiliants en vocal."
    assert sanction["duration"] == "1 h 30"
    assert sanction["duration_seconds"] == 5400
    created = datetime.fromisoformat(sanction["created_at"])
    assert datetime.fromisoformat(sanction["expires_at"]) - created == timedelta(seconds=5400)
    assert sanction["is_active"] is True
    assert sanction["moderator"] is None
    assert sanction["origin"] == "manual"
    assert sanction["created_by"]["id"] == h.USER_IDS["staff"]
    assert sanction["created_by"]["display_name"]
    assert body["active_mute_until"] == sanction["expires_at"]


def test_permanent_ban_and_duration_ignored_for_warning():
    casier_id = _insert_casier()

    ban = _post_sanction(casier_id, type="bannissement", duration="permanent").json()["sanctions"][0]
    assert (ban["duration"], ban["duration_seconds"], ban["expires_at"], ban["is_active"]) == (
        "Permanent", None, None, False
    )

    warning = _post_sanction(casier_id, type="avertissement", duration="2 jours").json()["sanctions"][0]
    assert warning["type"] == "avertissement"
    assert (warning["duration"], warning["duration_seconds"], warning["expires_at"]) == (None, None, None)


def test_invalid_sanction_payloads_are_rejected():
    casier_id = _insert_casier()

    response = _post_sanction(casier_id, type="pendaison")
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Type de sanction invalide. Valeurs autorisées :")
    assert "mute" in response.json()["detail"]
    assert _post_sanction(casier_id, reason="   ").status_code == 422
    assert _post_sanction(casier_id, reason="x" * 1001).status_code == 422
    assert _post_sanction("pas-un-id").status_code == 400
    assert _post_sanction(str(ObjectId())).status_code == 404
    assert _stored(casier_id)["sanctions"] == []


def test_sanction_from_ai_flag_errors_create_nothing():
    casier_id = _insert_casier(MATHIS, name="mathis.b")
    other_member_flag = _insert_flag(NOVA)
    linked_flag = _insert_flag(MATHIS, review="pertinent", sanction={"casier_id": casier_id, "sanction_id": "a" * 24})
    false_positive = _insert_flag(MATHIS, review="faux_positif")

    cases = [
        ("pas-hexa", 400, "Identifiant invalide."),
        (str(ObjectId()), 404, "Signalement introuvable."),
        (other_member_flag, 422, "Ce signalement ne concerne pas ce membre."),
        (linked_flag, 409, "Ce signalement est déjà lié à une sanction."),
        (false_positive, 409,
         "Ce signalement a été classé « Faux positif ». Changez sa revue avant de sanctionner."),
    ]
    for flag_id, code, detail in cases:
        response = _post_sanction(casier_id, ai_flag_id=flag_id)
        assert response.status_code == code, flag_id
        assert response.json()["detail"] == detail
    assert _stored(casier_id)["sanctions"] == []
    assert _logs() == []


def test_sanction_from_open_ai_flag_links_and_reviews_it():
    casier_id = _insert_casier(MATHIS, name="mathis.b")
    flag_id = _insert_flag(MATHIS)

    response = _post_sanction(casier_id, ai_flag_id=flag_id)

    assert response.status_code == 201, response.text
    sanction = response.json()["sanctions"][0]
    assert sanction["ai_flag_id"] == flag_id
    flag = _flag(flag_id)
    assert flag["sanction"] == {"casier_id": casier_id, "sanction_id": sanction["id"]}
    assert flag["review"]["status"] == "pertinent"
    assert flag["review"]["reviewed_by"]["id"] == h.USER_IDS["staff"]
    assert [log["event_type"] for log in _logs()] == ["casier.sanction.created", "casier.ai_flag.reviewed"]
    assert response.json()["ai_flags_open"] == 0
    assert response.json()["ai_flags_total"] == 1


def test_sanction_from_relevant_ai_flag_keeps_its_review():
    casier_id = _insert_casier(MATHIS, name="mathis.b")
    flag_id = _insert_flag(MATHIS, review="pertinent")

    response = _post_sanction(casier_id, ai_flag_id=flag_id)

    assert response.status_code == 201, response.text
    flag = _flag(flag_id)
    assert flag["review"]["status"] == "pertinent"
    assert flag["review"]["reviewed_by"] is None
    assert flag["sanction"]["sanction_id"] == response.json()["sanctions"][0]["id"]
    assert [log["event_type"] for log in _logs()] == ["casier.sanction.created"]


def test_sanction_route_roles():
    casier_id = _insert_casier()

    assert _post_sanction(casier_id, role=None).status_code == 401
    assert _post_sanction(casier_id, role="member").status_code == 403
    assert _post_sanction(casier_id, role="helper").status_code == 403
    assert _post_sanction(casier_id, role="staff").status_code == 201


# --------------------------------------------------------------------------------------
# 5. Informations complémentaires
# --------------------------------------------------------------------------------------


def _note_url(casier_id, sanction_id, note_id=None):
    url = f"{BASE}/{casier_id}/sanctions/{sanction_id}/notes"
    return f"{url}/{note_id}" if note_id else url


def _casier_with_sanction(**sanction_extra):
    sanction = _sanction("avertissement", "Insulte en vocal.", **sanction_extra)
    return _insert_casier(sanctions=[sanction]), sanction


def test_note_lifecycle_and_rights(responsable, other_staff):
    casier_id, sanction = _casier_with_sanction()
    url = _note_url(casier_id, sanction["id"])

    created = _client().post(url, json={"content": "  Captures transmises par mathis.b.  "})
    assert created.status_code == 201, created.text
    note = created.json()["sanctions"][0]["notes"][0]
    assert note["content"] == "Captures transmises par mathis.b."
    assert HEX_ID.fullmatch(note["id"])
    assert note["can_edit"] is True
    assert note["created_by"]["id"] == h.USER_IDS["staff"]

    other_view = _detail(casier_id, role=other_staff)["sanctions"][0]["notes"][0]
    assert other_view["can_edit"] is False
    assert _detail(casier_id, role=responsable)["sanctions"][0]["notes"][0]["can_edit"] is True

    note_url = _note_url(casier_id, sanction["id"], note["id"])
    forbidden = _client(other_staff).patch(note_url, json={"content": "Réécrit par un autre."})
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Seul l'auteur ou un Responsable peut modifier cette information."

    by_author = _client().patch(note_url, json={"content": "Captures et transcription transmises."})
    assert by_author.status_code == 200, by_author.text
    edited = by_author.json()["sanctions"][0]["notes"][0]
    assert edited["content"] == "Captures et transcription transmises."
    assert edited["updated_by"]["id"] == h.USER_IDS["staff"]
    assert edited["updated_at"]

    by_responsable = _client(responsable).patch(note_url, json={"content": "Vérifié par Lou."})
    assert by_responsable.status_code == 200
    assert by_responsable.json()["sanctions"][0]["notes"][0]["updated_by"]["id"] == h.USER_IDS["responsable"]

    forbidden = _client(other_staff).delete(note_url)
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Seul l'auteur ou un Responsable peut supprimer cette information."
    assert _client().patch(note_url, json={"content": "   "}).status_code == 422


def test_deleted_note_is_hidden_from_detail_and_search():
    casier_id, sanction = _casier_with_sanction()
    note = _client().post(_note_url(casier_id, sanction["id"]), json={"content": "Excuses en MP."}).json()
    note_id = note["sanctions"][0]["notes"][0]["id"]
    assert _list(q="excuses")

    response = _client().delete(_note_url(casier_id, sanction["id"], note_id))

    assert response.status_code == 200, response.text
    assert response.json()["sanctions"][0]["notes"] == []
    stored_note = _stored(casier_id)["sanctions"][0]["notes"][0]
    assert stored_note["deleted_at"] and stored_note["deleted_by"]["id"] == h.USER_IDS["staff"]
    assert _list(q="excuses") == []
    assert _client().delete(_note_url(casier_id, sanction["id"], note_id)).status_code == 404


def test_note_routes_validate_ids():
    casier_id, sanction = _casier_with_sanction()
    client = _client()

    assert client.post(_note_url(casier_id, "pas-hexa"), json={"content": "x"}).status_code == 400
    assert client.post(_note_url("pas-un-id", sanction["id"]), json={"content": "x"}).status_code == 400
    assert client.patch(_note_url(casier_id, sanction["id"], "zz"), json={"content": "x"}).status_code == 400
    unknown = client.post(_note_url(casier_id, "b" * 24), json={"content": "x"})
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Sanction introuvable."
    missing = client.patch(_note_url(casier_id, sanction["id"], "c" * 24), json={"content": "x"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Information introuvable."
    assert client.post(_note_url(str(ObjectId()), sanction["id"]), json={"content": "x"}).status_code == 404


# --------------------------------------------------------------------------------------
# 6. Fiches S
# --------------------------------------------------------------------------------------


def _inline(text, **styles):
    return {"type": "text", "text": text, "styles": styles}


def _block(type_, content=None, **props):
    return {"id": str(ObjectId()), "type": type_, "props": props, "content": content or [], "children": []}


def _fiche_url(casier_id, fiche_id=None, suffix=""):
    url = f"{BASE}/{casier_id}/fiches-s"
    return f"{url}/{fiche_id}{suffix}" if fiche_id else url


def test_create_blocknote_fiche_extracts_text_without_changing_status():
    casier_id = _insert_casier()
    blocks = [
        _block("paragraph", [_inline("Messages privés insistants.")]),
        _block("bulletListItem", [_inline("Relancer les nouveaux arrivants")]),
        _block("paragraph", [{"type": "link", "href": "https://loasis.example/regles", "content": [_inline("règlement")]}]),
        {"id": "t", "type": "table", "props": {}, "children": [],
         "content": {"type": "tableContent", "rows": [{"cells": [[_inline("Date")], [_inline("Salon")]]}]}},
        _block("image", url="/api/staff/meetings/images/capture.png", caption="Capture du salon"),
    ]

    response = _client().post(_fiche_url(casier_id), json={"title": "Comportement à suivre", "content": json.dumps(blocks)})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "vierge"
    fiche = body["fiches_s"][0]
    assert fiche["content_format"] == "blocknote"
    for text in ("Messages privés insistants.", "Relancer les nouveaux arrivants", "règlement", "Date", "Salon",
                 "Capture du salon"):
        assert text in fiche["content_text"]
    assert fiche["can_edit"] is True and fiche["revisions_count"] == 0
    assert body["active_fiches_s_count"] == 1
    assert _list()[0]["has_active_fiche_s"] is True


def test_empty_and_media_only_fiches():
    casier_id = _insert_casier()
    client = _client()

    empty = client.post(_fiche_url(casier_id), json={"title": "Vide", "content": json.dumps([_block("paragraph")])})
    assert empty.status_code == 422
    assert empty.json()["detail"] == "La fiche S est vide."

    image = [_block("image", url="/api/staff/meetings/images/x.png")]
    assert client.post(_fiche_url(casier_id), json={"title": "Image", "content": json.dumps(image)}).status_code == 201

    numbers = client.post(_fiche_url(casier_id), json={"title": "Nombres", "content": "[1,2]"})
    assert numbers.status_code == 201
    stored = next(f for f in numbers.json()["fiches_s"] if f["title"] == "Nombres")
    assert stored["content_format"] == "text" and stored["content"] == "[1,2]"
    assert client.post(_fiche_url(casier_id), json={"title": "  ", "content": "x"}).status_code == 422


def test_legacy_text_and_html_fiches_are_readable():
    casier_id = _insert_casier(fiches=[
        _fiche("Texte", "Ancienne fiche en texte brut."),
        _fiche("HTML", "<p>Ancienne <b>fiche</b></p><img src=x onerror=alert(1)>", active=False),
    ])

    fiches = {f["title"]: f for f in _detail(casier_id)["fiches_s"]}
    assert fiches["Texte"]["content_format"] == "text"
    assert fiches["Texte"]["content"] == "Ancienne fiche en texte brut."
    assert fiches["HTML"]["content_format"] == "html"
    assert "fiche" in fiches["HTML"]["content_text"] and "<" not in fiches["HTML"]["content_text"]
    assert [f["active"] for f in _detail(casier_id)["fiches_s"]] == [True, False]


def test_fiche_is_sanitized_on_write_and_on_read():
    unsafe = [
        _block("paragraph", [{"type": "link", "href": "javascript:alert(1)", "content": [_inline("clic")]}]),
        _block("paragraph", [{"type": "link", "href": " JaVaScRiPt:alert(1)", "content": [_inline("deux")]}]),
        _block("paragraph", [{"type": "link", "href": "java\tscript:alert(1)", "content": [_inline("trois")]}]),
        _block("paragraph", [{"type": "link", "href": "mailto:staff@loasis.example", "content": [_inline("mail")]}]),
        _block("paragraph", [{"type": "link", "href": "https://loasis.example", "content": [_inline("site")]}]),
        _block("image", url="https://tracker.example/p.gif"),
        _block("image", url="data:image/png;base64,AAAA"),
        _block("image", url="/api/staff/meetings/images/a.png"),
        _block("image", url="https://api.loasis.app/api/staff/meetings/images/a.png"),
    ]
    casier_id = _insert_casier()

    created = _client().post(_fiche_url(casier_id), json={"title": "Liens", "content": json.dumps(unsafe)})
    assert created.status_code == 201, created.text
    stored_content = _stored(casier_id)["fiches_s"][0]["content"]
    assert "javascript" not in stored_content.lower()
    assert "Média externe non affiché : https://tracker.example/p.gif" in stored_content
    blocks = json.loads(stored_content)
    links = [inline.get("href") for block in blocks for inline in block.get("content") or []
             if isinstance(inline, dict) and inline.get("type") == "link"]
    assert links == ["mailto:staff@loasis.example", "https://loasis.example"]
    images = [block["props"]["url"] for block in blocks if block["type"] == "image"]
    assert images == ["/api/staff/meetings/images/a.png", "https://api.loasis.app/api/staff/meetings/images/a.png"]
    text = created.json()["fiches_s"][0]["content_text"]
    assert all(word in text for word in ("clic", "deux", "trois", "mail", "site"))

    # Document écrit directement en base : assaini à la lecture.
    raw = json.dumps([_block("paragraph", [{"type": "link", "href": "javascript:alert(1)", "content": [_inline("x")]}])])
    other_id = _insert_casier(OTHER, name="autre", fiches=[_fiche("Brut", raw)])
    read = _detail(other_id)["fiches_s"][0]
    assert read["content_format"] == "blocknote"
    assert "javascript" not in read["content"].lower()


def test_fiche_patch_rights_and_revisions(responsable, other_staff):
    casier_id = _insert_casier()
    created = _client().post(_fiche_url(casier_id), json={"title": "Titre 1", "content": "Contenu 1"}).json()
    fiche_id = created["fiches_s"][0]["id"]
    url = _fiche_url(casier_id, fiche_id)

    assert _client().patch(url, json={}).json()["detail"] == "Rien à modifier."
    forbidden = _client(other_staff).patch(url, json={"title": "Pirate"})
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Seul l'auteur ou un Responsable peut modifier cette fiche S."
    assert _detail(casier_id, role=other_staff)["fiches_s"][0]["can_edit"] is False

    by_author = _client().patch(url, json={"title": "Titre 2", "content": "Contenu 2"})
    assert by_author.status_code == 200, by_author.text
    fiche = by_author.json()["fiches_s"][0]
    assert (fiche["title"], fiche["content"], fiche["revisions_count"]) == ("Titre 2", "Contenu 2", 1)
    assert fiche["updated_by"]["id"] == h.USER_IDS["staff"]
    revision = _stored(casier_id)["fiches_s"][0]["revisions"][0]
    assert (revision["title"], revision["content"]) == ("Titre 1", "Contenu 1")

    by_responsable = _client(responsable).patch(url, json={"content": "Contenu 3"})
    assert by_responsable.status_code == 200
    assert by_responsable.json()["fiches_s"][0]["revisions_count"] == 2

    logs_before = len(_logs())
    unchanged = _client().patch(url, json={"title": "Titre 2", "content": "Contenu 3"})
    assert unchanged.status_code == 200
    assert unchanged.json()["fiches_s"][0]["revisions_count"] == 2
    assert len(_logs()) == logs_before

    assert '"revisions"' not in json.dumps(unchanged.json())
    assert '"revisions"' not in json.dumps(_list())
    missing = _client().patch(_fiche_url(casier_id, "d" * 24), json={"title": "x"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Fiche S introuvable."
    assert _client().patch(_fiche_url(casier_id, "pas-hexa"), json={"title": "x"}).status_code == 400


def test_closed_and_legacy_fiches_are_editable_by_responsable_only(responsable):
    mine = _fiche("Ma fiche", "Contenu")
    legacy = _fiche("Héritée", "Sans auteur", created_by=None)
    casier_id = _insert_casier(fiches=[mine, legacy])
    fiche_id, legacy_id = mine["id"], legacy["id"]

    closed = _client().patch(_fiche_url(casier_id, fiche_id, "/close"))
    assert closed.status_code == 200, closed.text
    again = _client().patch(_fiche_url(casier_id, fiche_id, "/close"))
    assert again.status_code == 404
    assert again.json()["detail"] == "Casier ou fiche S introuvable, ou déjà clôturée."

    by_author = _client().patch(_fiche_url(casier_id, fiche_id), json={"title": "Après clôture"})
    assert by_author.status_code == 403
    assert by_author.json()["detail"] == "Seul un Responsable peut modifier une fiche S clôturée."
    assert _client(responsable).patch(_fiche_url(casier_id, fiche_id), json={"title": "Après clôture"}).status_code == 200

    assert _client().patch(_fiche_url(casier_id, legacy_id), json={"title": "x"}).status_code == 403
    assert _client(responsable).patch(_fiche_url(casier_id, legacy_id), json={"title": "x"}).status_code == 200


def test_fiche_keeps_only_twenty_revisions():
    casier_id = _insert_casier()
    fiche_id = _client().post(_fiche_url(casier_id), json={"title": "T", "content": "v0"}).json()["fiches_s"][0]["id"]

    for index in range(1, 26):
        assert _client().patch(_fiche_url(casier_id, fiche_id), json={"content": f"v{index}"}).status_code == 200

    revisions = _stored(casier_id)["fiches_s"][0]["revisions"]
    assert len(revisions) == 20
    assert [r["content"] for r in revisions] == [f"v{index}" for index in range(5, 25)]
    assert _detail(casier_id)["fiches_s"][0]["revisions_count"] == 20


# --------------------------------------------------------------------------------------
# 7. Super recherche
# --------------------------------------------------------------------------------------


@pytest.fixture
def search_data():
    phishing = _sanction("avertissement", "Récidive : lien de phishing supprimé.", minutes_ago=30,
                         notes=[_note("Captures transmises par la victime.", minutes_ago=20)],
                         attachments=[_attachment(filename="preuve-phishing.png")])
    ids = {
        "eloise": _insert_casier(ELOISE, name="Éloïse", username="eloise_92", sanctions=[phishing],
                                 created_minutes_ago=900),
        "ines": _insert_casier(INES_MEMBER, name="Inès", username="ines.membre", created_minutes_ago=800,
                               sanctions=[_sanction("kick", "Spam de liens.", created_by=LOU, minutes_ago=200)]),
        "mathis": _insert_casier(MATHIS, name="mathis.b", created_minutes_ago=700, sanctions=[
            _sanction("mute", "Propos humiliants.", created_by=BOT, minutes_ago=10,
                      moderator={"id": INES["id"], "username": None, "display_name": "Inès (staff)"},
                      source={"channel_id": CHANNEL_ID, "message_id": LOG_MESSAGE_ID, "message_url": None},
                      duration="1 h", duration_seconds=3600, expires_at=_ago(minutes=-50)),
        ]),
        "pixel": _insert_casier(PIXEL, name="pixel_renard", created_minutes_ago=600, is_prevention=True,
                                sanctions=[_sanction("avertissement", "🔥🔥 spam massif dans #général", created_by=LOU,
                                                     minutes_ago=400)],
                                fiches=[_fiche("Œuvre partagée sans accord", "Il a écrit straße partout.",
                                               created_by=LOU, minutes_ago=300)]),
    }
    _insert_flag(MATHIS)
    return ids


def test_member_search_is_accent_insensitive_and_scoped(search_data):
    items = _list(q="eloise")
    assert _names(items) == ["Éloïse"]
    match = items[0]["matches"][0]
    assert (match["kind"], match["field"]) == ("membre", "display_name")
    assert match["segments"] == [{"text": "Éloïse", "match": True}]

    assert _list(q="phishing", scope="membre") == []
    assert _names(_list(q="86093580", scope="membre")) == ["Éloïse"]
    assert "Éloïse" in _names(_list(q="115363852178", scope="membre"))
    assert _list(q="ELOISE_92")[0]["matches"][0]["field"] == "username"


def test_staff_search_uses_author_and_moderator(search_data):
    items = {item["member"]["display_name"]: item for item in _list(q="ines", scope="staff")}

    assert set(items) == {"Éloïse", "mathis.b"}
    assert items["Éloïse"]["matches"][0]["field"] == "author"
    moderator = items["mathis.b"]["matches"][0]
    assert moderator["field"] == "moderator"
    assert moderator["snippet"] == "Inès (staff)"
    assert moderator["author"]["display_name"] == "Inès (staff)"
    assert moderator["sanction_type"] == "mute"
    assert "mathis.b" in _names(_list(q="bot", scope="staff"))
    assert "Inès" in _names(_list(q="ines", scope="membre"))


def test_content_search_covers_reason_notes_fiches_and_files(search_data):
    eloise = _list(q="phishing", scope="contenu")
    assert _names(eloise) == ["Éloïse"]
    fields = [(m["kind"], m["field"]) for m in eloise[0]["matches"]]
    assert ("sanction", "reason") in fields and ("sanction", "filename") in fields
    assert all(m["sanction_id"] for m in eloise[0]["matches"])

    note = _list(q="transmises")[0]["matches"][0]
    assert (note["kind"], note["field"]) == ("note", "content")
    assert note["note_id"] and note["sanction_id"]

    title = _list(q="oeuvre")[0]["matches"][0]
    assert (title["kind"], title["field"], title["fiche_id"] is not None) == ("fiche_s", "title", True)
    assert [s["text"] for s in title["segments"] if s["match"]] == ["Œuvre"]
    content = _list(q="strasse")[0]["matches"][0]
    assert (content["kind"], content["field"]) == ("fiche_s", "content")
    assert [s["text"] for s in content["segments"] if s["match"]] == ["straße"]


def test_all_terms_must_match_and_term_limit(search_data):
    assert _names(_list(q="phishing captures")) == ["Éloïse"]
    assert _list(q="phishing introuvable") == []

    response = _client().get(BASE, params={"q": "un deux trois quatre cinq six"})
    assert response.status_code == 422
    assert response.json()["detail"] == "5 mots maximum."
    assert _client().get(BASE, params={"q": "x" * 101}).status_code == 422
    assert len(_list(q="   ")) == 4


def test_segments_are_exact_with_emojis(search_data):
    item = _list(q="spam massif")[0]
    assert item["member"]["display_name"] == "pixel_renard"
    for match in item["matches"]:
        assert "".join(segment["text"] for segment in match["segments"]) == match["snippet"]
        assert all(segment["text"] for segment in match["segments"])
        for segment in match["segments"]:
            if segment["match"]:
                assert casier_text.fold(segment["text"]) in {"spam", "massif"}
    reason = next(m for m in item["matches"] if m["field"] == "reason")
    assert reason["snippet"] == "🔥🔥 spam massif dans #général"
    assert [s["text"] for s in reason["segments"] if s["match"]] == ["spam", "massif"]


def test_matches_are_limited_to_five():
    sanctions = [_sanction("avertissement", f"Spam numéro {index}", minutes_ago=index) for index in range(7)]
    _insert_casier(sanctions=sanctions)

    item = _list(q="spam")[0]

    assert len(item["matches"]) == 5
    assert item["matches_total"] == 7
    assert [m["snippet"] for m in item["matches"]] == [f"Spam numéro {index}" for index in range(5)]
    assert _list()[0]["matches"] == [] and _list()[0]["matches_total"] == 0


def test_list_filters(search_data):
    assert set(_names(_list(status="banni,mute"))) == {"mathis.b"}
    assert set(_names(_list(status="averti,kick"))) == {"Éloïse", "Inès", "pixel_renard"}
    assert len(_list(status="")) == 4

    assert _names(_list(has_active_fiche_s="true")) == ["pixel_renard"]
    assert "pixel_renard" not in _names(_list(has_active_fiche_s="false"))
    assert _names(_list(prevention="true")) == ["pixel_renard"]
    assert len(_list(prevention="false")) == 3
    assert _names(_list(has_open_ai_flags="true")) == ["mathis.b"]
    assert len(_list(has_open_ai_flags="false")) == 3

    unknown = _client().get(BASE, params={"status": "banni,surveillance"})
    assert unknown.status_code == 422
    assert unknown.json()["detail"] == "Statut inconnu : surveillance."
    for params in ({"scope": "partout"}, {"sort": "hasard"}, {"prevention": "peut-etre"}):
        response = _client().get(BASE, params=params)
        assert response.status_code == 422, params
        assert isinstance(response.json()["detail"], list)


def test_list_sorts_and_fields(search_data):
    assert _names(_list()) == ["mathis.b", "Éloïse", "Inès", "pixel_renard"]
    assert _names(_list(sort="gravite")) == ["Inès", "mathis.b", "Éloïse", "pixel_renard"]
    assert _names(_list(sort="nom")) == ["Éloïse", "Inès", "mathis.b", "pixel_renard"]

    items = {item["member"]["display_name"]: item for item in _list()}
    mathis = items["mathis.b"]
    assert (mathis["ai_flags_total"], mathis["ai_flags_open"]) == (1, 1)
    assert mathis["active_mute_until"]
    assert mathis["sanctions_summary"]["mute"] == 1
    eloise = items["Éloïse"]
    assert eloise["last_sanction_label"] == "Récidive : lien de phishing supprimé."
    assert datetime.fromisoformat(eloise["last_activity_at"]) >= datetime.fromisoformat(eloise["last_sanction_at"])
    assert items["pixel_renard"]["is_prevention"] is True


# --------------------------------------------------------------------------------------
# 10. Fichiers : service des copies locales
# --------------------------------------------------------------------------------------


def _attachment_url(casier_id, sanction_id, attachment_id):
    return f"{BASE}/{casier_id}/sanctions/{sanction_id}/attachments/{attachment_id}"


def _casier_with_files(*attachments, write=True):
    sanction = _sanction("mute", "Avec fichiers.", attachments=list(attachments),
                         source={"channel_id": CHANNEL_ID, "message_id": LOG_MESSAGE_ID, "message_url": None})
    casier_id = _insert_casier(sanctions=[sanction])
    if write:
        for attachment in attachments:
            if attachment["status"] == "stored":
                _write_file(casier_id, sanction["id"], attachment, PNG)
    return casier_id, sanction


def test_attachment_png_is_served_inline_with_safe_headers():
    png = _attachment(filename="capture.png")
    casier_id, sanction = _casier_with_files(png)
    url = _attachment_url(casier_id, sanction["id"], png["id"])

    response = _client().get(url)

    assert response.status_code == 200, response.text
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"

    download = _client().get(url, params={"download": 1})
    assert download.headers["content-disposition"].startswith("attachment;")

    partial = _client().get(url, headers={"Range": "bytes=0-7"})
    assert partial.status_code == 206
    assert partial.content == PNG[:8]

    detail_file = _detail(casier_id)["sanctions"][0]["attachments"][0]
    assert detail_file["inline"] is True
    assert detail_file["download_url"] == f"/moderation/casiers/{casier_id}/sanctions/{sanction['id']}/attachments/{png['id']}"
    assert "source_url" not in detail_file


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("image.svg", "image/svg+xml"), ("page.html", "text/html"), ("rapport.pdf", "application/pdf"),
     ("faux.png", "text/html")],
)
def test_other_files_are_downloaded_with_safe_type(filename, content_type):
    attachment = _attachment(filename=filename, content_type=content_type)
    casier_id, sanction = _casier_with_files(attachment)

    response = _client().get(_attachment_url(casier_id, sanction["id"], attachment["id"]))

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-type"] == "application/octet-stream"


def test_attachment_errors(other_staff):
    stored = _attachment(filename="ok.png")
    pending = _attachment(filename="attente.png", status="pending")
    too_large = _attachment(filename="video.mp4", status="too_large", content_type="video/mp4")
    deleted = _attachment(filename="retire.png", origin="upload", deleted_at=_ago(minutes=1), uploaded_by=INES)
    missing_on_disk = _attachment(filename="perdu.png")
    casier_id, sanction = _casier_with_files(stored, pending, too_large, deleted, missing_on_disk, write=False)
    _write_file(casier_id, sanction["id"], stored)
    client = _client()

    for bad in ("..x", "abc", "12345", "a" * 25):
        assert client.get(_attachment_url(casier_id, sanction["id"], bad)).status_code == 400, bad
    for attachment in (pending, too_large, missing_on_disk):
        response = client.get(_attachment_url(casier_id, sanction["id"], attachment["id"]))
        assert response.status_code == 404
        assert response.json()["detail"] == "Copie locale indisponible pour ce fichier."
    gone = client.get(_attachment_url(casier_id, sanction["id"], deleted["id"]))
    assert gone.status_code == 404 and gone.json()["detail"] == "Fichier introuvable."
    assert [a["id"] for a in _detail(casier_id)["sanctions"][0]["attachments"]] == [
        stored["id"], pending["id"], too_large["id"], missing_on_disk["id"]
    ]
    url = _attachment_url(casier_id, sanction["id"], stored["id"])
    assert _client("helper").get(url).status_code == 403
    assert _client(None).get(url).status_code == 401
    assert _client(other_staff).get(url).status_code == 200


# --------------------------------------------------------------------------------------
# 11. Fichiers ajoutés à la main
# --------------------------------------------------------------------------------------


def _upload(casier_id, sanction_id, filename, data, content_type="application/octet-stream", role="staff"):
    return _client(role).post(
        f"{BASE}/{casier_id}/sanctions/{sanction_id}/attachments",
        files={"file": (filename, data, content_type)},
    )


def test_upload_png_then_delete_by_author(other_staff):
    casier_id, sanction = _casier_with_sanction()

    response = _upload(casier_id, sanction["id"], "capture.png", PNG, "text/html")

    assert response.status_code == 201, response.text
    attachment = response.json()["sanctions"][0]["attachments"][0]
    assert attachment["origin"] == "upload"
    assert attachment["status"] == "stored"
    assert attachment["content_type"] == "image/png"
    assert attachment["can_delete"] is True
    assert attachment["uploaded_by"]["id"] == h.USER_IDS["staff"]
    served = _client().get(_attachment_url(casier_id, sanction["id"], attachment["id"]))
    assert served.content == PNG
    stored = _stored(casier_id)["sanctions"][0]["attachments"][0]
    path = storage_service.STORAGE_ROOT / casier_attachments.attachment_storage_path(
        casier_id, sanction["id"], attachment["id"], stored["extension"]
    )
    assert path.is_file()

    assert _detail(casier_id, role=other_staff)["sanctions"][0]["attachments"][0]["can_delete"] is False
    url = _attachment_url(casier_id, sanction["id"], attachment["id"])
    forbidden = _client(other_staff).delete(url)
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Seul l'auteur ou un Responsable peut retirer ce fichier."

    removed = _client().delete(url)
    assert removed.status_code == 200, removed.text
    assert removed.json()["sanctions"][0]["attachments"] == []
    assert not path.exists()
    assert _stored(casier_id)["sanctions"][0]["attachments"][0]["deleted_at"]


def test_upload_rejects_bad_files(monkeypatch):
    casier_id, sanction = _casier_with_sanction()

    for filename in ("page.html", "image.svg"):
        response = _upload(casier_id, sanction["id"], filename, b"<svg></svg>")
        assert response.status_code == 422, filename
        assert response.json()["detail"] == "Format non autorisé (images, PDF ou TXT)."
    spoofed = _upload(casier_id, sanction["id"], "capture.png", b"<html><script>alert(1)</script></html>")
    assert spoofed.status_code == 422
    assert spoofed.json()["detail"] == "Le contenu du fichier ne correspond pas à son extension."

    monkeypatch.setattr(config, "CASIER_UPLOAD_MAX_BYTES", 32, raising=False)
    monkeypatch.setattr(casier_attachments, "CASIER_UPLOAD_MAX_BYTES", 32, raising=False)
    too_big = _upload(casier_id, sanction["id"], "capture.png", PNG)
    assert too_big.status_code == 413
    assert too_big.json()["detail"].startswith("Fichier trop volumineux")
    assert _stored(casier_id)["sanctions"][0]["attachments"] == []
    casiers_root = storage_service.STORAGE_ROOT / "iris" / "casiers"
    assert not casiers_root.exists() or not any(path.is_file() for path in casiers_root.rglob("*"))


def test_upload_limit_and_discord_files_cannot_be_removed():
    uploads = [_attachment(filename=f"capture-{i}.png", origin="upload", uploaded_by=INES) for i in range(10)]
    casier_id, sanction = _casier_with_sanction(attachments=uploads)

    full = _upload(casier_id, sanction["id"], "onzieme.png", PNG)
    assert full.status_code == 409
    assert full.json()["detail"] == "Limite de 10 fichiers atteinte pour cette sanction."

    discord_file = _attachment(filename="log.png")
    other_id, other_sanction = _casier_with_files(discord_file)
    response = _client().delete(_attachment_url(other_id, other_sanction["id"], discord_file["id"]))
    assert response.status_code == 409
    assert response.json()["detail"] == "Les fichiers importés depuis Discord ne peuvent pas être retirés."


# --------------------------------------------------------------------------------------
# 12. Récupération des fichiers du log
# --------------------------------------------------------------------------------------


def _raw_log_message(channel_id, message_id, moderator_id=INES["id"], member_id=MATHIS):
    attachment_id = str(int(message_id) + 1)
    return {
        "id": str(message_id),
        "channel_id": str(channel_id),
        "content": "",
        "embeds": [],
        "attachments": [{
            "id": attachment_id,
            "filename": "preuve-log.png",
            "size": len(PNG),
            "url": f"https://cdn.discordapp.com/attachments/{channel_id}/{attachment_id}/preuve-log.png?ex=1",
            "content_type": "image/png",
        }],
        "components": [{
            "type": 17,
            "components": [
                {"type": 10, "content": f"<@{moderator_id}> a mit <@{member_id}> (`{member_id}`) en mute.\n"
                                        "### Raison de l'ajout : \n```démo```"},
                {"type": 13, "file": {"url": "attachment://preuve-log.png", "attachment_id": attachment_id}},
            ],
        }],
    }


def _resync_url(casier_id, sanction_id):
    return f"{BASE}/{casier_id}/sanctions/{sanction_id}/attachments/resync"


def test_resync_queues_log_files_and_fills_moderator(monkeypatch, mirror_calls, fake_cdn, casier_http):
    calls = []

    async def fake_fetch(channel_id, message_id):
        calls.append((channel_id, message_id))
        return _raw_log_message(channel_id, message_id)

    monkeypatch.setattr(moderation_bot, "fetch_raw_message", fake_fetch)
    casier_http["members"][INES["id"]] = {"user": {"id": INES["id"], "username": "staff"}, "nick": "Inès (staff)"}
    sanction = _sanction("mute", "Importée avant la refonte.", created_by=BOT,
                         source={"channel_id": CHANNEL_ID, "message_id": LOG_MESSAGE_ID, "message_url": None})
    casier_id = _insert_casier(MATHIS, name="mathis.b", sanctions=[sanction])

    response = _client().post(_resync_url(casier_id, sanction["id"]))

    assert response.status_code == 202, response.text
    assert calls == [(int(CHANNEL_ID), int(LOG_MESSAGE_ID))]
    queued = response.json()["sanctions"][0]
    assert [(a["filename"], a["status"]) for a in queued["attachments"]] == [("preuve-log.png", "pending")]
    assert queued["moderator"]["id"] == INES["id"]
    assert mirror_calls == [(casier_id, sanction["id"])]
    log = _logs("casier.sanction.attachments.resynced")[0]
    assert log["status_code"] == 202
    assert (log["details"]["files_found"], log["details"]["files_queued"], log["details"]["moderator_filled"]) == (
        1, 1, True
    )

    h.run(casier_attachments.mirror_pending(casier_id, sanction["id"]))

    stored = _detail(casier_id)["sanctions"][0]["attachments"][0]
    assert stored["status"] == "stored"
    assert fake_cdn.requests and fake_cdn.requests[0].startswith("https://cdn.discordapp.com/attachments/")
    assert _client().get(f"/api{stored['download_url']}").content == PNG


def test_resync_errors_happen_before_any_write(monkeypatch, mirror_calls):
    manual = _sanction("avertissement", "Manuelle.")
    busy = _sanction("mute", "Copie en cours.", created_by=BOT,
                     source={"channel_id": CHANNEL_ID, "message_id": LOG_MESSAGE_ID, "message_url": None},
                     attachments=[_attachment(filename="attente.png", status="pending", created_at=_ago(minutes=2))])
    logged = _sanction("mute", "Log introuvable.", created_by=BOT,
                       source={"channel_id": CHANNEL_ID, "message_id": "1299887766554433999", "message_url": None})
    casier_id = _insert_casier(MATHIS, name="mathis.b", sanctions=[manual, busy, logged])
    before = _stored(casier_id)

    no_log = _client().post(_resync_url(casier_id, manual["id"]))
    assert no_log.status_code == 409
    assert no_log.json()["detail"] == "Cette sanction n'a pas de message de log Discord."
    running = _client().post(_resync_url(casier_id, busy["id"]))
    assert running.status_code == 409
    assert running.json()["detail"] == "Une copie des fichiers est déjà en cours."

    async def fetch_none(channel_id, message_id):
        return None

    async def fetch_raises(channel_id, message_id):
        raise RuntimeError("Discord indisponible")

    for fake in (fetch_none, fetch_raises):
        monkeypatch.setattr(moderation_bot, "fetch_raw_message", fake)
        failed = _client().post(_resync_url(casier_id, logged["id"]))
        assert failed.status_code == 502
        assert failed.json()["detail"] == "Message de log introuvable ou inaccessible sur Discord."

    assert _stored(casier_id)["sanctions"] == before["sanctions"]
    assert mirror_calls == []
    assert _logs() == []


# --------------------------------------------------------------------------------------
# 13. Signalements IA (API)
# --------------------------------------------------------------------------------------


@pytest.fixture
def flags_data():
    mathis_casier = _insert_casier(MATHIS, name="mathis.b", sanctions=[_sanction("mute")])
    return {
        "casier": mathis_casier,
        "insulte": _insert_flag(MATHIS, raison="Insulte dirigée contre Éloïse", minutes_ago=5),
        "menace": _insert_flag(MATHIS, review="pertinent", categorie="menace", gravite=3, minutes_ago=15),
        "spam": _insert_flag(NOVA, review="faux_positif", categorie="spam", gravite=1, author_name="nova.lune",
                             minutes_ago=25),
        "refus": _insert_flag(NOVA, kind="refus", content=None, author_name="nova.lune", minutes_ago=35),
    }


def _flags(**params) -> dict:
    response = _client().get(f"{BASE}/ai-flags", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_ai_flags_list_filters_and_counts(flags_data):
    everything = _flags()
    assert everything["total"] == 4
    assert [item["id"] for item in everything["items"]] == [
        flags_data["insulte"], flags_data["menace"], flags_data["spam"], flags_data["refus"]
    ]
    assert everything["counts"] == {"a_traiter": 2, "pertinent": 1, "faux_positif": 1, "total": 4}

    to_do = _flags(review_status="a_traiter")
    assert to_do["total"] == 2
    assert to_do["counts"]["total"] == 4
    assert [i["id"] for i in _flags(discord_id=NOVA)["items"]] == [flags_data["spam"], flags_data["refus"]]
    assert [i["id"] for i in _flags(min_gravity=3)["items"]] == [flags_data["menace"]]
    assert [i["id"] for i in _flags(min_gravity=1)["items"]] == [
        flags_data["insulte"], flags_data["menace"], flags_data["spam"]
    ]
    assert [i["id"] for i in _flags(category="spam")["items"]] == [flags_data["spam"]]
    assert [i["id"] for i in _flags(kind="refus")["items"]] == [flags_data["refus"]]
    assert [i["id"] for i in _flags(q="ELOÏSE")["items"]] == [flags_data["insulte"]]
    assert _flags(skip=1, limit=1)["items"][0]["id"] == flags_data["menace"]

    item = everything["items"][0]
    assert item["casier_id"] == flags_data["casier"] and item["casier_status"] == "mute"
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
    assert "guild_id" not in item and "parent_id" not in item["channel"]
    nova = next(i for i in everything["items"] if i["id"] == flags_data["spam"])
    assert nova["casier_id"] is None and nova["casier_status"] is None

    for params in ({"discord_id": "123"}, {"review_status": "ouvert"}, {"min_gravity": 4}, {"kind": "autre"},
                   {"category": "Pas-Valide"}, {"limit": 101}, {"skip": -1}):
        assert _client().get(f"{BASE}/ai-flags", params=params).status_code == 422, params
    assert _client().get(f"{BASE}/ai-flags", params={"discord_id": "123"}).json()["detail"] == (
        "Identifiant Discord invalide."
    )


def test_ai_flag_by_id(flags_data):
    response = _client().get(f"{BASE}/ai-flags/{flags_data['insulte']}")
    assert response.status_code == 200, response.text
    assert response.json() == _flags()["items"][0]

    unknown = _client().get(f"{BASE}/ai-flags/{'e' * 24}")
    assert unknown.status_code == 404 and unknown.json()["detail"] == "Signalement introuvable."
    malformed = _client().get(f"{BASE}/ai-flags/pas-un-id")
    assert malformed.status_code == 400 and malformed.json()["detail"] == "Identifiant invalide."
    assert _client("helper").get(f"{BASE}/ai-flags").status_code == 403


def test_ai_flag_review(flags_data):
    url = f"{BASE}/ai-flags/{flags_data['insulte']}"

    reviewed = _client().patch(url, json={"review_status": "faux_positif", "comment": "  Taquinerie entre amis.  "})
    assert reviewed.status_code == 200, reviewed.text
    review = reviewed.json()["review"]
    assert review["status"] == "faux_positif" and review["comment"] == "Taquinerie entre amis."
    assert review["reviewed_by"]["id"] == h.USER_IDS["staff"] and review["reviewed_at"]

    back = _client().patch(url, json={"review_status": "a_traiter"}).json()["review"]
    assert back["status"] == "a_traiter" and back["reviewed_by"] is None and back["reviewed_at"] is None
    assert back["comment"] == "Taquinerie entre amis."
    cleared = _client().patch(url, json={"review_status": "pertinent", "comment": None}).json()["review"]
    assert cleared["comment"] is None

    log = _logs("casier.ai_flag.reviewed")[0]
    assert log["details"]["casier_id"] == flags_data["casier"]
    assert (log["details"]["review_before"], log["details"]["review_after"]) == ("a_traiter", "faux_positif")
    assert log["details"]["comment_length"] == len("Taquinerie entre amis.")
    nova = _client().patch(f"{BASE}/ai-flags/{flags_data['refus']}", json={"review_status": "pertinent"})
    assert nova.status_code == 200
    nova_log = _logs("casier.ai_flag.reviewed")[-1]
    assert "casier_id" not in nova_log["details"] and nova_log["details"]["member_id"] == NOVA

    assert _client().patch(url, json={"review_status": "ouvert"}).status_code == 422
    assert _client().patch(url, json={"review_status": "pertinent", "comment": "x" * 501}).status_code == 422
    assert _client().patch(f"{BASE}/ai-flags/{'e' * 24}", json={"review_status": "pertinent"}).status_code == 404
    assert _client().patch(f"{BASE}/ai-flags/zz", json={"review_status": "pertinent"}).status_code == 400


def test_linked_ai_flag_cannot_become_false_positive():
    casier_id = _insert_casier(MATHIS, name="mathis.b")
    flag_id = _insert_flag(MATHIS)
    assert _post_sanction(casier_id, ai_flag_id=flag_id).status_code == 201

    response = _client().patch(f"{BASE}/ai-flags/{flag_id}", json={"review_status": "faux_positif"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Ce signalement est lié à une sanction : il ne peut pas être classé faux positif."
    assert _detail(casier_id)["ai_flags_open"] == 0


# --------------------------------------------------------------------------------------
# 14. Journal casier.* (auth_logs)
# --------------------------------------------------------------------------------------


def test_every_modification_writes_one_log_entry(monkeypatch, mirror_calls, fake_cdn, casier_http):
    casier_http["members"][ELOISE] = {"user": {"id": ELOISE, "username": "eloise", "global_name": "Éloïse"}}
    client = _client()

    def last_new(expected_type, count_before, status_code, keys):
        logs = _logs()
        assert len(logs) == count_before + 1, [log["event_type"] for log in logs]
        log = logs[-1]
        assert log["event_type"] == expected_type
        assert log["helper_id"] == h.USER_IDS["staff"]
        assert log["status_code"] == status_code
        assert keys <= set(log["details"]), (expected_type, set(log["details"]))
        assert "title" not in log["details"]
        return log

    common = {"casier_id", "member_id", "member_username"}
    sanction_keys = common | {"sanction_id", "sanction_type"}

    created = client.post(BASE, json={"discord_id": ELOISE})
    assert created.status_code == 201, created.text
    casier_id = created.json()["id"]
    last_new("casier.created", 0, 201, common | {"is_prevention"})

    sanction = client.post(f"{BASE}/{casier_id}/sanctions", json={"type": "mute", "reason": "Long motif " * 40,
                                                                   "duration": "10 min"})
    assert sanction.status_code == 201
    sanction_id = sanction.json()["sanctions"][0]["id"]
    log = last_new("casier.sanction.created", 1, 201, sanction_keys | {
        "reason_excerpt", "duration", "status_before", "status_after", "ai_flag_id"})
    assert len(log["details"]["reason_excerpt"]) <= 200
    assert (log["details"]["status_before"], log["details"]["status_after"]) == ("vierge", "mute")

    note = client.post(_note_url(casier_id, sanction_id), json={"content": "Information secrète."})
    note_id = note.json()["sanctions"][0]["notes"][0]["id"]
    log = last_new("casier.sanction.note.created", 2, 201, sanction_keys | {"note_id", "content_length"})
    assert "Information secrète." not in json.dumps(log["details"], ensure_ascii=False)

    client.patch(_note_url(casier_id, sanction_id, note_id), json={"content": "Plus long qu'avant."})
    log = last_new("casier.sanction.note.updated", 3, 200, sanction_keys | {"note_id", "before_length", "after_length"})
    assert (log["details"]["before_length"], log["details"]["after_length"]) == (20, 19)

    client.delete(_note_url(casier_id, sanction_id, note_id))
    last_new("casier.sanction.note.deleted", 4, 200, sanction_keys | {"note_id", "content_length"})

    uploaded = _upload(casier_id, sanction_id, "capture.png", PNG)
    attachment_id = uploaded.json()["sanctions"][0]["attachments"][0]["id"]
    last_new("casier.sanction.attachment.uploaded", 5, 201, sanction_keys | {"attachment_id", "original_filename", "size"})

    client.delete(_attachment_url(casier_id, sanction_id, attachment_id))
    last_new("casier.sanction.attachment.deleted", 6, 200, sanction_keys | {"attachment_id", "original_filename"})

    fiche = client.post(_fiche_url(casier_id), json={"title": "Titre", "content": "Contenu confidentiel"})
    fiche_id = fiche.json()["fiches_s"][0]["id"]
    log = last_new("casier.fiche_s.created", 7, 201, common | {"fiche_id", "fiche_title", "content_length"})
    assert "Contenu confidentiel" not in json.dumps(log["details"], ensure_ascii=False)

    client.patch(_fiche_url(casier_id, fiche_id), json={"title": "Nouveau titre", "content": "Autre contenu"})
    log = last_new("casier.fiche_s.updated", 8, 200, common | {
        "fiche_id", "fiche_title", "previous_title", "before_length", "after_length", "revision_number"})
    assert log["details"]["previous_title"] == "Titre"

    client.patch(_fiche_url(casier_id, fiche_id, "/close"))
    last_new("casier.fiche_s.closed", 9, 200, common | {"fiche_id", "fiche_title"})

    flag_id = _insert_flag(ELOISE)
    client.patch(f"{BASE}/ai-flags/{flag_id}", json={"review_status": "pertinent", "comment": "Vu."})
    last_new("casier.ai_flag.reviewed", 10, 200, common | {"flag_id", "review_before", "review_after", "comment_length"})


def test_failing_audit_log_never_fails_the_request(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("auth_logs indisponible")

    monkeypatch.setattr(audit_service, "log_auth_event", broken)
    casier_id = _insert_casier()

    response = _post_sanction(casier_id)

    assert response.status_code == 201, response.text
    assert len(_stored(casier_id)["sanctions"]) == 1


# --------------------------------------------------------------------------------------
# 15. Discord hors du chemin critique
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [HTTPException(status_code=502, detail="Discord indisponible."),
     httpx.ConnectError("connexion refusée"),
     HTTPException(status_code=500, detail="Configuration Discord manquante.")],
)
def test_detail_falls_back_to_snapshot_when_discord_fails(monkeypatch, failure):
    calls = []

    async def failing(discord_id):
        calls.append(discord_id)
        raise failure

    monkeypatch.setattr(casier, "fetch_guild_member", failing)
    casier_id = _insert_casier(refreshed=False)

    detail = _detail(casier_id)

    assert detail["member"]["display_name"] == "Éloïse"
    assert calls == [ELOISE]
    assert _stored(casier_id)["member_refreshed_at"]


def test_member_refresh_is_spaced(casier_http):
    casier_http["members"][ELOISE] = {"user": {"id": ELOISE, "username": "eloise", "global_name": "Éloïse D."},
                                      "nick": None}
    casier_id = _insert_casier(refreshed=False, is_prevention=True)

    first = _detail(casier_id)
    _detail(casier_id)

    assert len(casier_http["urls"]) == 1
    assert first["member"]["display_name"] == "Éloïse D."
    assert first["is_prevention"] is False

    h.run(h.db.casiers.update_one({"_id": ObjectId(casier_id)}, {"$set": {"member_refreshed_at": _ago(minutes=11)}}))
    _detail(casier_id)
    assert len(casier_http["urls"]) == 2


def test_modification_routes_never_call_discord(monkeypatch, casier_http, mirror_calls):
    casier_http["status"] = 503
    flag_id = _insert_flag(ELOISE)
    casier_id = _insert_casier(refreshed=False)
    client = _client()

    sanction = client.post(f"{BASE}/{casier_id}/sanctions", json={"type": "avertissement", "reason": "Motif.",
                                                                   "ai_flag_id": flag_id})
    assert sanction.status_code == 201, sanction.text
    sanction_id = sanction.json()["sanctions"][0]["id"]
    note = client.post(_note_url(casier_id, sanction_id), json={"content": "Note."})
    assert note.status_code == 201
    note_id = note.json()["sanctions"][0]["notes"][0]["id"]
    assert client.patch(_note_url(casier_id, sanction_id, note_id), json={"content": "Note 2."}).status_code == 200
    assert client.delete(_note_url(casier_id, sanction_id, note_id)).status_code == 200
    uploaded = _upload(casier_id, sanction_id, "capture.png", PNG)
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()["sanctions"][0]["attachments"][0]["id"]
    assert client.delete(_attachment_url(casier_id, sanction_id, attachment_id)).status_code == 200
    fiche = client.post(_fiche_url(casier_id), json={"title": "Fiche", "content": "Contenu"})
    assert fiche.status_code == 201
    fiche_id = fiche.json()["fiches_s"][0]["id"]
    assert client.patch(_fiche_url(casier_id, fiche_id), json={"content": "Contenu 2"}).status_code == 200
    assert client.patch(_fiche_url(casier_id, fiche_id, "/close")).status_code == 200
    other_flag = _insert_flag(ELOISE)
    assert client.patch(f"{BASE}/ai-flags/{other_flag}", json={"review_status": "faux_positif"}).status_code == 200

    assert casier_http["urls"] == []


def test_legacy_invalid_id_in_db_still_never_reaches_discord(casier_http):
    oid = h.run(h.db.casiers.insert_one({
        "discord_id": "../../users/@me-0000",
        "discord_member_snapshot": {"id": "x", "username": "ancien", "display_name": "ancien"},
        "sanctions": [], "fiches_s": [], "created_at": "2026-01-01T00:00:00+00:00",
    })).inserted_id

    response = _client().get(f"{BASE}/{oid}")

    assert response.status_code == 200, response.text
    assert response.json()["member"]["username"] == "ancien"
    assert casier_http["urls"] == []


def test_create_casier_still_checks_discord_before_writing(casier_http):
    casier_http["status"] = 503
    response = _client().post(BASE, json={"discord_id": ELOISE, "username": "eloise"})
    assert response.status_code == 502
    assert h.run(h.db.casiers.count_documents({})) == 0

    casier_http["status"] = None
    created = _client().post(BASE, json={"discord_id": ELOISE, "username": "eloise"})
    assert created.status_code == 201
    duplicate = _client().post(BASE, json={"discord_id": ELOISE, "username": "eloise"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Un casier existe déjà pour ce membre."
    found = _list(q=ELOISE, scope="membre")
    assert [item["member"]["id"] for item in found] == [ELOISE]
    assert found[0]["is_prevention"] is True


# --------------------------------------------------------------------------------------
# Fonctions pures de casier_search
# --------------------------------------------------------------------------------------


def test_parse_terms_and_status_filter():
    assert casier_search.parse_terms("  Éloïse   ÉCART éloïse ") == ["eloise", "ecart"]
    assert casier_search.parse_terms("   ") == []
    assert casier_search.parse_terms(None) == []
    with pytest.raises(HTTPException) as error:
        casier_search.parse_terms("a b c d e f")
    assert error.value.status_code == 422 and error.value.detail == "5 mots maximum."
    assert casier_search.parse_status_filter("banni, mute,") == frozenset({"banni", "mute"})
    assert casier_search.parse_status_filter(" , ") is None
    with pytest.raises(HTTPException) as error:
        casier_search.parse_status_filter("vigilance")
    assert error.value.detail == "Statut inconnu : vigilance."


def test_search_casier_without_terms_matches_everything():
    assert casier_search.search_casier({"discord_id": ELOISE}, [], "tout") == (True, [], 0)
    matched, matches, total = casier_search.search_casier(
        {"discord_id": ELOISE, "discord_member_snapshot": {"username": "kev_42", "display_name": "Kev_42"}},
        ["kev"], "membre",
    )
    assert matched and total == 1
    assert matches[0]["field"] == "display_name"
