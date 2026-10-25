"""Tests hors-ligne du service des signalements IA (services/casier_ai_flags.py).

Lancer depuis backend/ : python -m pytest -q -p no:cacheprovider -n 0 tests/test_casier_ai_flags.py
"""
import security_harness as h  # noqa: I001  (doit être importé en premier)

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import config
from services import casier_ai_flags as flags
from services import casier_service

MEMBER_A = "1153638521786093582"
MEMBER_B = "1153638521786093583"
CHANNEL = "600000000000000101"
THREAD = "600000000000000555"
TICKET_CHANNEL = "600000000000000777"
SKIPPED = "600000000000000888"
NOW = datetime(2026, 10, 25, 17, 0, tzinfo=timezone.utc)
STAFF = {"id": h.USER_IDS["staff"], "username": "staff", "display_name": "Inès (staff)"}
OTHER_STAFF = {"id": h.USER_IDS["responsable"], "username": "lou", "display_name": "Lou"}
HEX_ID = re.compile(r"[0-9a-f]{24}")
OUT_KEYS = {
    "id", "created_at", "discord_id", "author", "channel", "message", "kind", "verdict", "mode",
    "planned_action", "executed", "alert", "model", "review", "sanction", "casier_id", "casier_status",
}

_message_counter = iter(range(1300000000000000000, 1300000000000100000))


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    h.reset_db()
    h.reset_discord()
    monkeypatch.setattr(config, "AI_MODERATION_FLAG_SKIP_IDS", frozenset(), raising=False)
    monkeypatch.setattr(config, "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT", False, raising=False)
    yield


def _payload(member=MEMBER_A, *, kind="violation", content="t'es vraiment nul", message_id=None,
             channel=None, verdict="default", minutes_ago=0, **extra):
    message_id = message_id or str(next(_message_counter))
    created = NOW - timedelta(minutes=minutes_ago)
    payload = {
        "discord_id": member,
        "author": {"id": member, "username": f"user-{member[-2:]}", "display_name": f"Membre {member[-2:]}",
                   "avatar_url": None},
        "guild_id": h.GUILD_ID,
        "channel": channel or {"id": CHANNEL, "name": "général", "parent_id": None,
                               "category_id": h.OTHER_CATEGORY_ID},
        "message": {"id": message_id, "content": content, "created_at": created,
                    "jump_url": f"https://discord.com/channels/{h.GUILD_ID}/{CHANNEL}/{message_id}"},
        "kind": kind,
        "verdict": (
            {"violation": True, "categorie": "insulte", "gravite": 2, "confiance": 0.88,
             "raison": "Insulte dirigée", "sanction": "Avertissement"}
            if verdict == "default" else verdict
        ),
        "mode": "log",
        "planned_action": "alert",
        "executed": [],
        "alert": {"posted": True, "channel_id": "600000000000000009", "message_id": "1300000000000002947",
                  "jump_url": f"https://discord.com/channels/{h.GUILD_ID}/600000000000000009/1300000000000002947",
                  "pinged": True},
        "model": "claude-haiku-5-5",
        "created_at": created,
    }
    payload.update(extra)
    return payload


def _record(*args, **kwargs) -> str | None:
    return h.run(flags.record_ai_flag(_payload(*args, **kwargs)))


def _count(query=None) -> int:
    return h.run(h.db.ai_moderation_flags.count_documents(query or {}))


def _doc(flag_id: str) -> dict:
    return h.run(h.db.ai_moderation_flags.find_one({"id": flag_id}))


def _verdict(categorie="insulte", gravite=2, raison="Insulte dirigée"):
    return {"violation": True, "categorie": categorie, "gravite": gravite, "confiance": 0.8, "raison": raison,
            "sanction": ""}


def _insert_casier(discord_id: str, types=(), oid: ObjectId | None = None) -> str:
    document = {
        "discord_id": discord_id,
        "created_at": NOW.isoformat(),
        "sanctions": [{"id": str(ObjectId()), "type": t, "reason": "Motif", "created_at": NOW.isoformat()}
                      for t in types],
        "fiches_s": [],
    }
    if oid is not None:
        document["_id"] = oid
    return str(h.run(h.db.casiers.insert_one(document)).inserted_id)


def _raises(coroutine) -> HTTPException:
    with pytest.raises(HTTPException) as excinfo:
        h.run(coroutine)
    return excinfo.value


# --------------------------------------------------------------------------- exclusion des salons


def test_is_excluded_location_matches_ticket_categories_and_skip_ids(monkeypatch):
    assert flags.is_excluded_location(CHANNEL, None, h.TICKET_CATEGORY_ID)
    assert flags.is_excluded_location(int(CHANNEL), None, int(h.TICKET_CATEGORY_ID))
    # Fil dont le salon parent est dans la catégorie des tickets.
    assert flags.is_excluded_location(THREAD, TICKET_CHANNEL, h.TICKET_CATEGORY_ID)
    assert not flags.is_excluded_location(CHANNEL, None, h.OTHER_CATEGORY_ID)
    assert not flags.is_excluded_location(None, None, None)

    monkeypatch.setattr(config, "AI_MODERATION_FLAG_SKIP_IDS", frozenset({SKIPPED}), raising=False)
    assert flags.is_excluded_location(SKIPPED, None, h.OTHER_CATEGORY_ID)
    assert flags.is_excluded_location(THREAD, int(SKIPPED), None)
    assert flags.is_excluded_location(CHANNEL, None, SKIPPED)
    assert not flags.is_excluded_location(CHANNEL, None, h.OTHER_CATEGORY_ID)


def test_excluded_ids_are_read_from_config_at_call_time(monkeypatch):
    other_tickets = "200000000000000777"
    assert not flags.is_excluded_location(CHANNEL, None, other_tickets)
    monkeypatch.setattr(config, "ALLOWED_TICKET_CATEGORY_IDS", frozenset({other_tickets}))
    assert flags.is_excluded_location(CHANNEL, None, other_tickets)
    assert not flags.is_excluded_location(CHANNEL, None, h.TICKET_CATEGORY_ID)
    channel = {"id": CHANNEL, "name": "ticket", "parent_id": None, "category_id": other_tickets}
    assert _record(channel=channel) is None
    assert _count() == 0


@pytest.mark.parametrize("channel", [
    {"id": TICKET_CHANNEL, "name": "ticket-0001", "parent_id": None, "category_id": h.TICKET_CATEGORY_ID},
    {"id": THREAD, "name": "fil", "parent_id": TICKET_CHANNEL, "category_id": h.TICKET_CATEGORY_ID},
    {"id": int(TICKET_CHANNEL), "name": "ticket", "parent_id": None, "category_id": int(h.TICKET_CATEGORY_ID)},
    {"id": SKIPPED, "name": "écoute", "parent_id": None, "category_id": h.OTHER_CATEGORY_ID},
    {"id": THREAD, "name": "fil d'écoute", "parent_id": SKIPPED, "category_id": None},
])
def test_record_never_stores_ticket_or_listening_channels(monkeypatch, channel):
    monkeypatch.setattr(config, "AI_MODERATION_FLAG_SKIP_IDS", frozenset({SKIPPED}), raising=False)
    assert _record(channel=channel) is None
    assert _record(channel=channel, kind="refus", verdict=None) is None
    assert _count() == 0


# --------------------------------------------------------------------------- enregistrement


def test_record_creates_document_and_dedupes_on_message_id():
    flag_id = _record(message_id="1300000000000002940")
    assert flag_id and HEX_ID.fullmatch(flag_id)

    doc = _doc(flag_id)
    assert isinstance(doc["created_at"], datetime)
    assert doc["discord_id"] == MEMBER_A
    assert doc["author"] == {"id": MEMBER_A, "username": "user-82", "display_name": "Membre 82", "avatar_url": None}
    assert doc["guild_id"] == h.GUILD_ID
    assert doc["channel"] == {"id": CHANNEL, "name": "général", "parent_id": None,
                              "category_id": h.OTHER_CATEGORY_ID}
    assert doc["message"]["id"] == "1300000000000002940"
    assert doc["message"]["content"] == "t'es vraiment nul"
    assert doc["message"]["content_redacted"] is False
    assert doc["message"]["created_at"] == NOW.isoformat()
    assert doc["message"]["jump_url"].startswith("https://discord.com/channels/")
    assert doc["kind"] == "violation"
    assert doc["verdict"] == {"violation": True, "categorie": "insulte", "gravite": 2, "confiance": 0.88,
                              "raison": "Insulte dirigée", "sanction": "Avertissement"}
    assert doc["mode"] == "log" and doc["planned_action"] == "alert" and doc["executed"] == []
    assert doc["alert"]["posted"] is True and doc["alert"]["pinged"] is True
    assert doc["alert"]["message_id"] == "1300000000000002947"
    assert doc["model"] == "claude-haiku-5-5"
    assert doc["review"] == {"status": "a_traiter", "comment": None, "reviewed_at": None, "reviewed_by": None}
    assert doc["sanction"] is None

    # Même message traité une seconde fois : aucun doublon, même identifiant.
    again = _record(message_id="1300000000000002940", content="autre texte")
    assert again == flag_id
    assert _count() == 1
    assert _doc(flag_id)["message"]["content"] == "t'es vraiment nul"


def test_refusal_content_is_not_kept_by_default(monkeypatch):
    flag_id = _record(kind="refus", content="je n'en peux plus", verdict=_verdict())
    doc = _doc(flag_id)
    assert doc["message"]["content"] is None
    assert doc["message"]["content_redacted"] is True
    assert doc["verdict"] is None
    assert doc["message"]["jump_url"] and doc["author"]["id"] == MEMBER_A

    monkeypatch.setattr(config, "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT", True, raising=False)
    kept = _doc(_record(kind="refus", content="je n'en peux plus", verdict=None))
    assert kept["message"]["content"] == "je n'en peux plus"
    assert kept["message"]["content_redacted"] is False


def test_unreadable_answer_keeps_content_without_verdict():
    doc = _doc(_record(kind="illisible", content="message analysé", verdict=_verdict()))
    assert doc["kind"] == "illisible"
    assert doc["verdict"] is None
    assert doc["message"]["content"] == "message analysé"
    assert doc["message"]["content_redacted"] is False


@pytest.mark.parametrize("overrides", [
    {"verdict": {"violation": False, "categorie": "aucune", "gravite": 0, "confiance": 0.9, "raison": ""}},
    {"verdict": {"violation": True, "categorie": "insulte", "gravite": 0, "confiance": 0.9, "raison": "x"}},
    {"verdict": {"violation": False, "categorie": "insulte", "gravite": 2, "confiance": 0.9, "raison": "x"}},
    {"verdict": None},
    {"kind": "ok"},
    {"member": "abc"},
    {"member": "123"},
    {"message": {"id": None, "content": "x"}},
    {"message": {"id": "pas-un-id", "content": "x"}},
])
def test_messages_judged_ok_or_invalid_payloads_are_not_recorded(overrides):
    overrides = dict(overrides)
    member = overrides.pop("member", MEMBER_A)
    payload = _payload(member)
    payload.update(overrides)
    assert h.run(flags.record_ai_flag(payload)) is None
    assert _count() == 0


@pytest.mark.parametrize("payload", [None, "texte", 42, {}, {"kind": "violation"}])
def test_record_rejects_garbage_payloads(payload):
    assert h.run(flags.record_ai_flag(payload)) is None
    assert _count() == 0


def test_record_truncates_and_cleans_fields():
    @dataclass
    class Verdict:  # comme ai_moderation.Verdict : objet à attributs, pas un dict
        violation: bool
        categorie: str
        gravite: int
        confiance: float
        raison: str
        sanction: str = ""

    flag_id = _record(
        content="x" * 5000,
        verdict=Verdict(True, "c" * 60, 7, 1.7, "r" * 300, "s" * 300),
        mode="autre",
        planned_action="ban",
        executed=["message supprimé"],
        alert={"posted": 1, "jump_url": "http://exemple.org/alerte", "pinged": 0},
        author={"id": MEMBER_A, "username": "u" * 300, "display_name": " Mathis ",
                "avatar_url": "javascript:alert(1)"},
        message={"id": "1300000000000009999", "content": "x" * 5000, "created_at": "2026-10-25T17:00:00+00:00",
                 "jump_url": "javascript:alert(1)"},
    )
    doc = _doc(flag_id)
    assert len(doc["message"]["content"]) == 4000
    assert doc["message"]["jump_url"] is None
    assert doc["message"]["created_at"] == "2026-10-25T17:00:00+00:00"
    assert doc["verdict"]["categorie"] == "c" * 40
    assert doc["verdict"]["gravite"] == 3
    assert doc["verdict"]["confiance"] == 1.0
    assert len(doc["verdict"]["raison"]) == 200 and len(doc["verdict"]["sanction"]) == 200
    assert doc["mode"] == "log"
    assert doc["planned_action"] is None
    assert doc["executed"] == []  # mode log : rien d'exécuté
    assert doc["alert"] == {"posted": True, "channel_id": None, "message_id": None, "jump_url": None,
                            "pinged": False}
    assert len(doc["author"]["username"]) == 100
    assert doc["author"]["display_name"] == "Mathis"
    assert doc["author"]["avatar_url"] is None


def test_record_keeps_executed_actions_in_act_mode():
    actions = ["message supprimé", "timeout 10 min"] + [f"action {i}" for i in range(15)]
    doc = _doc(_record(mode="act", planned_action="timeout", executed=actions))
    assert doc["mode"] == "act" and doc["planned_action"] == "timeout"
    assert doc["executed"][:2] == ["message supprimé", "timeout 10 min"]
    assert len(doc["executed"]) == 10
    # Valeur inattendue (chaîne au lieu d'une liste) : ignorée, le signalement est quand même enregistré.
    assert _doc(_record(mode="act", executed="message supprimé"))["executed"] == []


def test_record_without_created_at_uses_current_time():
    payload = _payload()
    del payload["created_at"]
    before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
    doc = _doc(h.run(flags.record_ai_flag(payload)))
    assert doc["created_at"] >= before


def test_record_never_raises_when_database_fails(monkeypatch, caplog):
    class Exploding:
        async def update_one(self, *args, **kwargs):
            raise RuntimeError("Mongo indisponible")

        async def find_one(self, *args, **kwargs):
            raise RuntimeError("Mongo indisponible")

    monkeypatch.setattr(flags, "db", SimpleNamespace(ai_moderation_flags=Exploding()))
    with caplog.at_level(logging.ERROR, logger=flags.logger.name):
        assert _record() is None
    assert "Signalement IA non enregistré" in caplog.text


def test_record_returns_existing_id_on_concurrent_duplicate(monkeypatch):
    flag_id = _record(message_id="1300000000000004444")
    real = h.db.ai_moderation_flags

    class Racing:
        async def update_one(self, *args, **kwargs):
            raise DuplicateKeyError("E11000 duplicate key error")

        def find_one(self, *args, **kwargs):
            return real.find_one(*args, **kwargs)

    monkeypatch.setattr(flags, "db", SimpleNamespace(ai_moderation_flags=Racing()))
    assert _record(message_id="1300000000000004444") == flag_id


# --------------------------------------------------------------------------- liste, filtres et compteurs


@pytest.fixture
def five_flags():
    """f1..f5, du plus ancien au plus récent."""
    f1 = _record(MEMBER_A, content="Éloïse est vraiment nulle", minutes_ago=50)
    f2 = _record(MEMBER_A, content="achetez mes skins", verdict=_verdict("spam", 1, "Publicité"),
                 minutes_ago=40)
    f3 = _record(MEMBER_B, content="lien steam gratuit", verdict=_verdict("arnaque", 3, "Phishing évident"),
                 minutes_ago=30, author={"id": MEMBER_B, "username": "kev_42", "display_name": "Kévin"})
    f4 = _record(MEMBER_B, kind="refus", content="message de détresse", verdict=None, minutes_ago=20)
    f5 = _record(MEMBER_B, kind="illisible", content="voir axb", verdict=None, minutes_ago=10)
    h.run(flags.review_flag(f2, "pertinent", None, STAFF))
    h.run(flags.review_flag(f3, "faux_positif", "Contexte OK.", STAFF))
    return [f1, f2, f3, f4, f5]


def _ids(filters=None, skip=0, limit=30):
    total, docs = h.run(flags.list_flags(filters, skip, limit))
    return total, [doc["id"] for doc in docs]


def test_list_without_filters_sorted_newest_first(five_flags):
    f1, f2, f3, f4, f5 = five_flags
    assert _ids() == (5, [f5, f4, f3, f2, f1])
    assert _ids({"review_status": "tous", "q": "   ", "discord_id": None}) == (5, [f5, f4, f3, f2, f1])
    total, docs = h.run(flags.list_flags({}))
    assert all("_id" not in doc for doc in docs)


def test_list_pagination(five_flags):
    f1, f2, f3, f4, f5 = five_flags
    assert _ids(limit=2) == (5, [f5, f4])
    assert _ids(skip=2, limit=2) == (5, [f3, f2])
    assert _ids(skip=4) == (5, [f1])
    assert _ids(skip=50) == (5, [])


def test_list_filters(five_flags):
    f1, f2, f3, f4, f5 = five_flags
    assert _ids({"discord_id": MEMBER_A}) == (2, [f2, f1])
    assert _ids({"review_status": "a_traiter"}) == (3, [f5, f4, f1])
    assert _ids({"review_status": "pertinent"}) == (1, [f2])
    assert _ids({"review_status": "faux_positif"}) == (1, [f3])
    # min_gravity exclut les refus et les réponses illisibles.
    assert _ids({"min_gravity": 2}) == (2, [f3, f1])
    assert _ids({"min_gravity": 1}) == (3, [f3, f2, f1])
    assert _ids({"category": "spam"}) == (1, [f2])
    assert _ids({"kind": "refus"}) == (1, [f4])
    assert _ids({"kind": "violation", "discord_id": MEMBER_B}) == (1, [f3])
    assert _ids({"discord_id": MEMBER_B, "review_status": "a_traiter", "kind": "illisible"}) == (1, [f5])


def test_list_text_search_is_accent_and_case_insensitive(five_flags):
    pytest.importorskip("services.casier_text")
    f1, f2, f3, f4, f5 = five_flags
    assert _ids({"q": "eloise"}) == (1, [f1])
    assert _ids({"q": "ÉLOÏSE est"}) == (1, [f1])
    assert _ids({"q": "kevin"}) == (1, [f3])            # author.display_name
    assert _ids({"q": "KEV_42"}) == (1, [f3])           # author.username
    assert _ids({"q": "phishing evident"}) == (1, [f3])  # verdict.raison, chaîne entière
    assert _ids({"q": "86093582"}) == (2, [f2, f1])     # discord_id en sous-chaîne
    assert _ids({"q": "a.b"}) == (0, [])                # caractères spéciaux échappés
    assert _ids({"q": "détresse"}) == (0, [])           # contenu d'un refus jamais conservé
    assert _ids({"q": "eloise", "discord_id": MEMBER_B}) == (0, [])


def test_counts_ignore_review_status_filter(five_flags):
    counts = h.run(flags.counts_for({"discord_id": MEMBER_B, "review_status": "pertinent"}))
    assert counts == {"a_traiter": 2, "pertinent": 0, "faux_positif": 1, "total": 3}
    assert _ids({"discord_id": MEMBER_B, "review_status": "pertinent"}) == (0, [])
    assert h.run(flags.counts_for(None)) == {"a_traiter": 3, "pertinent": 1, "faux_positif": 1, "total": 5}
    assert h.run(flags.counts_for({"kind": "violation", "min_gravity": 2})) == {
        "a_traiter": 1, "pertinent": 0, "faux_positif": 1, "total": 2}


def test_document_without_review_is_read_as_to_do(five_flags):
    h.run(h.db.ai_moderation_flags.insert_one({
        "id": str(ObjectId()), "created_at": NOW.replace(tzinfo=None), "discord_id": MEMBER_A,
        "message": {"id": "1300000000000008888"}, "kind": "violation",
    }))
    assert _ids({"review_status": "a_traiter", "discord_id": MEMBER_A})[0] == 2
    assert h.run(flags.counts_for({"discord_id": MEMBER_A}))["a_traiter"] == 2
    assert h.run(flags.counts_by_discord_ids([MEMBER_A]))[MEMBER_A] == {"total": 3, "open": 2}


def test_counts_by_discord_ids(five_flags):
    expected = {MEMBER_A: {"total": 2, "open": 1}, MEMBER_B: {"total": 3, "open": 2}}
    assert h.run(flags.counts_by_discord_ids([MEMBER_A, MEMBER_B, "1153638521786093599"])) == expected
    assert h.run(flags.counts_by_discord_ids({MEMBER_B})) == {MEMBER_B: expected[MEMBER_B]}
    assert h.run(flags.counts_by_discord_ids(None)) == expected
    assert h.run(flags.counts_by_discord_ids([])) == {}
    assert h.run(flags.counts_by_discord_ids(["", None])) == {}


# --------------------------------------------------------------------------- format de sortie


def test_to_out_hides_internal_fields_and_renders_dates_with_timezone():
    flag_id = _record(message_id="1300000000000002940")
    doc = _doc(flag_id)
    assert doc["created_at"].tzinfo is None  # relu naïf depuis Mongo
    out = flags.to_out(doc, {})
    assert set(out) == OUT_KEYS
    assert out["id"] == flag_id
    assert out["created_at"] == NOW.isoformat()
    assert out["channel"] == {"id": CHANNEL, "name": "général"}
    assert out["alert"] == {"posted": True, "jump_url": doc["alert"]["jump_url"], "pinged": True}
    assert "guild_id" not in out and "_id" not in out
    assert set(out["message"]) == {"id", "content", "content_redacted", "created_at", "jump_url"}
    assert out["review"] == {"status": "a_traiter", "comment": None, "reviewed_at": None, "reviewed_by": None}
    assert out["sanction"] is None
    assert out["casier_id"] is None and out["casier_status"] is None


def test_to_out_tolerates_minimal_legacy_document():
    out = flags.to_out({"id": "a" * 24, "created_at": datetime(2026, 1, 2, 3, 4, 5), "discord_id": MEMBER_A})
    assert set(out) == OUT_KEYS
    assert out["created_at"] == "2026-01-02T03:04:05+00:00"
    assert out["author"] == {"id": MEMBER_A, "username": None, "display_name": None, "avatar_url": None}
    assert out["message"] == {"id": None, "content": None, "content_redacted": False, "created_at": None,
                              "jump_url": None}
    assert out["kind"] == "violation" and out["verdict"] is None and out["mode"] == "log"
    assert out["executed"] == []
    assert out["alert"] == {"posted": False, "jump_url": None, "pinged": False}
    assert out["review"]["status"] == "a_traiter"
    assert out["sanction"] is None


def test_to_out_matches_response_model():
    models = pytest.importorskip("models.casier")
    _insert_casier(MEMBER_A)  # casier vierge : statut identique dans l'ancien et le nouveau calcul
    flag_id = _record()
    h.run(flags.review_flag(flag_id, "pertinent", "Vu.", STAFF))
    out = h.run(flags.get_flag_out(flag_id))
    validated = models.AiFlagOut.model_validate(out).model_dump()
    for key in ("id", "created_at", "discord_id", "kind", "mode", "casier_id"):
        assert validated[key] == out[key]
    refusal = h.run(flags.get_flag_out(_record(kind="refus", verdict=None)))
    assert models.AiFlagOut.model_validate(refusal).message.content_redacted is True


def test_casier_index_uses_compute_status_and_oldest_duplicate(monkeypatch):
    seen = []

    def fake_status(casier):
        seen.append(sorted(s["type"] for s in casier.get("sanctions", [])))
        return "kick" if any(s["type"] == "kick" for s in casier.get("sanctions", [])) else "vierge"

    monkeypatch.setattr(casier_service, "compute_status", fake_status)
    oldest = _insert_casier(MEMBER_A, ["kick"], ObjectId("000000000000000000000001"))
    _insert_casier(MEMBER_A, [], ObjectId("ffffffffffffffffffffffff"))
    index = h.run(flags.casier_index_for([MEMBER_A, MEMBER_B, None]))
    assert index == {MEMBER_A: {"casier_id": oldest, "casier_status": "kick"}}
    assert ["kick"] in seen
    assert h.run(flags.casier_index_for([])) == {}


@pytest.mark.skipif(not hasattr(casier_service, "STATUS_ORDER"),
                    reason="statut « pire sanction » pas encore livré dans casier_service")
def test_casier_status_uses_new_values():
    banned = _insert_casier(MEMBER_A, ["rappel_a_lordre", "avertissement", "bannissement"])
    _insert_casier(MEMBER_B, ["rappel_a_lordre"])
    first, second = _record(MEMBER_A), _record(MEMBER_B)
    out = h.run(flags.get_flag_out(first))
    assert out["casier_id"] == banned and out["casier_status"] == "banni"
    assert h.run(flags.get_flag_out(second))["casier_status"] == "vierge"


def test_get_flag_out_errors_and_success():
    assert _raises(flags.get_flag_out("pas-un-id")).status_code == 400
    assert _raises(flags.get_flag_out("A" * 24)).status_code == 400
    error = _raises(flags.get_flag_out("0" * 24))
    assert (error.status_code, error.detail) == (404, "Signalement introuvable.")
    casier_id = _insert_casier(MEMBER_A, ["avertissement"])
    flag_id = _record()
    out = h.run(flags.get_flag_out(flag_id))
    assert out["id"] == flag_id and out["casier_id"] == casier_id
    assert h.run(flags.get_flag("pas-un-id")) is None
    assert h.run(flags.get_flag(None)) is None


def test_build_list_response_shape(five_flags):
    casier_id = _insert_casier(MEMBER_A, ["avertissement"])
    response = h.run(flags.build_list_response({"review_status": "a_traiter"}, 0, 2))
    assert set(response) == {"total", "counts", "items"}
    assert response["total"] == 3
    assert response["counts"] == {"a_traiter": 3, "pertinent": 1, "faux_positif": 1, "total": 5}
    assert [item["id"] for item in response["items"]] == [five_flags[4], five_flags[3]]
    assert all(set(item) == OUT_KEYS for item in response["items"])
    assert all(item["casier_id"] is None for item in response["items"])  # MEMBER_B n'a pas de casier
    last = h.run(flags.build_list_response({"discord_id": MEMBER_A}))
    assert {item["casier_id"] for item in last["items"]} == {casier_id}


# --------------------------------------------------------------------------- revue


def test_review_flag_sets_and_resets_reviewer():
    flag_id = _record()
    doc, before = h.run(flags.review_flag(flag_id, "pertinent", "  Insulte avérée.  ", STAFF))
    assert before == "a_traiter"
    assert doc["review"]["status"] == "pertinent"
    assert doc["review"]["comment"] == "Insulte avérée."
    assert doc["review"]["reviewed_by"] == STAFF
    assert datetime.fromisoformat(doc["review"]["reviewed_at"]).tzinfo is not None

    # Retour à « À traiter » : relecteur remis à null, commentaire laissé tel quel.
    doc, before = h.run(flags.review_flag(flag_id, "a_traiter", flags.UNCHANGED, OTHER_STAFF))
    assert before == "pertinent"
    assert doc["review"] == {"status": "a_traiter", "comment": "Insulte avérée.", "reviewed_at": None,
                             "reviewed_by": None}

    doc, _ = h.run(flags.review_flag(flag_id, "faux_positif", None, OTHER_STAFF))
    assert doc["review"]["comment"] is None and doc["review"]["reviewed_by"] == OTHER_STAFF
    doc, _ = h.run(flags.review_flag(flag_id, "faux_positif", "   ", OTHER_STAFF))
    assert doc["review"]["comment"] is None
    doc, _ = h.run(flags.review_flag(flag_id, "pertinent", "x" * 600, STAFF))
    assert len(doc["review"]["comment"]) == 500
    out = flags.to_out(doc)
    assert out["review"]["reviewed_by"] == STAFF and out["review"]["reviewed_at"].endswith("+00:00")


def test_review_flag_errors():
    flag_id = _record()
    assert _raises(flags.review_flag("pas-un-id", "pertinent", None, STAFF)).status_code == 400
    assert _raises(flags.review_flag("0" * 24, "pertinent", None, STAFF)).status_code == 404
    error = _raises(flags.review_flag(flag_id, "tous", None, STAFF))
    assert error.status_code == 422
    assert _doc(flag_id)["review"]["status"] == "a_traiter"


def test_linked_flag_cannot_become_false_positive():
    flag_id = _record()
    assert h.run(flags.link_sanction(flag_id, "c" * 24, "d" * 24, STAFF))
    error = _raises(flags.review_flag(flag_id, "faux_positif", "Non", OTHER_STAFF))
    assert error.status_code == 409
    assert error.detail == "Ce signalement est lié à une sanction : il ne peut pas être classé faux positif."
    assert _doc(flag_id)["review"]["status"] == "pertinent"
    # Les autres revues restent possibles.
    doc, before = h.run(flags.review_flag(flag_id, "a_traiter", None, OTHER_STAFF))
    assert before == "pertinent" and doc["review"]["status"] == "a_traiter"


def test_false_positive_refused_when_linked_concurrently(monkeypatch):
    flag_id = _record()
    stale = _doc(flag_id)
    stale.pop("_id")
    h.run(flags.link_sanction(flag_id, "c" * 24, "d" * 24, STAFF))
    real_get = flags.get_flag
    calls = []

    async def get_flag_once_stale(value):
        calls.append(value)
        return dict(stale) if len(calls) == 1 else await real_get(value)

    monkeypatch.setattr(flags, "get_flag", get_flag_once_stale)
    assert _raises(flags.review_flag(flag_id, "faux_positif", None, OTHER_STAFF)).status_code == 409
    assert _doc(flag_id)["review"]["status"] == "pertinent"


# --------------------------------------------------------------------------- lien avec une sanction


def test_check_linkable_errors_in_order():
    flag_id = _record(MEMBER_A)
    assert _raises(flags.check_linkable("xyz", MEMBER_A)).status_code == 400
    error = _raises(flags.check_linkable("0" * 24, MEMBER_A))
    assert (error.status_code, error.detail) == (404, "Signalement introuvable.")
    error = _raises(flags.check_linkable(flag_id, MEMBER_B))
    assert (error.status_code, error.detail) == (422, "Ce signalement ne concerne pas ce membre.")
    assert h.run(flags.check_linkable(flag_id, MEMBER_A))["id"] == flag_id

    h.run(flags.review_flag(flag_id, "faux_positif", None, STAFF))
    error = _raises(flags.check_linkable(flag_id, MEMBER_A))
    assert error.status_code == 409
    assert error.detail == ("Ce signalement a été classé « Faux positif ». "
                            "Changez sa revue avant de sanctionner.")

    linked = _record(MEMBER_A)
    h.run(flags.link_sanction(linked, "c" * 24, "d" * 24, STAFF))
    error = _raises(flags.check_linkable(linked, MEMBER_A))
    assert (error.status_code, error.detail) == (409, "Ce signalement est déjà lié à une sanction.")
    # Autre membre avant « déjà lié ».
    assert _raises(flags.check_linkable(linked, MEMBER_B)).status_code == 422


def test_link_sanction_from_to_do_marks_relevant():
    flag_id = _record()
    result = h.run(flags.link_sanction(flag_id, "c" * 24, "d" * 24, STAFF))
    assert result == {"review_before": "a_traiter", "review_after": "pertinent", "review_changed": True}
    doc = _doc(flag_id)
    assert doc["sanction"] == {"casier_id": "c" * 24, "sanction_id": "d" * 24}
    assert doc["review"]["status"] == "pertinent"
    assert doc["review"]["reviewed_by"] == STAFF
    assert doc["review"]["reviewed_at"]
    out = flags.to_out(doc)
    assert out["sanction"] == {"casier_id": "c" * 24, "sanction_id": "d" * 24}


def test_link_sanction_keeps_existing_relevant_review():
    flag_id = _record()
    h.run(flags.review_flag(flag_id, "pertinent", "Vu par Lou.", OTHER_STAFF))
    reviewed = _doc(flag_id)["review"]
    result = h.run(flags.link_sanction(flag_id, "c" * 24, "d" * 24, STAFF))
    assert result == {"review_before": "pertinent", "review_after": "pertinent", "review_changed": False}
    doc = _doc(flag_id)
    assert doc["sanction"] == {"casier_id": "c" * 24, "sanction_id": "d" * 24}
    assert doc["review"] == reviewed


def test_link_sanction_lost_race_returns_none_and_warns(caplog):
    flag_id = _record()
    assert h.run(flags.link_sanction(flag_id, "c" * 24, "d" * 24, STAFF))
    with caplog.at_level(logging.WARNING, logger=flags.logger.name):
        assert h.run(flags.link_sanction(flag_id, "e" * 24, "f" * 24, OTHER_STAFF)) is None
    assert "non lié" in caplog.text
    assert _doc(flag_id)["sanction"] == {"casier_id": "c" * 24, "sanction_id": "d" * 24}

    false_positive = _record()
    h.run(flags.review_flag(false_positive, "faux_positif", None, STAFF))
    assert h.run(flags.link_sanction(false_positive, "c" * 24, "d" * 24, STAFF)) is None
    assert _doc(false_positive)["sanction"] is None
    assert h.run(flags.link_sanction("0" * 24, "c" * 24, "d" * 24, STAFF)) is None


def test_link_sanction_on_document_without_review():
    flag_id = str(ObjectId())
    h.run(h.db.ai_moderation_flags.insert_one({
        "id": flag_id, "created_at": NOW, "discord_id": MEMBER_A, "message": {"id": "1300000000000007777"},
        "kind": "violation",
    }))
    result = h.run(flags.link_sanction(flag_id, "c" * 24, "d" * 24, STAFF))
    assert result["review_changed"] is True
    assert _doc(flag_id)["review"]["status"] == "pertinent"
