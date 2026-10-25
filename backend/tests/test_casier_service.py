"""Tests hors-ligne du cœur du casier : statut, sanctions, informations complémentaires, fiches S.

Lancer depuis backend/ : python -m pytest -q -p no:cacheprovider -n 0 tests/test_casier_service.py
"""
import security_harness as h  # noqa: I001  (doit rester le premier import)

import json
import re
import sys
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import HTTPException

import services
from models.casier import CasierDetailResponse, CasierListItem, FicheSOut, NoteOut
from models.ticket import AuthenticatedHelper
from services import casier_search, casier_service as cs

HEX24 = re.compile(r"^[0-9a-f]{24}$")
MEMBER_ID = "1153638521786093580"
SNAPSHOT = {"id": MEMBER_ID, "username": "kev_42", "display_name": "Kev_42", "avatar_url": None}
STAFF_A = {"id": h.USER_IDS["staff"], "username": "test-staff", "display_name": "Inès (staff)"}
STAFF_B = {"id": h.USER_IDS["admin"], "username": "test-admin", "display_name": "Lou"}
RESP = {"id": h.USER_IDS["responsable"], "username": "test-responsable", "display_name": "Responsable"}
IRIS_IMAGE = "/api/staff/meetings/images/capture.png"


def viewer(author: dict, responsable: bool = False) -> dict:
    return {"id": author["id"], "is_responsable": responsable}


@pytest.fixture(autouse=True)
def _isolation():
    h.reset_db()
    h.reset_discord()
    yield
    h.reset_db()


@pytest.fixture
def mirror_calls(monkeypatch):
    """Couture de la copie en tâche de fond : les appels sont mémorisés, rien n'est lancé."""
    calls = []
    try:
        from services import casier_attachments
    except Exception:  # module livré par un autre lot : remplacé par un module factice
        casier_attachments = types.ModuleType("services.casier_attachments")
        casier_attachments.schedule_mirror = lambda casier_id, sanction_id: None
        monkeypatch.setitem(sys.modules, "services.casier_attachments", casier_attachments)
        monkeypatch.setattr(services, "casier_attachments", casier_attachments, raising=False)
    monkeypatch.setattr(casier_attachments, "schedule_mirror", lambda c, s: calls.append((c, s)))
    return calls


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _sanction(sanction_type: str, **extra) -> dict:
    return {
        "id": extra.pop("id", cs.new_id()),
        "type": sanction_type,
        "reason": extra.pop("reason", f"Motif {sanction_type}."),
        "created_at": extra.pop("created_at", cs.now_iso()),
        "created_by": extra.pop("created_by", STAFF_A),
        **extra,
    }


def _blocks(*texts: str) -> str:
    return json.dumps([
        {"type": "paragraph", "content": [{"type": "text", "text": text}]} for text in texts
    ])


def _insert(**extra) -> ObjectId:
    document = {
        "discord_id": MEMBER_ID,
        "created_at": cs.now_iso(),
        "status": "vierge",
        "created_by": STAFF_A,
        "discord_member_snapshot": SNAPSHOT,
        "sanctions": [],
        "fiches_s": [],
        **extra,
    }
    return h.run(h.db.casiers.insert_one(document)).inserted_id


def _stored(casier_id: ObjectId) -> dict:
    return h.run(h.db.casiers.find_one({"_id": casier_id}))


def _raises(coroutine) -> HTTPException:
    with pytest.raises(HTTPException) as error:
        h.run(coroutine)
    return error.value


def _fiche(**extra) -> dict:
    return {
        "id": extra.pop("id", cs.new_id()),
        "title": extra.pop("title", "Comportement à suivre"),
        "content": extra.pop("content", "Texte d'origine."),
        "created_at": extra.pop("created_at", cs.now_iso()),
        "created_by": extra.pop("created_by", STAFF_A),
        "active": extra.pop("active", True),
        "closed_at": None,
        "closed_by": None,
        **extra,
    }


# --- Statut ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("types_", "fiches", "expected"),
    [
        ([], [], "vierge"),
        (["rappel_a_lordre"], [], "vierge"),
        ([], [{"active": True}], "vierge"),
        (["avertissement"], [], "averti"),
        (["avertissement", "mute"], [], "mute"),
        (["mute", "kick"], [], "kick"),
        (["rappel_a_lordre", "avertissement", "mute", "kick", "bannissement"], [{"active": True}], "banni"),
        (["inconnu"], [], "vierge"),
        (["avertissement", "inconnu", "rappel_a_lordre"], [], "averti"),
    ],
)
def test_compute_status_is_worst_sanction(types_, fiches, expected):
    casier = {"sanctions": [{"type": t} for t in types_], "fiches_s": fiches}
    assert cs.compute_status(casier) == expected


def test_compute_status_tolerates_legacy_documents():
    assert cs.compute_status({}) == "vierge"
    assert cs.compute_status({"sanctions": None, "fiches_s": None}) == "vierge"
    assert cs.compute_status({"sanctions": ["pas un objet", {"type": ["liste"]}, {"type": "kick"}]}) == "kick"
    assert cs.has_active_fiche_s({"fiches_s": None}) is False


@pytest.mark.parametrize(
    ("types_", "fiches", "expected"),
    [
        ([], [], "vierge"),
        (["rappel_a_lordre"], [], "vigilance"),
        ([], [{"active": True}], "surveillance"),
        ([], [{"active": False}], "vierge"),
        (["rappel_a_lordre"], [{"active": True}], "surveillance"),
        (["avertissement"], [], "surveillance"),
        (["mute"], [], "sanctionne"),
        (["kick"], [{"active": True}], "sanctionne"),
        (["avertissement", "bannissement"], [], "bloque"),
    ],
)
def test_compute_legacy_status_keeps_old_values(types_, fiches, expected):
    casier = {"sanctions": [{"type": t} for t in types_], "fiches_s": fiches}
    assert cs.compute_legacy_status(casier) == expected


def test_status_constants_and_search_filter():
    assert cs.STATUS_ORDER == ("vierge", "averti", "mute", "kick", "banni")
    assert set(cs.STATUS_LABELS) == set(cs.STATUS_ORDER)
    assert cs.STATUS_LABELS["banni"] == "Banni"
    assert set(cs.TYPE_TO_STATUS.values()) <= set(cs.STATUS_ORDER)
    assert cs.SANCTION_TYPES == {"avertissement", "mute", "bannissement", "kick", "rappel_a_lordre"}
    assert casier_search.parse_status_filter("banni,mute") == {"banni", "mute"}


def test_staff_to_author_always_has_a_name():
    helper = AuthenticatedHelper(id=h.USER_IDS["staff"], username="ines", global_name="Inès")
    assert cs.staff_to_author(helper) == {"id": h.USER_IDS["staff"], "username": "ines", "display_name": "Inès"}
    plain = AuthenticatedHelper(id=h.USER_IDS["staff"], username="ines")
    assert cs.staff_to_author(plain)["display_name"] == "ines"
    assert cs.staff_to_author({"id": 42, "username": "x", "display_name": "Lou"}) == {
        "id": "42", "username": "x", "display_name": "Lou",
    }
    assert cs.staff_to_author(SimpleNamespace()) == {"id": None, "username": None, "display_name": None}


# --- Sanctions ---------------------------------------------------------------------------------


def test_add_sanction_positional_call_like_base_seed():
    casier = h.run(cs.add_sanction(MEMBER_ID, "avertissement", "  Spam répété.  ", SNAPSHOT, created_by=STAFF_A))
    assert len(casier["sanctions"]) == 1
    sanction = casier["sanctions"][0]
    assert HEX24.match(sanction["id"])
    assert sanction["reason"] == "Spam répété."
    assert sanction["created_by"] == STAFF_A
    assert sanction["moderator"] is None
    assert sanction["attachments"] == [] and sanction["notes"] == []
    assert sanction["duration"] is None and sanction["duration_seconds"] is None and sanction["expires_at"] is None
    assert sanction["ai_flag_id"] is None and sanction["source"] is None
    assert casier["updated_at"] == sanction["created_at"]
    assert casier["status"] == "vierge"  # champ historique jamais mis à jour

    source = {"channel_id": "1", "message_id": "2", "message_url": None}
    casier = h.run(cs.add_sanction(MEMBER_ID, "kick", "Insultes.", SNAPSHOT, STAFF_A, None, source, "2"))
    assert [s["type"] for s in casier["sanctions"]] == ["avertissement", "kick"]
    assert HEX24.match(casier["sanctions"][1]["id"])
    assert cs.sanction_origin(casier["sanctions"][1]) == "discord_log"
    assert cs.sanction_origin(casier["sanctions"][0]) == "manual"
    assert h.run(h.db.casiers.count_documents({})) == 1


def test_add_sanction_keyword_call_like_bot(mirror_calls):
    expires = _iso(datetime.now(timezone.utc) + timedelta(hours=1))
    files = [
        {"id": "1299887766554433221", "origin": "discord", "filename": "capture.png", "status": "pending",
         "source_url": "https://cdn.discordapp.com/attachments/1/2/capture.png"},
        {"id": "1299887766554433222", "origin": "discord", "filename": "video.mp4", "status": "too_large"},
    ]
    moderator = {"id": "900000000000000001", "username": None, "display_name": None, "extra": "ignoré"}
    kwargs = dict(
        discord_id=MEMBER_ID, sanction_type="mute", reason="Propos humiliants.", snapshot=SNAPSHOT,
        created_by=None, source={"channel_id": "6", "message_id": "77", "message_url": "https://x"},
        dedupe_message_id="77", duration="1 h", duration_seconds=3600, expires_at=expires,
        attachments=files, moderator=moderator,
    )
    casier = h.run(cs.add_sanction(**kwargs))
    sanction = casier["sanctions"][0]
    assert HEX24.match(sanction["id"])
    assert sanction["created_by"] == cs.BOT_AUTHOR
    assert sanction["moderator"] == {"id": "900000000000000001", "username": None, "display_name": None}
    assert (sanction["duration"], sanction["duration_seconds"], sanction["expires_at"]) == ("1 h", 3600, expires)
    assert [a["status"] for a in sanction["attachments"]] == ["pending", "too_large"]
    assert all(a["created_at"] == sanction["created_at"] for a in sanction["attachments"])
    assert files[0].get("created_at") is None  # la liste de l'appelant n'est pas modifiée
    assert mirror_calls == [(str(casier["_id"]), sanction["id"])]
    assert cs.is_sanction_active(sanction) is True

    # Même message traité deux fois : une seule sanction, une seule copie planifiée.
    again = h.run(cs.add_sanction(**kwargs))
    assert len(again["sanctions"]) == 1
    assert mirror_calls == [(str(casier["_id"]), sanction["id"])]


def test_add_sanction_without_files_does_not_schedule(mirror_calls):
    h.run(cs.add_sanction(MEMBER_ID, "kick", "Motif.", SNAPSHOT, attachments=[]))
    h.run(cs.add_sanction(MEMBER_ID, "kick", "Motif.", SNAPSHOT))
    assert mirror_calls == []


def test_add_sanction_normalizes_files(mirror_calls):
    files = ["pas un objet"] + [{"id": str(10**17 + n), "filename": f"f{n}.png"} for n in range(12)]
    casier = h.run(cs.add_sanction(MEMBER_ID, "kick", "Motif.", SNAPSHOT, attachments=files))
    stored = casier["sanctions"][0]["attachments"]
    assert len(stored) == 9  # 10 premiers éléments, dont un ignoré
    assert all(a["status"] == "pending" and a["created_at"] for a in stored)
    assert len(mirror_calls) == 1


@pytest.mark.parametrize(
    ("sanction_type", "kwargs", "expected_label", "expected_seconds", "has_expiry"),
    [
        ("mute", {"duration": "1h30"}, "1 h 30", 5400, True),
        ("mute", {"duration": "  10 minutes "}, "10 min", 600, True),
        ("bannissement", {"duration": "permanent"}, "Permanent", None, False),
        ("mute", {"duration": "jusqu'à nouvel ordre"}, "jusqu'à nouvel ordre", None, False),
        ("mute", {"duration_seconds": 600}, "10 min", 600, True),
        ("mute", {"duration": "   "}, None, None, False),
        ("mute", {"duration": "1 h", "duration_seconds": -5}, "1 h", 3600, True),
        ("avertissement", {"duration": "1h", "duration_seconds": 3600}, None, None, False),
        ("kick", {"duration": "2 jours"}, None, None, False),
    ],
)
def test_add_sanction_duration_rules(sanction_type, kwargs, expected_label, expected_seconds, has_expiry):
    casier = h.run(cs.add_sanction(MEMBER_ID, sanction_type, "Motif.", SNAPSHOT, created_by=STAFF_A, **kwargs))
    sanction = casier["sanctions"][0]
    assert sanction["duration"] == expected_label
    assert sanction["duration_seconds"] == expected_seconds
    if has_expiry:
        created = datetime.fromisoformat(sanction["created_at"])
        assert datetime.fromisoformat(sanction["expires_at"]) == created + timedelta(seconds=expected_seconds)
        assert cs.is_sanction_active(sanction) is True
    else:
        assert sanction["expires_at"] is None
        assert cs.is_sanction_active(sanction) is False


def test_add_sanction_keeps_given_expiry_and_accepts_datetime():
    moment = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    casier = h.run(cs.add_sanction(MEMBER_ID, "mute", "M.", SNAPSHOT, duration="1 h", duration_seconds=3600,
                                   expires_at=moment))
    assert casier["sanctions"][0]["expires_at"] == moment.isoformat()
    huge = h.run(cs.add_sanction("1153638521786093581", "mute", "M.", SNAPSHOT, duration_seconds=10**15))
    assert huge["sanctions"][0]["expires_at"] is None  # dépassement de date : fin inconnue, sanction gardée


def test_add_sanction_validations_and_given_id():
    with pytest.raises(ValueError):
        h.run(cs.add_sanction(MEMBER_ID, "surveillance", "M.", SNAPSHOT))
    with pytest.raises(ValueError):
        h.run(cs.add_sanction(MEMBER_ID, "kick", "M.", SNAPSHOT, sanction_id="../pas-un-id"))
    assert h.run(h.db.casiers.count_documents({})) == 0
    sanction_id = cs.new_id()
    flag_id = cs.new_id()
    casier = h.run(cs.add_sanction(MEMBER_ID, "kick", "M.", SNAPSHOT, STAFF_A, sanction_id=sanction_id,
                                   ai_flag_id=flag_id))
    assert casier["sanctions"][0]["id"] == sanction_id
    assert casier["sanctions"][0]["ai_flag_id"] == flag_id


def test_add_sanction_dedupe_guard_is_atomic(monkeypatch):
    first = h.run(cs.add_sanction(MEMBER_ID, "kick", "M.", SNAPSHOT,
                                  source={"message_id": "55"}, dedupe_message_id="55"))
    stale = {**first, "sanctions": []}

    async def stale_casier(discord_id, snapshot, created_by=None):
        return stale  # lecture faite avant l'écriture d'un traitement concurrent

    monkeypatch.setattr(cs, "get_or_create_casier", stale_casier)
    result = h.run(cs.add_sanction(MEMBER_ID, "kick", "M.", SNAPSHOT,
                                   source={"message_id": "55"}, dedupe_message_id="55"))
    assert len(result["sanctions"]) == 1
    assert len(_stored(first["_id"])["sanctions"]) == 1


def test_add_sanction_survives_mirror_failures(monkeypatch, mirror_calls):
    from services import casier_attachments

    def boom(casier_id, sanction_id):
        raise RuntimeError("pas de boucle")

    monkeypatch.setattr(casier_attachments, "schedule_mirror", boom)
    files = [{"id": "1299887766554433221", "filename": "a.png", "status": "pending"}]
    casier = h.run(cs.add_sanction(MEMBER_ID, "kick", "M.", SNAPSHOT, attachments=files))
    assert casier["sanctions"][0]["attachments"][0]["status"] == "pending"

    # Module de copie absent (import impossible) : la sanction est quand même enregistrée.
    monkeypatch.delattr(services, "casier_attachments", raising=False)
    monkeypatch.setitem(sys.modules, "services.casier_attachments", None)
    casier = h.run(cs.add_sanction(MEMBER_ID, "mute", "M.", SNAPSHOT, attachments=files))
    assert len(casier["sanctions"]) == 2


def test_add_sanction_survives_duration_parser_failure(monkeypatch):
    def boom(text):
        raise RuntimeError("analyse impossible")

    monkeypatch.setattr(cs.casier_log_parser, "parse_duration_text", boom)
    casier = h.run(cs.add_sanction(MEMBER_ID, "mute", "M.", SNAPSHOT, duration="1h30"))
    sanction = casier["sanctions"][0]
    assert (sanction["duration"], sanction["duration_seconds"], sanction["expires_at"]) == ("1h30", None, None)


def test_get_or_create_casier_sets_updated_at_and_refreshes_snapshot():
    created = h.run(cs.get_or_create_casier(MEMBER_ID, SNAPSHOT))
    assert created["created_by"] == cs.BOT_AUTHOR
    assert created["updated_at"] == created["created_at"]
    fresh = {**SNAPSHOT, "display_name": "Kev"}
    again = h.run(cs.get_or_create_casier(MEMBER_ID, fresh, STAFF_A))
    assert again["_id"] == created["_id"]
    assert _stored(created["_id"])["discord_member_snapshot"]["display_name"] == "Kev"
    assert h.run(cs.get_casier_by_discord_id(MEMBER_ID))["_id"] == created["_id"]
    assert h.run(cs.get_casier_by_discord_id("1153638521786093599")) is None


# --- Ids et index ------------------------------------------------------------------------------


def test_ensure_item_ids_assigns_stable_ids():
    casier_id = _insert(
        sanctions=[
            {"type": "avertissement", "reason": "Sans clé.", "created_at": "2025-01-01T00:00:00+00:00"},
            {"id": None, "type": "kick", "reason": "Null.", "created_at": "2025-01-02T00:00:00+00:00"},
            {"id": "", "type": "kick", "reason": "Vide.", "created_at": "2025-01-03T00:00:00+00:00"},
        ],
        fiches_s=[{"title": "Ancienne", "content": "Texte.", "created_at": "2025-01-04T00:00:00+00:00"}],
    )
    casier = h.run(cs.ensure_item_ids(_stored(casier_id)))
    ids = [s["id"] for s in casier["sanctions"]] + [casier["fiches_s"][0]["id"]]
    assert all(HEX24.match(item_id) for item_id in ids) and len(set(ids)) == 4
    again = h.run(cs.ensure_item_ids(_stored(casier_id)))
    assert [s["id"] for s in again["sanctions"]] + [again["fiches_s"][0]["id"]] == ids


def test_index_helpers_raise_404():
    notes = [{"id": "a" * 24, "deleted_at": None}, {"id": "b" * 24, "deleted_at": "2025-01-01"}]
    sanction = _sanction("kick", notes=notes)
    casier = {"sanctions": [{"type": "kick", "id": None}, sanction], "fiches_s": [_fiche(id="c" * 24)]}
    assert cs.sanction_index(casier, sanction["id"]) == 1
    assert cs.fiche_index(casier, "c" * 24) == 0
    assert cs.note_index(sanction, "a" * 24) == 0
    for call, detail in (
        (lambda: cs.sanction_index(casier, "d" * 24), "Sanction introuvable."),
        (lambda: cs.sanction_index(casier, None), "Sanction introuvable."),  # jamais l'élément sans id
        (lambda: cs.sanction_index({}, "d" * 24), "Sanction introuvable."),
        (lambda: cs.fiche_index(casier, "d" * 24), "Fiche S introuvable."),
        (lambda: cs.note_index(sanction, "b" * 24), "Information introuvable."),  # supprimée
        (lambda: cs.note_index({"notes": None}, "a" * 24), "Information introuvable."),
    ):
        with pytest.raises(HTTPException) as error:
            call()
        assert (error.value.status_code, error.value.detail) == (404, detail)


# --- Informations complémentaires --------------------------------------------------------------


def test_add_note_and_details():
    sanction = _sanction("mute")
    casier_id = _insert(sanctions=[_sanction("kick"), sanction])
    casier, details = h.run(cs.add_note(_stored(casier_id), sanction["id"], "  Captures transmises.  ", STAFF_A))
    note = casier["sanctions"][1]["notes"][0]
    assert HEX24.match(note["id"])
    assert note["content"] == "Captures transmises."
    assert note["created_by"] == STAFF_A and note["created_at"] == casier["updated_at"]
    assert note["updated_at"] is None and note["deleted_at"] is None
    assert casier["sanctions"][0].get("notes") is None  # l'autre sanction n'est pas touchée
    assert details == {"sanction_id": sanction["id"], "sanction_type": "mute", "note_id": note["id"],
                       "content_length": len("Captures transmises.")}
    NoteOut.model_validate(cs.note_to_out(note, viewer(STAFF_A)))


def test_add_note_on_legacy_null_notes_and_errors():
    sanction = _sanction("kick", notes=None)
    casier_id = _insert(sanctions=[sanction])
    casier, _ = h.run(cs.add_note(_stored(casier_id), sanction["id"], "Première.", STAFF_A))
    casier, _ = h.run(cs.add_note(casier, sanction["id"], "Seconde.", STAFF_B))
    assert [n["content"] for n in casier["sanctions"][0]["notes"]] == ["Première.", "Seconde."]

    error = _raises(cs.add_note(casier, "f" * 24, "Texte.", STAFF_A))
    assert (error.status_code, error.detail) == (404, "Sanction introuvable.")
    error = _raises(cs.add_note(casier, sanction["id"], "   ", STAFF_A))
    assert error.status_code == 422
    assert len(_stored(casier_id)["sanctions"][0]["notes"]) == 2


def test_update_note_permissions():
    sanction = _sanction("avertissement")
    casier_id = _insert(sanctions=[sanction])
    casier, details = h.run(cs.add_note(_stored(casier_id), sanction["id"], "Avant.", STAFF_A))
    note_id = details["note_id"]

    error = _raises(cs.update_note(casier, sanction["id"], note_id, "Pirate.", STAFF_B, viewer=viewer(STAFF_B)))
    assert (error.status_code, error.detail) == (403, cs.NOTE_EDIT_FORBIDDEN)
    assert _stored(casier_id)["sanctions"][0]["notes"][0]["content"] == "Avant."

    casier, details = h.run(cs.update_note(casier, sanction["id"], note_id, " Après modif. ", STAFF_A,
                                           viewer=viewer(STAFF_A)))
    note = casier["sanctions"][0]["notes"][0]
    assert note["content"] == "Après modif." and note["updated_by"] == STAFF_A and note["updated_at"]
    assert details == {"sanction_id": sanction["id"], "sanction_type": "avertissement", "note_id": note_id,
                       "before_length": 6, "after_length": 12}

    casier, _ = h.run(cs.update_note(casier, sanction["id"], note_id, "Par un responsable.", RESP,
                                     viewer=viewer(RESP, responsable=True)))
    assert casier["sanctions"][0]["notes"][0]["updated_by"] == RESP
    assert cs.note_to_out(casier["sanctions"][0]["notes"][0], viewer(STAFF_B))["can_edit"] is False
    assert cs.note_to_out(casier["sanctions"][0]["notes"][0], viewer(STAFF_A))["can_edit"] is True
    assert cs.note_to_out(casier["sanctions"][0]["notes"][0], viewer(STAFF_B, True))["can_edit"] is True


def test_delete_note_is_soft():
    sanction = _sanction("kick")
    casier_id = _insert(sanctions=[sanction])
    casier, first = h.run(cs.add_note(_stored(casier_id), sanction["id"], "Gardée.", STAFF_A))
    casier, second = h.run(cs.add_note(casier, sanction["id"], "À retirer.", STAFF_A))

    error = _raises(cs.delete_note(casier, sanction["id"], second["note_id"], STAFF_B, viewer=viewer(STAFF_B)))
    assert (error.status_code, error.detail) == (403, cs.NOTE_DELETE_FORBIDDEN)

    casier, details = h.run(cs.delete_note(casier, sanction["id"], second["note_id"], STAFF_A,
                                           viewer=viewer(STAFF_A)))
    notes = casier["sanctions"][0]["notes"]
    assert len(notes) == 2 and notes[1]["deleted_at"] and notes[1]["deleted_by"] == STAFF_A
    assert [n["id"] for n in cs.visible_notes(casier["sanctions"][0])] == [first["note_id"]]
    assert details == {"sanction_id": sanction["id"], "sanction_type": "kick", "note_id": second["note_id"],
                       "content_length": len("À retirer.")}

    for coroutine in (
        cs.delete_note(casier, sanction["id"], second["note_id"], STAFF_A),
        cs.update_note(casier, sanction["id"], second["note_id"], "Retour.", STAFF_A),
    ):
        error = _raises(coroutine)
        assert (error.status_code, error.detail) == (404, "Information introuvable.")


def test_note_write_on_stale_document_rereads_then_404():
    sanction = _sanction("kick")
    casier_id = _insert(sanctions=[sanction])
    casier, details = h.run(cs.add_note(_stored(casier_id), sanction["id"], "Texte.", STAFF_A))
    h.run(cs.delete_note(casier, sanction["id"], details["note_id"], STAFF_A))
    # `casier` est la copie d'avant la suppression : la garde échoue, la relecture voit la note supprimée.
    error = _raises(cs.update_note(casier, sanction["id"], details["note_id"], "Trop tard.", STAFF_A))
    assert error.status_code == 404
    assert _stored(casier_id)["sanctions"][0]["notes"][0]["content"] == "Texte."


class _FlakyCasiers:
    """Collection dont les `failures` premiers `update_one` ne trouvent rien (écriture concurrente)."""

    def __init__(self, real, failures: int):
        self.real = real
        self.failures = failures
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self.real, name)

    async def update_one(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            return SimpleNamespace(matched_count=0, modified_count=0)
        return await self.real.update_one(*args, **kwargs)


def test_guarded_write_retries_once_then_409(monkeypatch):
    sanction = _sanction("kick")
    casier_id = _insert(sanctions=[sanction])

    flaky = _FlakyCasiers(h.db.casiers, failures=1)
    monkeypatch.setattr(cs, "db", SimpleNamespace(casiers=flaky))
    casier, _ = h.run(cs.add_note(_stored(casier_id), sanction["id"], "Après relecture.", STAFF_A))
    assert flaky.calls == 2 and len(casier["sanctions"][0]["notes"]) == 1

    blocked = _FlakyCasiers(h.db.casiers, failures=10)
    monkeypatch.setattr(cs, "db", SimpleNamespace(casiers=blocked))
    error = _raises(cs.add_note(_stored(casier_id), sanction["id"], "Refusée.", STAFF_A))
    assert (error.status_code, error.detail) == (409, "Le casier a changé, réessayez.")
    assert blocked.calls == 2
    assert len(_stored(casier_id)["sanctions"][0]["notes"]) == 1


# --- Fiches S ----------------------------------------------------------------------------------


def test_add_fiche_s_sanitizes_and_extracts_text():
    content = json.dumps([
        {"type": "heading", "content": [{"type": "text", "text": "Contexte"}]},
        {"type": "paragraph", "content": [
            {"type": "link", "href": " JaVaScRiPt:alert(1)", "content": [{"type": "text", "text": "piège"}]},
            {"type": "link", "href": "https://loasis.app", "content": [{"type": "text", "text": "règlement"}]},
        ]},
        {"type": "image", "props": {"url": "https://tracker.example/p.gif"}},
        {"type": "bulletListItem", "content": [{"type": "text", "text": "MP insistants"}]},
    ])
    fiche_id = cs.new_id()
    casier = h.run(cs.add_fiche_s(MEMBER_ID, "  Comportement  ", content, SNAPSHOT, STAFF_A, fiche_id=fiche_id))
    fiche = casier["fiches_s"][0]
    assert fiche["id"] == fiche_id and fiche["title"] == "Comportement"
    blocks = json.loads(fiche["content"])
    assert "javascript" not in fiche["content"].lower()
    assert [block["type"] for block in blocks] == ["heading", "paragraph", "paragraph", "bulletListItem"]
    assert [item.get("href") for item in blocks[1]["content"] if item["type"] == "link"] == ["https://loasis.app"]
    for text in ("Contexte", "piège", "règlement", "MP insistants", "Média externe non affiché"):
        assert text in fiche["content_text"]
    assert fiche["revisions"] == [] and fiche["updated_at"] is None and fiche["updated_by"] is None
    assert fiche["active"] is True and casier["updated_at"] == fiche["created_at"]
    assert cs.compute_status(casier) == "vierge"
    assert cs.fiche_to_out(fiche)["content_format"] == "blocknote"


def test_add_fiche_s_formats_and_empty_content():
    error = _raises(cs.add_fiche_s(MEMBER_ID, "Vide", json.dumps([{"type": "paragraph", "content": []}]),
                                   SNAPSHOT, STAFF_A))
    assert (error.status_code, error.detail) == (422, "La fiche S est vide.")
    assert h.run(h.db.casiers.count_documents({})) == 0  # aucun casier créé pour rien

    image_only = json.dumps([{"type": "image", "props": {"url": IRIS_IMAGE}}])
    casier = h.run(cs.add_fiche_s(MEMBER_ID, "Capture", image_only, SNAPSHOT, STAFF_A))
    casier = h.run(cs.add_fiche_s(MEMBER_ID, "Texte", "Signalé par deux membres.", SNAPSHOT, STAFF_A))
    casier = h.run(cs.add_fiche_s(MEMBER_ID, "Liste", "[1,2]", SNAPSHOT, STAFF_A))
    formats = [cs.fiche_to_out(f)["content_format"] for f in casier["fiches_s"]]
    assert formats == ["blocknote", "text", "text"]
    assert casier["fiches_s"][1]["content_text"] == "Signalé par deux membres."
    assert casier["fiches_s"][2]["content"] == "[1,2]"
    with pytest.raises(ValueError):
        h.run(cs.add_fiche_s(MEMBER_ID, "T", "Texte.", SNAPSHOT, STAFF_A, fiche_id="pas-un-id"))


def test_update_fiche_s_by_author_keeps_revision():
    fiche = _fiche(content=_blocks("Version 1"), content_text="Version 1")
    casier_id = _insert(fiches_s=[fiche])
    casier, changed, details = h.run(cs.update_fiche_s(
        _stored(casier_id), fiche["id"], "Nouveau titre", _blocks("Version 2 plus longue"), STAFF_A,
        viewer=viewer(STAFF_A),
    ))
    assert changed is True
    stored = casier["fiches_s"][0]
    assert stored["title"] == "Nouveau titre"
    assert stored["content_text"] == "Version 2 plus longue"
    assert stored["updated_by"] == STAFF_A and stored["updated_at"] == casier["updated_at"]
    assert stored["revisions"] == [{
        "title": "Comportement à suivre", "content": fiche["content"],
        "updated_at": fiche["created_at"], "updated_by": STAFF_A,
    }]
    assert details == {"fiche_id": fiche["id"], "fiche_title": "Nouveau titre",
                       "previous_title": "Comportement à suivre", "before_length": 9, "after_length": 21,
                       "revision_number": 1}
    out = cs.fiche_to_out(stored, viewer(STAFF_A))
    assert out["revisions_count"] == 1 and "revisions" not in out and out["can_edit"] is True
    assert "revisions" not in FicheSOut.model_validate(out).model_dump()


def test_update_fiche_s_without_real_change_writes_nothing():
    fiche = _fiche(content=json.dumps([{"type": "paragraph", "content": [{"type": "text", "text": "Même"}]}],
                                      indent=2))
    casier_id = _insert(fiches_s=[fiche], updated_at="2025-01-01T00:00:00+00:00")
    before = _stored(casier_id)
    casier, changed, details = h.run(cs.update_fiche_s(
        before, fiche["id"], "Comportement à suivre ", _blocks("Même"), STAFF_A, viewer=viewer(STAFF_A),
    ))
    assert changed is False and "previous_title" not in details
    after = _stored(casier_id)
    assert after == before and "revisions" not in after["fiches_s"][0]


def test_update_fiche_s_permissions():
    active = _fiche()
    closed = _fiche(active=False, closed_at=cs.now_iso(), closed_by=STAFF_A)
    legacy = _fiche(created_by=None)
    casier_id = _insert(fiches_s=[active, closed, legacy])

    cases = [
        (active, STAFF_B, False, 403, cs.FICHE_EDIT_FORBIDDEN),
        (closed, STAFF_A, False, 403, cs.FICHE_CLOSED_EDIT_FORBIDDEN),
        (legacy, STAFF_A, False, 403, cs.FICHE_EDIT_FORBIDDEN),
    ]
    for fiche, author, responsable, code, detail in cases:
        error = _raises(cs.update_fiche_s(_stored(casier_id), fiche["id"], "Autre", None, author,
                                          viewer=viewer(author, responsable)))
        assert (error.status_code, error.detail) == (code, detail)
    assert all("revisions" not in f for f in _stored(casier_id)["fiches_s"])

    for fiche in (active, closed, legacy):
        _, changed, _ = h.run(cs.update_fiche_s(_stored(casier_id), fiche["id"], "Par la responsable", None, RESP,
                                                viewer=viewer(RESP, responsable=True)))
        assert changed is True
    stored = _stored(casier_id)["fiches_s"]
    assert [f["title"] for f in stored] == ["Par la responsable"] * 3
    assert [f["content"] for f in stored] == [active["content"], closed["content"], legacy["content"]]
    assert stored[1]["active"] is False  # modifier ne rouvre pas une fiche clôturée


def test_can_edit_fiche_table():
    active, closed, legacy = _fiche(), _fiche(active=False), _fiche(created_by={"id": None})
    assert cs.can_edit_fiche(active, viewer(STAFF_A)) is True
    assert cs.can_edit_fiche(active, viewer(STAFF_B)) is False
    assert cs.can_edit_fiche(active, viewer(STAFF_B, True)) is True
    assert cs.can_edit_fiche(closed, viewer(STAFF_A)) is False
    assert cs.can_edit_fiche(closed, viewer(STAFF_A, True)) is True
    assert cs.can_edit_fiche(legacy, {"id": None, "is_responsable": False}) is False
    assert cs.fiche_edit_error(active, viewer(STAFF_A)) is None
    assert cs.fiche_edit_error(closed, viewer(STAFF_B)) == cs.FICHE_CLOSED_EDIT_FORBIDDEN


def test_update_fiche_s_validations():
    fiche = _fiche()
    casier_id = _insert(fiches_s=[fiche])
    casier = _stored(casier_id)
    for args, detail in (
        ((None, None), "Rien à modifier."),
        (("   ", None), cs.FICHE_TITLE_EMPTY),
        ((None, json.dumps([{"type": "paragraph"}])), "La fiche S est vide."),
    ):
        error = _raises(cs.update_fiche_s(casier, fiche["id"], *args, STAFF_A))
        assert (error.status_code, error.detail) == (422, detail)
    error = _raises(cs.update_fiche_s(casier, "e" * 24, "Titre", None, STAFF_A))
    assert (error.status_code, error.detail) == (404, "Fiche S introuvable.")


def test_update_fiche_s_keeps_twenty_revisions():
    fiche = _fiche(content="Version 0")
    casier_id = _insert(fiches_s=[fiche])
    casier = _stored(casier_id)
    for number in range(1, 26):
        casier, changed, details = h.run(cs.update_fiche_s(casier, fiche["id"], None, f"Version {number}", STAFF_A))
        assert changed is True
    revisions = casier["fiches_s"][0]["revisions"]
    assert len(revisions) == 20 and details["revision_number"] == 20
    assert [r["content"] for r in revisions] == [f"Version {n}" for n in range(5, 25)]
    assert casier["fiches_s"][0]["content"] == "Version 25"


def test_update_fiche_s_concurrent_edit_keeps_every_version():
    fiche = _fiche(content="Version A")
    casier_id = _insert(fiches_s=[fiche])
    stale = _stored(casier_id)
    h.run(cs.update_fiche_s(_stored(casier_id), fiche["id"], None, "Version B", STAFF_B,
                            viewer=viewer(STAFF_B, True)))
    casier, changed, _ = h.run(cs.update_fiche_s(stale, fiche["id"], None, "Version C", STAFF_A))
    assert changed is True
    stored = casier["fiches_s"][0]
    assert stored["content"] == "Version C"
    assert [r["content"] for r in stored["revisions"]] == ["Version A", "Version B"]
    assert stored["revisions"][1]["updated_by"] == STAFF_B


def test_update_fiche_s_closed_concurrently_rechecks_rights():
    fiche = _fiche()
    casier_id = _insert(fiches_s=[fiche])
    stale = _stored(casier_id)
    assert h.run(cs.close_fiche_s(casier_id, fiche["id"], RESP)) is not None
    error = _raises(cs.update_fiche_s(stale, fiche["id"], "Trop tard", None, STAFF_A, viewer=viewer(STAFF_A)))
    assert (error.status_code, error.detail) == (403, cs.FICHE_CLOSED_EDIT_FORBIDDEN)


def test_fiche_to_out_sanitizes_documents_written_in_database():
    raw = json.dumps([{"type": "paragraph", "content": [
        {"type": "link", "href": "javascript:alert(1)", "content": [{"type": "text", "text": "clic"}]},
    ]}])
    fiche = _fiche(content=raw, revisions=[{"title": "x", "content": "y"}])
    out = cs.fiche_to_out(fiche, viewer(STAFF_B))
    assert "javascript" not in out["content"] and out["content_text"] == "clic"
    assert out["revisions_count"] == 1 and out["can_edit"] is False and out["active"] is True
    model = FicheSOut.model_validate(out)
    assert model.content_format == "blocknote"
    html = cs.fiche_to_out(_fiche(content="<p>Ancien <b>HTML</b></p>"))
    assert html["content_format"] == "html" and html["content_text"].strip() == "Ancien HTML"


def test_close_fiche_s():
    fiche = _fiche()
    casier_id = _insert(fiches_s=[_fiche(id="a" * 24), fiche])
    casier = h.run(cs.close_fiche_s(casier_id, fiche["id"], RESP))
    closed = casier["fiches_s"][1]
    assert closed["active"] is False and closed["closed_by"] == RESP and closed["closed_at"] == casier["updated_at"]
    assert casier["fiches_s"][0]["active"] is True
    assert h.run(cs.close_fiche_s(casier_id, fiche["id"], RESP)) is None  # déjà clôturée
    assert h.run(cs.close_fiche_s(casier_id, "f" * 24, RESP)) is None
    assert h.run(cs.close_fiche_s(ObjectId(), fiche["id"], RESP)) is None


# --- Résumé ------------------------------------------------------------------------------------


def test_summarize_counts_and_dates():
    now = datetime.now(timezone.utc)
    t = [_iso(now - timedelta(days=30 - n)) for n in range(10)]
    future = _iso(now + timedelta(minutes=45))
    later = _iso(now + timedelta(hours=3))
    casier = {
        "_id": ObjectId(),
        "created_at": t[0],
        "sanctions": [
            _sanction("rappel_a_lordre", created_at=t[1]),
            _sanction("avertissement", created_at=t[2], notes=[
                {"id": "a" * 24, "created_at": t[3], "updated_at": t[5]},
            ]),
            _sanction("mute", reason="Mute en cours.", created_at=t[4], expires_at=future),
            _sanction("mute", created_at=t[1], expires_at=later),
            _sanction("mute", created_at=t[1], expires_at=_iso(now - timedelta(hours=1))),
            _sanction("bannissement", created_at=t[1], expires_at=_iso(now + timedelta(days=9))),
            _sanction("inconnu", created_at=t[1]),
        ],
        "fiches_s": [
            _fiche(created_at=t[1], active=False, closed_at=t[6]),
            _fiche(created_at=t[2], updated_at=t[3]),
        ],
    }
    summary = cs.summarize(casier, now)
    assert summary["status"] == "banni"
    assert summary["sanctions_count"] == 7 and summary["rappels_count"] == 1
    assert summary["sanctions_summary"] == {"avertissement": 1, "mute": 3, "kick": 0, "bannissement": 1,
                                            "rappel_a_lordre": 1}
    assert summary["has_active_fiche_s"] is True and summary["active_fiches_s_count"] == 1
    assert summary["last_sanction_at"] == t[4] and summary["last_sanction_label"] == "Mute en cours."
    assert summary["active_mute_until"] == later  # ban et mute expiré ignorés
    assert summary["last_activity_at"] == t[6]

    casier["sanctions"][1]["attachments"] = [
        {"id": "b" * 24, "origin": "upload", "created_at": t[7], "deleted_at": t[8]},
        {"id": "1" * 18, "origin": "discord", "created_at": t[9]},
    ]
    casier["sanctions"][1]["notes"].append({"id": "c" * 24, "created_at": t[4], "deleted_at": t[5]})
    assert cs.summarize(casier, now)["last_activity_at"] == t[8]

    item = CasierListItem.model_validate({
        **cs.summarize(casier, now), "id": str(casier["_id"]), "member": SNAPSHOT, "created_at": t[0],
    })
    assert item.status == "banni" and item.active_mute_until == later
    detail = CasierDetailResponse.model_validate({
        **cs.summarize(casier, now), "id": str(casier["_id"]), "member": SNAPSHOT, "created_at": t[0],
        "sanctions": [], "fiches_s": [],
    })
    assert detail.rappels_count == 1


def test_summarize_empty_and_legacy_casier():
    summary = cs.summarize({"created_at": "2025-01-01T00:00:00+00:00"})
    assert summary == {
        "status": "vierge",
        "sanctions_count": 0,
        "rappels_count": 0,
        "sanctions_summary": {"avertissement": 0, "mute": 0, "kick": 0, "bannissement": 0, "rappel_a_lordre": 0},
        "has_active_fiche_s": False,
        "active_fiches_s_count": 0,
        "last_sanction_at": None,
        "last_sanction_label": "Aucune sanction enregistrée.",
        "last_activity_at": "2025-01-01T00:00:00+00:00",
        "active_mute_until": None,
    }
    naive = cs.summarize({"created_at": datetime(2025, 1, 1), "sanctions": [{"type": "kick", "created_at": "?"}]},
                         datetime(2025, 6, 1))
    assert naive["last_activity_at"] == "2025-01-01T00:00:00+00:00"
    assert naive["last_sanction_at"] == "?" and naive["status"] == "kick"


def test_is_sanction_active_rules():
    now = datetime.now(timezone.utc)
    future, past = _iso(now + timedelta(minutes=5)), _iso(now - timedelta(minutes=5))
    assert cs.is_sanction_active({"type": "mute", "expires_at": future}) is True
    assert cs.is_sanction_active({"type": "bannissement", "expires_at": future}) is True
    assert cs.is_sanction_active({"type": "mute", "expires_at": past}) is False
    assert cs.is_sanction_active({"type": "kick", "expires_at": future}) is False
    assert cs.is_sanction_active({"type": "mute", "expires_at": "illisible"}) is False
    assert cs.is_sanction_active({"type": "mute"}) is False
