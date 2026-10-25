"""Modèles Pydantic du casier (models/casier.py) : exemples du contrat d'API (spec casier, section 3)."""
import copy
from datetime import datetime, timezone

import security_harness as h  # noqa: F401  (environnement de test et chemin du backend)

import pytest
from fastapi import APIRouter
from pydantic import ValidationError

from models import casier as m

CASIER_ID = "6718f0c2a1b2c3d4e5f60718"
SANCTION_ID = "6718f0c2a1b2c3d4e5f60801"
INES = {"id": "400000000000000003", "username": "staff", "display_name": "Inès (staff)"}
BOT = {"id": None, "username": "bot", "display_name": "Bot Modération"}

ATTACHMENT_OUT = {
    "id": "1299887766554433221",
    "origin": "discord",
    "filename": "capture-salon-general.png",
    "content_type": "image/png",
    "size": 1696,
    "status": "stored",
    "error": None,
    "inline": True,
    "download_url": f"/moderation/casiers/{CASIER_ID}/sanctions/{SANCTION_ID}/attachments/1299887766554433221",
    "created_at": "2026-10-25T17:25:00+00:00",
    "uploaded_by": None,
    "can_delete": False,
}

NOTE_OUT = {
    "id": "6718f0c2a1b2c3d4e5f60901",
    "content": "Mute posé via OasisBot. À revoir à la fin du mute.",
    "created_at": "2026-10-25T17:30:00+00:00",
    "created_by": INES,
    "updated_at": None,
    "updated_by": None,
    "can_edit": True,
}

SANCTION_OUT = {
    "id": SANCTION_ID,
    "type": "mute",
    "reason": "Récidive : propos humiliants répétés envers luna.matcha.",
    "created_at": "2026-10-25T17:25:00+00:00",
    "created_by": BOT,
    "moderator": INES,
    "duration": "1 h",
    "duration_seconds": 3600,
    "expires_at": "2026-10-25T18:25:00+00:00",
    "is_active": True,
    "origin": "discord_log",
    "source": {
        "channel_id": "600000000000000004",
        "message_id": "1299887766554433200",
        "message_url": "https://discord.com/channels/100000000000000001/600000000000000004/1299887766554433200",
    },
    "attachments": [ATTACHMENT_OUT],
    "notes": [NOTE_OUT],
    "ai_flag_id": None,
}

FICHE_OUT = {
    "id": "6718f0c2a1b2c3d4e5f60b01",
    "title": "Messages privés insistants",
    "content": '[{"id":"b1","type":"paragraph","props":{},"content":[{"type":"text","text":"Plusieurs"}]}]',
    "content_format": "blocknote",
    "content_text": "Plusieurs nouveaux arrivants…",
    "created_at": "2026-10-24T10:00:00+00:00",
    "created_by": INES,
    "updated_at": "2026-10-25T09:00:00+00:00",
    "updated_by": {"id": "400000000000000004", "username": "lou", "display_name": "Lou"},
    "active": True,
    "closed_at": None,
    "closed_by": None,
    "can_edit": True,
    "revisions_count": 2,
}

SEARCH_MATCH = {
    "kind": "sanction",
    "field": "reason",
    "sanction_id": "6718f0c2a1b2c3d4e5f60802",
    "sanction_type": "avertissement",
    "note_id": None,
    "fiche_id": None,
    "snippet": "Récidive : lien de phishing supprimé.",
    "segments": [
        {"text": "Récidive : lien de ", "match": False},
        {"text": "phishing", "match": True},
        {"text": " supprimé.", "match": False},
    ],
    "created_at": "2026-10-25T17:32:10+00:00",
    "author": INES,
}

LIST_ITEM = {
    "id": CASIER_ID,
    "member": {"id": "1153638521786093580", "username": "kev_42", "display_name": "Kev_42", "avatar_url": None},
    "status": "banni",
    "sanctions_count": 3,
    "rappels_count": 0,
    "has_active_fiche_s": False,
    "active_fiches_s_count": 0,
    "last_sanction_at": "2026-10-25T17:32:10.123456+00:00",
    "last_sanction_label": "Tentative d'arnaque en MP à plusieurs membres.",
    "last_activity_at": "2026-10-25T18:40:00+00:00",
    "created_at": "2026-10-25T17:32:09+00:00",
    "sanctions_summary": {"avertissement": 2, "mute": 0, "kick": 0, "bannissement": 1, "rappel_a_lordre": 0},
    "is_prevention": False,
    "active_mute_until": None,
    "ai_flags_total": 1,
    "ai_flags_open": 0,
    "matches": [SEARCH_MATCH],
    "matches_total": 1,
}

DETAIL = {
    "id": CASIER_ID,
    "member": {"id": "1153638521786093582", "username": "mathis.b", "display_name": "mathis.b", "avatar_url": None},
    "status": "mute",
    "created_at": "2026-10-22T18:00:00+00:00",
    "created_by": INES,
    "sanctions_count": 3,
    "rappels_count": 1,
    "sanctions_summary": {"avertissement": 1, "mute": 1, "kick": 0, "bannissement": 0, "rappel_a_lordre": 1},
    "sanctions": [SANCTION_OUT],
    "fiches_s": [FICHE_OUT],
    "active_fiches_s_count": 0,
    "is_prevention": False,
    "active_mute_until": "2026-10-25T18:25:00+00:00",
    "last_activity_at": "2026-10-25T17:30:00+00:00",
    "ai_flags_total": 2,
    "ai_flags_open": 1,
}

AI_FLAG_ITEM = {
    "id": "6718f0c2a1b2c3d4e5f60c02",
    "created_at": "2026-10-23T16:41:00+00:00",
    "discord_id": "1153638521786093582",
    "author": {"id": "1153638521786093582", "username": "mathis.b", "display_name": "mathis.b", "avatar_url": None},
    "channel": {"id": "600000000000000101", "name": "général"},
    "message": {
        "id": "1300000000000002940",
        "content": "t'es vraiment une sale merde, personne veut de toi ici",
        "content_redacted": False,
        "created_at": "2026-10-23T16:41:00+00:00",
        "jump_url": "https://discord.com/channels/100000000000000001/600000000000000101/1300000000000002940",
    },
    "kind": "violation",
    "verdict": {"violation": True, "categorie": "insulte", "gravite": 2, "confiance": 0.88,
                "raison": "Insulte dirigée et humiliante envers un membre", "sanction": "Avertissement"},
    "mode": "log",
    "planned_action": "alert",
    "executed": [],
    "alert": {"posted": True,
              "jump_url": "https://discord.com/channels/100000000000000001/600000000000000009/1300000000000002947",
              "pinged": True},
    "model": "claude-haiku-5-5",
    "review": {"status": "pertinent", "comment": None, "reviewed_at": "2026-10-23T17:41:00+00:00",
               "reviewed_by": INES},
    "sanction": {"casier_id": CASIER_ID, "sanction_id": "6718f0c2a1b2c3d4e5f60802"},
    "casier_id": CASIER_ID,
    "casier_status": "mute",
}

AI_FLAG_LIST = {
    "total": 4,
    "counts": {"a_traiter": 2, "pertinent": 1, "faux_positif": 1, "total": 4},
    "items": [AI_FLAG_ITEM],
}


def dump(model) -> dict:
    return model.model_dump(mode="json")


# --- Réponses : les exemples de la section 3 passent tels quels (mêmes clés, mêmes valeurs) ---------------


@pytest.mark.parametrize(
    ("model", "example"),
    [
        (m.AttachmentOut, ATTACHMENT_OUT),
        (m.NoteOut, NOTE_OUT),
        (m.SanctionOut, SANCTION_OUT),
        (m.FicheSOut, FICHE_OUT),
        (m.SearchMatch, SEARCH_MATCH),
        (m.CasierListItem, LIST_ITEM),
        (m.CasierDetailResponse, DETAIL),
        (m.AiFlagOut, AI_FLAG_ITEM),
        (m.AiFlagListResponse, AI_FLAG_LIST),
    ],
)
def test_section_3_examples_round_trip(model, example):
    assert dump(model.model_validate(copy.deepcopy(example))) == example


def test_member_author_source_and_creation_shapes():
    member = {"id": "1153638521786093580", "username": "kev_42", "display_name": "Kev_42", "avatar_url": None}
    assert dump(m.CasierMember(**member)) == member
    assert dump(m.MemberSearchResult(**member)) == member
    assert dump(m.SanctionAuthor(**INES)) == INES
    assert dump(m.SanctionAuthor()) == {"id": None, "username": None, "display_name": None}
    assert dump(m.SanctionSource()) == {"channel_id": None, "message_id": None, "message_url": None}
    created = {"id": CASIER_ID, "discord_id": "1153638521786093583", "created_at": "2026-10-25T17:00:00+00:00"}
    assert dump(m.CasierResponse(**created)) == created


def test_bot_response_keeps_exactly_five_fields():
    payload = {
        "discord_id": "1153638521786093582",
        "status": "sanctionne",
        "sanctions_count": 3,
        "has_active_fiche_s": False,
        "sanctions_markdown": "**🔇 Mute** (1 h) — 25/10/2026\n> Récidive",
    }
    assert dump(m.BotCasierResponse(**payload)) == payload
    assert list(m.BotCasierResponse.model_fields) == [
        "discord_id", "status", "sanctions_count", "has_active_fiche_s", "sanctions_markdown",
    ]
    # Valeurs legacy (défaut) et v2 acceptées.
    for status in ("bloque", "surveillance", "vigilance", "banni", "mute", "vierge"):
        assert m.BotCasierResponse(**{**payload, "status": status}).status == status


def test_search_segments_rebuild_snippet():
    match = m.SearchMatch.model_validate(SEARCH_MATCH)
    assert "".join(segment.text for segment in match.segments) == match.snippet
    assert [segment.text for segment in match.segments if segment.match] == ["phishing"]
    member_match = m.SearchMatch(kind="membre", field="discord_id", snippet="1153638521786093580",
                                 segments=[{"text": "1153638521786093580", "match": True}])
    assert member_match.sanction_id is None and member_match.author is None


# --- Réponses : champs internes jamais exposés, lecteurs tolérants --------------------------------------------


def test_internal_fields_are_never_serialized():
    stored_attachment = {
        **ATTACHMENT_OUT,
        "extension": "png",
        "source_url": "https://cdn.discordapp.com/attachments/1/2/capture.png?ex=abc",
        "stored_at": "2026-10-25T17:26:00+00:00",
        "deleted_at": None,
        "deleted_by": None,
    }
    assert "source_url" not in dump(m.AttachmentOut.model_validate(stored_attachment))
    assert dump(m.AttachmentOut.model_validate(stored_attachment)) == ATTACHMENT_OUT

    stored_note = {**NOTE_OUT, "deleted_at": None, "deleted_by": None}
    assert dump(m.NoteOut.model_validate(stored_note)) == NOTE_OUT

    stored_fiche = {**FICHE_OUT, "revisions": [{"title": "Ancien", "content": "ancien"}]}
    assert "revisions" not in dump(m.FicheSOut.model_validate(stored_fiche))


def test_ai_flag_from_stored_document():
    stored = {
        "_id": "objet-mongo",
        "id": "6718f0c2a1b2c3d4e5f60c01",
        "created_at": datetime(2026, 10, 23, 16, 41),  # naïf, comme relu de Mongo
        "discord_id": "1153638521786093582",
        "author": {"id": "1153638521786093582", "username": "mathis.b", "display_name": "mathis.b",
                   "avatar_url": None},
        "guild_id": "100000000000000001",
        "channel": {"id": "600000000000000101", "name": "général", "parent_id": "700000000000000001",
                    "category_id": "700000000000000001"},
        "message": {"id": "1300000000000002950", "content": None, "content_redacted": True,
                    "created_at": "2026-10-23T16:41:00+00:00", "jump_url": "https://discord.com/channels/1/2/3"},
        "kind": "refus",
        "verdict": None,
        "mode": "log",
        "planned_action": None,
        "executed": [],
        "alert": {"posted": True, "channel_id": "600000000000000009", "message_id": "1300000000000002951",
                  "jump_url": "https://discord.com/channels/1/9/4", "pinged": False},
        "model": "claude-haiku-5-5",
        "review": {"status": "a_traiter", "comment": None, "reviewed_at": None, "reviewed_by": None},
        "sanction": None,
    }
    out = dump(m.AiFlagOut.model_validate(stored))
    assert out["created_at"] == "2026-10-23T16:41:00+00:00"
    assert out["channel"] == {"id": "600000000000000101", "name": "général"}
    assert out["alert"] == {"posted": True, "jump_url": "https://discord.com/channels/1/9/4", "pinged": False}
    assert out["message"]["content"] is None and out["message"]["content_redacted"] is True
    assert out["casier_id"] is None and out["casier_status"] is None
    for hidden in ("_id", "guild_id"):
        assert hidden not in out

    aware = datetime(2026, 10, 23, 16, 41, tzinfo=timezone.utc)
    assert m.AiFlagOut.model_validate({**stored, "created_at": aware}).created_at == "2026-10-23T16:41:00+00:00"


def test_ai_flag_tolerates_old_documents():
    minimal = {
        "id": "6718f0c2a1b2c3d4e5f60c03",
        "created_at": datetime(2026, 10, 23, 16, 41, tzinfo=timezone.utc),
        "discord_id": "1153638521786093582",
        "kind": "illisible",
        "message": {"id": "1300000000000002960", "content": "texte", "content_redacted": None},
    }
    out = m.AiFlagOut.model_validate(minimal)
    assert out.message.content_redacted is False
    assert out.review.status == "a_traiter" and out.review.reviewed_by is None
    assert out.executed == [] and out.sanction is None and out.verdict is None
    without_message = m.AiFlagOut.model_validate({k: v for k, v in minimal.items() if k != "message"})
    assert without_message.message.content_redacted is False


def test_sanction_defaults_for_legacy_documents():
    legacy = {"id": SANCTION_ID, "type": "type_inconnu", "reason": "Ancien motif",
              "created_at": "2025-01-01T10:00:00+00:00", "created_by": None}
    out = m.SanctionOut.model_validate(legacy)
    assert out.type == "type_inconnu"
    assert out.origin == "manual" and out.is_active is False
    assert out.attachments == [] and out.notes == []
    assert out.moderator is None and out.duration_seconds is None and out.expires_at is None


def test_computed_values_are_constrained():
    with pytest.raises(ValidationError):
        m.CasierListItem.model_validate({**LIST_ITEM, "status": "surveillance"})
    with pytest.raises(ValidationError):
        m.CasierDetailResponse.model_validate({**DETAIL, "status": "vigilance"})
    with pytest.raises(ValidationError):
        m.SanctionOut.model_validate({**SANCTION_OUT, "origin": "bot"})
    with pytest.raises(ValidationError):
        m.FicheSOut.model_validate({**FICHE_OUT, "content_format": "markdown"})
    with pytest.raises(ValidationError):
        m.SearchMatch.model_validate({**SEARCH_MATCH, "kind": "fichier"})
    with pytest.raises(ValidationError):
        m.SearchMatch.model_validate({**SEARCH_MATCH, "field": "content_text"})
    with pytest.raises(ValidationError):
        m.AiFlagOut.model_validate({**AI_FLAG_ITEM, "casier_status": "bloque"})


def test_datetimes_are_rendered_with_timezone():
    naive = datetime(2026, 10, 25, 18, 25)
    assert m.iso_datetime(naive) == "2026-10-25T18:25:00+00:00"
    assert m.iso_datetime("2026-10-25T18:25:00+00:00") == "2026-10-25T18:25:00+00:00"
    assert m.iso_datetime(None) is None
    out = m.SanctionOut.model_validate({**SANCTION_OUT, "expires_at": naive})
    assert out.expires_at == "2026-10-25T18:25:00+00:00"


# --- Requêtes : exemples et limites de longueur ------------------------------------------------------------


def test_create_casier_payload_unchanged():
    payload = m.CreateCasierPayload(discord_id="1153638521786093583", username="nova.lune")
    assert payload.username == "nova.lune"
    assert m.CreateCasierPayload(discord_id="1153638521786093583").username is None
    for bad in ({"discord_id": "1234"}, {"discord_id": "1" * 22},
                {"discord_id": "1153638521786093583", "username": ""},
                {"discord_id": "1153638521786093583", "username": "x" * 81}):
        with pytest.raises(ValidationError):
            m.CreateCasierPayload(**bad)


def test_create_sanction_payload_example_and_limits():
    payload = m.CreateSanctionPayload(type="mute", reason="Propos humiliants en vocal.", duration="1h30",
                                      ai_flag_id="6718f0c2a1b2c3d4e5f60c02")
    assert dump(payload) == {"type": "mute", "reason": "Propos humiliants en vocal.", "duration": "1h30",
                             "ai_flag_id": "6718f0c2a1b2c3d4e5f60c02"}

    stripped = m.CreateSanctionPayload(type="avertissement", reason="  Motif  ", duration="   ")
    assert stripped.reason == "Motif" and stripped.duration is None and stripped.ai_flag_id is None
    assert m.CreateSanctionPayload(type="kick", reason="x" * 1000).reason == "x" * 1000
    assert m.CreateSanctionPayload(type="mute", reason="r", duration=" " + "d" * 80 + " ").duration == "d" * 80

    # Type inconnu et identifiant mal formé : refusés par le router (422 et 400 avec message dédié), pas ici.
    assert m.CreateSanctionPayload(type="inconnu", reason="r", ai_flag_id="../x").ai_flag_id == "../x"

    for bad in ({"type": "mute", "reason": "   "}, {"type": "mute", "reason": ""},
                {"type": "mute", "reason": "x" * 1001}, {"type": "mute", "reason": "r", "duration": "d" * 81},
                {"type": "t" * 41, "reason": "r"}, {"reason": "r"}, {"type": "mute"}):
        with pytest.raises(ValidationError):
            m.CreateSanctionPayload(**bad)


def test_note_payload_limits():
    assert m.NotePayload(content="  Captures transmises par mathis.b.  ").content == "Captures transmises par mathis.b."
    assert len(m.NotePayload(content="n" * 4000).content) == 4000
    for bad in ("", "   \n ", "n" * 4001):
        with pytest.raises(ValidationError):
            m.NotePayload(content=bad)


def test_fiche_s_payloads_limits():
    content = '[{"type":"paragraph","content":[{"type":"text","text":"Suivi"}]}]'
    created = m.CreateFicheSPayload(title=" Comportement à suivre ", content=content)
    assert created.title == "Comportement à suivre" and created.content == content
    assert len(m.CreateFicheSPayload(title="t" * 160, content="c" * 200_000).content) == 200_000
    for bad in ({"title": "", "content": "c"}, {"title": "  ", "content": "c"}, {"title": "t" * 161, "content": "c"},
                {"title": "t", "content": ""}, {"title": "t", "content": "c" * 200_001}, {"title": "t"}):
        with pytest.raises(ValidationError):
            m.CreateFicheSPayload(**bad)

    assert m.UpdateFicheSPayload().is_empty()
    assert m.UpdateFicheSPayload(title=None, content=None).is_empty()
    assert not m.UpdateFicheSPayload(title="Nouveau titre").is_empty()
    assert not m.UpdateFicheSPayload(content=content).is_empty()
    for bad in ({"title": ""}, {"title": "t" * 161}, {"content": ""}, {"content": "c" * 200_001}):
        with pytest.raises(ValidationError):
            m.UpdateFicheSPayload(**bad)


def test_review_payload_example_and_limits():
    payload = m.ReviewAiFlagPayload(review_status="faux_positif", comment="Taquinerie entre amis, contexte OK.")
    assert payload.comment == "Taquinerie entre amis, contexte OK." and payload.comment_provided

    cleared = m.ReviewAiFlagPayload.model_validate({"review_status": "a_traiter", "comment": None})
    assert cleared.comment is None and cleared.comment_provided
    blank = m.ReviewAiFlagPayload.model_validate({"review_status": "pertinent", "comment": "   "})
    assert blank.comment is None and blank.comment_provided
    absent = m.ReviewAiFlagPayload.model_validate({"review_status": "pertinent"})
    assert absent.comment is None and not absent.comment_provided

    for bad in ({"review_status": "tous"}, {"review_status": "invalide"}, {},
                {"review_status": "pertinent", "comment": "c" * 501}):
        with pytest.raises(ValidationError):
            m.ReviewAiFlagPayload.model_validate(bad)


def test_identifier_patterns():
    assert m.HEX_ID_PATTERN.fullmatch(SANCTION_ID)
    for bad in ("6718F0C2A1B2C3D4E5F60801", "6718f0c2", "../x", SANCTION_ID + "0"):
        assert not m.HEX_ID_PATTERN.fullmatch(bad)
    assert m.ATTACHMENT_ID_PATTERN.fullmatch("1299887766554433221")
    assert m.ATTACHMENT_ID_PATTERN.fullmatch(SANCTION_ID)
    for bad in ("../x", "1234", "x" * 24, "1" * 21):
        assert not m.ATTACHMENT_ID_PATTERN.fullmatch(bad)


# --- Intégration FastAPI : 422 standard, filtrage des réponses, schéma OpenAPI -------------------------------


def _models_router() -> APIRouter:
    router = APIRouter(prefix="/modeles")

    @router.post("/sanctions", response_model=m.CasierDetailResponse, status_code=201)
    async def create_sanction(payload: m.CreateSanctionPayload):
        detail = copy.deepcopy(DETAIL)
        detail["sanctions"][0]["reason"] = payload.reason
        detail["sanctions"][0]["attachments"][0]["source_url"] = "https://cdn.discordapp.com/attachments/1/2/a.png"
        detail["fiches_s"][0]["revisions"] = [{"title": "Ancien", "content": "ancien"}]
        return detail

    @router.post("/notes", response_model=m.NoteOut)
    async def create_note(payload: m.NotePayload):
        return {**NOTE_OUT, "content": payload.content, "deleted_at": None}

    @router.post("/fiches", response_model=m.FicheSOut)
    async def create_fiche(payload: m.CreateFicheSPayload):
        return FICHE_OUT

    @router.patch("/fiches", response_model=m.FicheSOut)
    async def update_fiche(payload: m.UpdateFicheSPayload):
        return FICHE_OUT

    @router.patch("/revue", response_model=m.AiFlagOut)
    async def review(payload: m.ReviewAiFlagPayload):
        return {**AI_FLAG_ITEM, "guild_id": "100000000000000001"}

    @router.get("/signalements", response_model=m.AiFlagListResponse)
    async def flags(review_status: m.AiFlagReviewFilter = "tous", kind: m.AiFlagKind | None = None,
                    scope: m.SearchScope = "tout", sort: m.CasierSort = "recent"):
        return AI_FLAG_LIST

    @router.get("/liste", response_model=list[m.CasierListItem])
    async def casiers():
        return [LIST_ITEM]

    @router.get("/bot", response_model=m.BotCasierResponse)
    async def bot():
        return {"discord_id": "1153638521786093582", "status": "vierge", "sanctions_count": 0,
                "has_active_fiche_s": False, "sanctions_markdown": "*Aucune sanction enregistrée.*"}

    @router.post("/casiers", response_model=m.CasierResponse)
    async def create_casier(payload: m.CreateCasierPayload):
        return {"id": CASIER_ID, "discord_id": payload.discord_id, "created_at": "2026-10-25T17:00:00+00:00"}

    @router.get("/membres", response_model=list[m.MemberSearchResult])
    async def members():
        return []

    return router


def test_models_through_fastapi():
    client = h.make_client(_models_router())

    response = client.post("/api/modeles/sanctions", json={"type": "mute", "reason": "  Motif  ", "duration": "1h"})
    assert response.status_code == 201
    body = response.json()
    assert body["sanctions"][0]["reason"] == "Motif"
    assert "source_url" not in body["sanctions"][0]["attachments"][0]
    assert "revisions" not in body["fiches_s"][0]

    invalid = client.post("/api/modeles/sanctions", json={"type": "mute", "reason": "   "})
    assert invalid.status_code == 422 and isinstance(invalid.json()["detail"], list)
    assert client.post("/api/modeles/notes", json={"content": "n" * 4001}).status_code == 422
    assert client.post("/api/modeles/notes", json={"content": " ok "}).json()["content"] == "ok"
    assert "deleted_at" not in client.post("/api/modeles/notes", json={"content": "ok"}).json()
    assert client.post("/api/modeles/fiches", json={"title": "t" * 161, "content": "c"}).status_code == 422
    assert client.patch("/api/modeles/fiches", json={}).status_code == 200  # « Rien à modifier. » : router
    assert client.patch("/api/modeles/revue", json={"review_status": "tous"}).status_code == 422
    assert "guild_id" not in client.patch("/api/modeles/revue", json={"review_status": "pertinent"}).json()

    assert client.get("/api/modeles/signalements").json() == AI_FLAG_LIST
    assert client.get("/api/modeles/signalements", params={"review_status": "inconnu"}).status_code == 422
    assert client.get("/api/modeles/signalements", params={"kind": "ok"}).status_code == 422
    assert client.get("/api/modeles/signalements", params={"scope": "partout"}).status_code == 422
    assert client.get("/api/modeles/signalements", params={"sort": "alpha"}).status_code == 422
    assert client.get("/api/modeles/liste").json() == [LIST_ITEM]
    assert set(client.get("/api/modeles/bot").json()) == {
        "discord_id", "status", "sanctions_count", "has_active_fiche_s", "sanctions_markdown",
    }

    schema = client.app.openapi()
    components = schema["components"]["schemas"]
    for name in ("CasierDetailResponse", "SanctionOut", "AttachmentOut", "NoteOut", "FicheSOut", "AiFlagOut",
                 "AiFlagListResponse", "CasierListItem", "SearchMatch", "CreateSanctionPayload", "NotePayload",
                 "CreateFicheSPayload", "UpdateFicheSPayload", "ReviewAiFlagPayload", "CreateCasierPayload"):
        assert name in components or f"{name}-Input" in components or f"{name}-Output" in components
