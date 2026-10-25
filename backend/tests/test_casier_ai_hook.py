"""Tests hors-ligne du branchement de l'automodération IA sur Iris (services/ai_moderation.py).

Aucun appel Discord ni Anthropic : messages, salons et réponses du modèle sont des SimpleNamespace.
Lancer depuis backend/ : python -m pytest -q -p no:cacheprovider -n 0 tests/test_casier_ai_hook.py
"""
import security_harness as h  # noqa: I001  (doit être importé en premier)

import asyncio
import logging
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import discord
import pytest

import config
from services import ai_moderation as aim
from services import casier_ai_flags as flags

MEMBER = "1153638521786093582"
CHANNEL = "600000000000000101"
THREAD = "600000000000000555"
SKIPPED = "600000000000000888"
ALERT_CHANNEL = "600000000000000009"
ALERT_MESSAGE = "1300000000000002947"
PING_ROLE = 700000000000000001
CREATED = datetime(2026, 10, 25, 17, 0, tzinfo=timezone.utc)
ALERT_URL = f"https://discord.com/channels/{h.GUILD_ID}/{ALERT_CHANNEL}/{ALERT_MESSAGE}"
LOG_TEXT = "Signalement IA non enregistré dans Iris"

_message_ids = iter(range(1300000000000000000, 1300000000000100000))


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    h.reset_db()
    h.reset_discord()
    monkeypatch.setattr(config, "ALLOWED_TICKET_CATEGORY_IDS", frozenset({h.TICKET_CATEGORY_ID}))
    monkeypatch.setattr(config, "AI_MODERATION_FLAG_SKIP_IDS", frozenset(), raising=False)
    monkeypatch.setattr(config, "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT", False, raising=False)
    monkeypatch.setattr(aim, "MODE", "log")
    monkeypatch.setattr(aim, "ALERT_ALL", False)
    monkeypatch.setattr(aim, "PING_ROLE_ID", PING_ROLE)
    monkeypatch.setattr(aim, "PING_MIN_GRAVITY", 1)
    monkeypatch.setattr(aim, "PING_MIN_CONFIDENCE", 0.6)
    monkeypatch.setattr(aim, "ALERT_CHANNEL_ID", int(ALERT_CHANNEL))
    monkeypatch.setattr(aim, "MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(aim, "FLAG_RECORD_TIMEOUT", 5)
    yield


# --------------------------------------------------------------------------- faux objets Discord


def _text_channel(channel_id=CHANNEL, category_id=h.OTHER_CATEGORY_ID, name="général"):
    return SimpleNamespace(id=int(channel_id), name=name, category_id=int(category_id), mention=f"<#{channel_id}>")


def _job(channel=None, *, content="t'es vraiment nul", message_id=None, delete_error=None):
    message_id = message_id or next(_message_ids)
    channel = channel or _text_channel()
    author = SimpleNamespace(
        id=int(MEMBER), name="pseudo", display_name="Pseudo affiché", mention=f"<@{MEMBER}>",
        display_avatar=SimpleNamespace(url=f"https://cdn.discordapp.com/avatars/{MEMBER}/a.png"),
    )
    message = SimpleNamespace(
        id=message_id, author=author, channel=channel, guild=SimpleNamespace(id=int(h.GUILD_ID)),
        clean_content=content, created_at=CREATED,
        jump_url=f"https://discord.com/channels/{h.GUILD_ID}/{channel.id}/{message_id}",
        deleted=False,
    )

    async def _delete():
        if delete_error is not None:
            raise delete_error
        message.deleted = True

    message.delete = _delete
    return SimpleNamespace(message=message, author="Pseudo affiché", channel_name="général", text=content, context=[])


def _verdict(violation=True, gravite=2, confiance=0.88, categorie="insulte"):
    return aim.Verdict(violation=violation, categorie=categorie, gravite=gravite, confiance=confiance,
                       raison="Insulte dirigée", sanction="Avertissement")


def _sent_alert():
    return SimpleNamespace(id=int(ALERT_MESSAGE), channel=SimpleNamespace(id=int(ALERT_CHANNEL)), jump_url=ALERT_URL)


class AlertSpy:
    """Remplace send_alert : enregistre les appels et renvoie un faux message posté (ou None)."""

    def __init__(self, posted=True):
        self.posted = posted
        self.calls: list[dict] = []

    async def __call__(self, job, **kwargs):
        self.calls.append(kwargs)
        return _sent_alert() if self.posted else None


@pytest.fixture
def alerts(monkeypatch):
    spy = AlertSpy()
    monkeypatch.setattr(aim, "send_alert", spy)
    return spy


def _flags() -> list[dict]:
    return h.run(h.db.ai_moderation_flags.find({}, {"_id": 0}).to_list(length=100))


def _response(stop_reason, text=None):
    content = [] if text is None else [SimpleNamespace(type="text", text=text)]
    usage = SimpleNamespace(input_tokens=12, output_tokens=8, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage)


@pytest.fixture
def model(monkeypatch):
    """Client Anthropic factice ; le budget de tokens n'écrit aucun fichier."""
    monkeypatch.setattr(aim, "_budget", SimpleNamespace(ratio=0.0, day="2026-10-25", used=0, add=lambda tokens: None))
    monkeypatch.setattr(aim, "_warned", set())
    monkeypatch.setattr(aim, "_cache_stats", {"calls": 0, "read": 0, "write": 0, "uncached": 0})
    monkeypatch.setattr(aim, "build_system_prompt", lambda: "Règlement de test")

    def _answer(response):
        requests: list[dict] = []

        async def _create(**request):
            requests.append(request)
            return response

        monkeypatch.setattr(aim, "_client", SimpleNamespace(messages=SimpleNamespace(create=_create)))
        return requests

    return _answer


# --------------------------------------------------------------------------- send_alert


class FakeAlertChannel:
    def __init__(self, error=None):
        self.error = error
        self.sent: list[dict] = []

    async def send(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.sent.append(kwargs)
        return _sent_alert()


def _send(job, **overrides):
    kwargs = {"title": " ", "color": discord.Color.orange(), "verdict": _verdict(), "action_line": "Avertissement"}
    kwargs.update(overrides)
    return h.run(aim.send_alert(job, **kwargs))


def test_send_alert_returns_the_posted_message(monkeypatch):
    channel = FakeAlertChannel()

    async def _channel():
        return channel

    monkeypatch.setattr(aim, "_get_alert_channel", _channel)
    sent = _send(_job())
    assert sent is not None and sent.id == int(ALERT_MESSAGE) and sent.jump_url == ALERT_URL
    assert len(channel.sent) == 1
    mentions = channel.sent[0]["allowed_mentions"]
    assert [role.id for role in mentions.roles] == [PING_ROLE]

    sent = _send(_job(), verdict=None, ping=False)
    assert sent is not None
    assert channel.sent[1]["allowed_mentions"].roles is False


def test_send_alert_returns_none_without_channel_or_on_discord_error(monkeypatch, caplog):
    monkeypatch.setattr(aim, "ALERT_CHANNEL_ID", 0)
    assert _send(_job()) is None

    monkeypatch.setattr(aim, "ALERT_CHANNEL_ID", int(ALERT_CHANNEL))
    for error in (
        discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "accès refusé"),
        discord.HTTPException(SimpleNamespace(status=500, reason="Erreur"), "boom"),
    ):
        channel = FakeAlertChannel(error)

        async def _channel(channel=channel):
            return channel

        monkeypatch.setattr(aim, "_get_alert_channel", _channel)
        with caplog.at_level(logging.ERROR, logger="ai_moderation"):
            assert _send(_job()) is None
    assert "Échec de l'envoi de l'alerte" in caplog.text


# --------------------------------------------------------------------------- apply_verdict


def test_log_mode_violation_is_recorded_after_the_alert(alerts):
    job = _job()
    h.run(aim.apply_verdict(job, _verdict()))

    assert len(alerts.calls) == 1 and alerts.calls[0]["ping"] is True
    assert job.message.deleted is False  # mode log : aucune action Discord
    [doc] = _flags()
    assert doc["kind"] == "violation"
    assert doc["discord_id"] == MEMBER
    assert doc["author"] == {
        "id": MEMBER, "username": "pseudo", "display_name": "Pseudo affiché",
        "avatar_url": f"https://cdn.discordapp.com/avatars/{MEMBER}/a.png",
    }
    assert doc["guild_id"] == h.GUILD_ID
    assert doc["channel"] == {"id": CHANNEL, "name": "général", "parent_id": None, "category_id": h.OTHER_CATEGORY_ID}
    assert doc["message"]["id"] == str(job.message.id)
    assert doc["message"]["content"] == "t'es vraiment nul"
    assert doc["message"]["content_redacted"] is False
    assert doc["message"]["created_at"] == CREATED.isoformat()
    assert doc["message"]["jump_url"] == job.message.jump_url
    assert doc["verdict"] == {"violation": True, "categorie": "insulte", "gravite": 2, "confiance": 0.88,
                              "raison": "Insulte dirigée", "sanction": "Avertissement"}
    assert doc["mode"] == "log"
    assert doc["planned_action"] == "delete"
    assert doc["executed"] == []
    assert doc["alert"] == {"posted": True, "channel_id": ALERT_CHANNEL, "message_id": ALERT_MESSAGE,
                            "jump_url": ALERT_URL, "pinged": True}
    assert doc["model"] == "claude-haiku-5-5"
    assert doc["review"] == {"status": "a_traiter", "comment": None, "reviewed_at": None, "reviewed_by": None}
    assert doc["sanction"] is None


@pytest.mark.parametrize(
    ("delete_error", "expected"),
    [
        (None, ["message supprimé"]),
        (discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "absent"), ["message déjà supprimé"]),
        (discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "non"),
         ["suppression impossible (permissions ?)"]),
    ],
)
def test_act_mode_records_executed_actions(monkeypatch, alerts, delete_error, expected):
    monkeypatch.setattr(aim, "MODE", "act")
    job = _job(delete_error=delete_error)
    h.run(aim.apply_verdict(job, _verdict(gravite=2, confiance=0.9)))

    assert len(alerts.calls) == 1
    assert job.message.deleted is (delete_error is None)
    [doc] = _flags()
    assert doc["mode"] == "act"
    assert doc["planned_action"] == "delete"
    assert doc["executed"] == expected


def test_act_mode_alert_only_records_empty_execution(monkeypatch, alerts):
    monkeypatch.setattr(aim, "MODE", "act")
    job = _job()
    h.run(aim.apply_verdict(job, _verdict(gravite=1, confiance=0.7)))

    assert job.message.deleted is False
    [doc] = _flags()
    assert doc["mode"] == "act" and doc["planned_action"] == "alert" and doc["executed"] == []


@pytest.mark.parametrize("mode", ["log", "act"])
@pytest.mark.parametrize(
    "verdict",
    [_verdict(violation=False, gravite=0, categorie="aucune"), _verdict(gravite=0), _verdict(violation=False)],
    ids=["ok", "violation-gravite-0", "gravite-sans-violation"],
)
def test_messages_judged_ok_are_never_recorded(monkeypatch, alerts, mode, verdict):
    monkeypatch.setattr(aim, "MODE", mode)
    monkeypatch.setattr(aim, "ALERT_ALL", True)
    h.run(aim.apply_verdict(_job(), verdict))

    if mode == "log":  # récapitulatif de test toujours posté, sans ping
        assert len(alerts.calls) == 1 and alerts.calls[0]["ping"] is False
    else:
        assert alerts.calls == []
    assert _flags() == []


@pytest.mark.parametrize(
    ("role", "confiance", "posted", "expected"),
    [
        (PING_ROLE, 0.88, True, True),
        (0, 0.88, True, False),           # aucun rôle configuré
        (PING_ROLE, 0.3, True, False),    # confiance sous le seuil de ping
        (PING_ROLE, 0.88, False, False),  # alerte non postée : personne n'a été pingé
    ],
)
def test_pinged_follows_role_thresholds_and_posting(monkeypatch, role, confiance, posted, expected):
    monkeypatch.setattr(aim, "PING_ROLE_ID", role)
    monkeypatch.setattr(aim, "send_alert", AlertSpy(posted=posted))
    h.run(aim.apply_verdict(_job(), _verdict(confiance=confiance)))

    [doc] = _flags()
    assert doc["alert"]["pinged"] is expected
    assert doc["alert"]["posted"] is posted


def test_violation_is_recorded_even_without_alert_channel(monkeypatch, alerts):
    alerts.posted = False  # mode log sans salon d'alerte : le signalement reste visible dans Iris
    h.run(aim.apply_verdict(_job(), _verdict()))

    [doc] = _flags()
    assert doc["alert"] == {"posted": False, "channel_id": None, "message_id": None, "jump_url": None,
                            "pinged": False}


@pytest.mark.parametrize(
    "channel",
    [
        _text_channel(category_id=h.TICKET_CATEGORY_ID, name="ticket-0001"),
        # Fil discord.py : parent_id = salon parent, category_id = catégorie du parent.
        SimpleNamespace(id=int(THREAD), name="fil", parent_id=int(CHANNEL), category_id=int(h.TICKET_CATEGORY_ID),
                        mention=f"<#{THREAD}>"),
        # Objet sans parent_id mais avec un parent : catégorie lue sur le parent.
        SimpleNamespace(id=int(THREAD), name="fil", parent=SimpleNamespace(category_id=int(h.TICKET_CATEGORY_ID)),
                        mention=f"<#{THREAD}>"),
        _text_channel(channel_id=SKIPPED, name="écoute"),
        SimpleNamespace(id=int(THREAD), name="fil", parent_id=int(SKIPPED), category_id=int(h.OTHER_CATEGORY_ID),
                        mention=f"<#{THREAD}>"),
    ],
    ids=["salon-ticket", "fil-ticket", "fil-parent-ticket", "salon-ecoute", "fil-ecoute"],
)
def test_ticket_and_listening_channels_are_never_recorded(monkeypatch, alerts, channel):
    monkeypatch.setattr(config, "AI_MODERATION_FLAG_SKIP_IDS", frozenset({SKIPPED}), raising=False)
    h.run(aim.apply_verdict(_job(channel), _verdict()))

    assert len(alerts.calls) == 1  # l'alerte Discord, elle, est inchangée
    assert _flags() == []


def test_thread_outside_tickets_keeps_parent_and_category(alerts):
    thread = SimpleNamespace(id=int(THREAD), name="fil", parent_id=int(CHANNEL), category_id=int(h.OTHER_CATEGORY_ID),
                             mention=f"<#{THREAD}>")
    h.run(aim.apply_verdict(_job(thread), _verdict()))

    [doc] = _flags()
    assert doc["channel"] == {"id": THREAD, "name": "fil", "parent_id": CHANNEL, "category_id": h.OTHER_CATEGORY_ID}


def test_channel_location_rules():
    assert aim.channel_location(_text_channel()) == (None, int(h.OTHER_CATEGORY_ID))
    thread = SimpleNamespace(parent_id=5, category_id=7, parent=SimpleNamespace(category_id=9))
    assert aim.channel_location(thread) == (5, 7)
    assert aim.channel_location(SimpleNamespace(parent=SimpleNamespace(category_id=9))) == (None, 9)
    assert aim.channel_location(SimpleNamespace()) == (None, None)
    assert aim.channel_location(None) == (None, None)


# --------------------------------------------------------------------------- _process (refus, illisible, verdict)


def test_refusal_is_recorded_without_content_by_default(model, alerts):
    model(_response("refusal"))
    job = _job(content="je n'en peux plus de tout ça")
    h.run(aim._process(job))

    assert len(alerts.calls) == 1 and alerts.calls[0]["verdict"] is None
    [doc] = _flags()
    assert doc["kind"] == "refus"
    assert doc["message"]["content"] is None
    assert doc["message"]["content_redacted"] is True
    assert doc["message"]["jump_url"] == job.message.jump_url
    assert doc["verdict"] is None
    assert doc["planned_action"] is None
    assert doc["executed"] == []
    assert doc["alert"]["posted"] is True and doc["alert"]["pinged"] is True


def test_refusal_content_kept_when_enabled(monkeypatch, model, alerts):
    monkeypatch.setattr(config, "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT", True, raising=False)
    monkeypatch.setattr(aim, "PING_ROLE_ID", 0)
    model(_response("refusal"))
    h.run(aim._process(_job(content="message refusé")))

    [doc] = _flags()
    assert doc["kind"] == "refus"
    assert doc["message"]["content"] == "message refusé"
    assert doc["message"]["content_redacted"] is False
    assert doc["alert"]["pinged"] is False


def test_unreadable_answer_is_recorded_with_content(model, alerts):
    model(_response("end_turn", "Je ne peux pas répondre au format demandé."))
    h.run(aim._process(_job(content="message ambigu")))

    assert len(alerts.calls) == 1
    [doc] = _flags()
    assert doc["kind"] == "illisible"
    assert doc["message"]["content"] == "message ambigu"
    assert doc["message"]["content_redacted"] is False
    assert doc["verdict"] is None
    assert doc["planned_action"] is None


def test_parsed_violation_goes_through_apply_verdict(model, alerts):
    requests = model(_response(
        "end_turn",
        '{"violation": true, "categorie": "menace", "gravite": 3, "confiance": 0.95, '
        '"sanction": "Bannissement", "raison": "Menace explicite"}',
    ))
    h.run(aim._process(_job(content="je vais te retrouver")))

    assert len(requests) == 1
    [doc] = _flags()
    assert doc["kind"] == "violation"
    assert doc["verdict"]["categorie"] == "menace" and doc["verdict"]["gravite"] == 3
    assert doc["planned_action"] == "timeout"
    assert doc["executed"] == []  # mode log


def test_ok_answer_from_the_model_is_not_recorded(monkeypatch, model, alerts):
    monkeypatch.setattr(aim, "ALERT_ALL", True)
    model(_response(
        "end_turn",
        '{"violation": false, "categorie": "aucune", "gravite": 0, "confiance": 0.9, "sanction": "", "raison": "RAS"}',
    ))
    h.run(aim._process(_job(content="bonne soirée à tous")))

    assert len(alerts.calls) == 1
    assert _flags() == []


def test_refusal_in_ticket_category_is_not_recorded(model, alerts):
    model(_response("refusal"))
    h.run(aim._process(_job(_text_channel(category_id=h.TICKET_CATEGORY_ID))))

    assert len(alerts.calls) == 1
    assert _flags() == []


# --------------------------------------------------------------------------- _record_flag : robustesse


def _record(job=None, **overrides):
    kwargs = {"kind": "violation", "verdict": _verdict(), "planned": "alert", "executed": [], "pinged": False,
              "alert_message": None}
    kwargs.update(overrides)
    return h.run(aim._record_flag(job or _job(), **kwargs))


def test_record_flag_returns_id_and_dedupes_on_message():
    job = _job()
    first = _record(job)
    second = _record(job, alert_message=_sent_alert())

    assert first and first == second
    [doc] = _flags()
    assert doc["id"] == first
    assert doc["alert"]["posted"] is False  # le premier enregistrement est conservé


def test_record_flag_sends_plain_data_payload(monkeypatch):
    received: list[dict] = []

    async def _capture(payload):
        received.append(payload)
        return "6718f0c2a1b2c3d4e5f60c01"

    monkeypatch.setattr(flags, "record_ai_flag", _capture)
    monkeypatch.setattr(aim, "MODE", "act")
    job = _job()
    flag_id = _record(job, planned="delete", executed=["message supprimé"], pinged=True, alert_message=_sent_alert())

    assert flag_id == "6718f0c2a1b2c3d4e5f60c01"
    [payload] = received
    assert payload["verdict"] == {"violation": True, "categorie": "insulte", "gravite": 2, "confiance": 0.88,
                                  "raison": "Insulte dirigée", "sanction": "Avertissement"}
    assert payload["discord_id"] == MEMBER and payload["author"]["id"] == MEMBER
    assert payload["guild_id"] == h.GUILD_ID
    assert payload["channel"] == {"id": CHANNEL, "name": "général", "parent_id": None,
                                  "category_id": h.OTHER_CATEGORY_ID}
    assert payload["message"]["id"] == str(job.message.id)
    assert payload["mode"] == "act" and payload["planned_action"] == "delete"
    assert payload["executed"] == ["message supprimé"]
    assert payload["alert"] == {"posted": True, "channel_id": ALERT_CHANNEL, "message_id": ALERT_MESSAGE,
                                "jump_url": ALERT_URL, "pinged": True}

    received.clear()
    _record(job, kind="refus", verdict=None, planned=None)
    assert received[0]["verdict"] is None and received[0]["kind"] == "refus"


def test_record_flag_never_raises_when_recording_fails(monkeypatch, caplog):
    async def _explode(payload):
        raise RuntimeError("Mongo indisponible")

    monkeypatch.setattr(flags, "record_ai_flag", _explode)
    job = _job()
    with caplog.at_level(logging.ERROR, logger="ai_moderation"):
        assert _record(job) is None
    assert f"{LOG_TEXT} (message {job.message.id})" in caplog.text


def test_record_flag_survives_database_errors(monkeypatch):
    class Exploding:
        def __getattr__(self, name):
            raise RuntimeError("base hors service")

    monkeypatch.setattr(flags, "db", SimpleNamespace(ai_moderation_flags=Exploding()))
    assert _record() is None


def test_record_flag_gives_up_after_timeout(monkeypatch, caplog, alerts):
    async def _sleepy(payload):
        await asyncio.sleep(10)
        return "jamais"

    monkeypatch.setattr(flags, "record_ai_flag", _sleepy)
    monkeypatch.setattr(aim, "FLAG_RECORD_TIMEOUT", 0.1)
    job = _job()
    started = time.monotonic()
    with caplog.at_level(logging.ERROR, logger="ai_moderation"):
        h.run(aim.apply_verdict(job, _verdict()))  # le worker rend la main sans exception
    assert time.monotonic() - started < 3
    assert len(alerts.calls) == 1
    assert f"{LOG_TEXT} (message {job.message.id})" in caplog.text


@pytest.mark.parametrize(
    "job",
    [SimpleNamespace(), SimpleNamespace(message=None), SimpleNamespace(message=SimpleNamespace(id=12))],
    ids=["sans-message", "message-none", "message-minimal"],
)
def test_record_flag_tolerates_incomplete_jobs(job):
    assert _record(job) is None
    assert _flags() == []


def test_record_flag_tolerates_broken_message_properties(caplog):
    class BrokenMessage:
        id = 1300000000000009999

        @property
        def clean_content(self):
            raise RuntimeError("cache Discord incomplet")

    with caplog.at_level(logging.ERROR, logger="ai_moderation"):
        assert _record(SimpleNamespace(message=BrokenMessage())) is None
    assert f"{LOG_TEXT} (message 1300000000000009999)" in caplog.text
