"""Tests de sécurité hors-ligne : accès aux tickets d'écoute (H1, H2, L7, L2).

Lancement : cd backend && python -m pytest -q -p no:cacheprovider -n 0 tests/test_security_tickets.py
"""
import security_harness as h

import json

import pytest
from fastapi import HTTPException

import config
from routers import members, tickets
from services import discord_service
from services.discord_service import DiscordService, ensure_discord_id

TICKET_CHANNEL_ID = "500000000000000001"
OTHER_CHANNEL_ID = "500000000000000002"
PARENT_TEXT_CHANNEL_ID = "500000000000000003"
THREAD_CHANNEL_ID = "500000000000000004"
MEMBER_ID = h.USER_IDS["member"]

ALLOWED_ROLES = ["helper", "admin", "responsable"]
FORBIDDEN_ROLES = ["staff", "animateur", "operateur"]


def raw_message(message_id: str, content: str) -> dict:
    return {
        "id": message_id,
        "content": content,
        "timestamp": "2026-10-01T10:00:00+00:00",
        "author": {"id": MEMBER_ID, "username": "membre"},
    }


@pytest.fixture
def client():
    h.reset_db()
    h.reset_discord()
    h.fake_discord.add_channel(TICKET_CHANNEL_ID, parent_id=h.TICKET_CATEGORY_ID, name="ticket-0001")
    h.fake_discord.add_channel(OTHER_CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="staff-prive")
    h.fake_discord.messages[TICKET_CHANNEL_ID] = [raw_message("600000000000000001", "Bonjour, j'ai besoin d'aide")]
    h.fake_discord.messages[OTHER_CHANNEL_ID] = [raw_message("600000000000000002", "Discussion staff confidentielle")]
    return h.make_client(tickets.router, members.router)


def create_ticket(client, role: str = "helper", channel_id: str = TICKET_CHANNEL_ID):
    return client.post(
        "/api/tickets",
        json={"member_id": MEMBER_ID, "channel_id": channel_id},
        cookies=h.session_cookies(role),
    )


def seed_ticket(client) -> dict:
    response = create_ticket(client, "helper")
    assert response.status_code == 201, response.text
    return response.json()


def ticket_requests(ticket_id: str, note_id: str = "note-inexistante"):
    return [
        ("get", "/api/tickets", None),
        ("get", "/api/tickets/stats", None),
        ("get", f"/api/tickets/{ticket_id}", None),
        ("patch", f"/api/tickets/{ticket_id}", {"notes": "modifié"}),
        ("post", f"/api/tickets/{ticket_id}/notes", {"title": "t", "content": "c"}),
        ("delete", f"/api/tickets/{ticket_id}/notes/{note_id}", None),
        ("post", f"/api/tickets/{ticket_id}/sync", None),
        ("post", f"/api/tickets/{ticket_id}/ai-summary/stream", None),
        ("post", "/api/tickets", {"member_id": MEMBER_ID, "channel_id": OTHER_CHANNEL_ID}),
        ("get", f"/api/members/{MEMBER_ID}", None),
    ]


def sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def send(client, method: str, path: str, body, role: str | None):
    cookies = h.session_cookies(role) if role else None
    kwargs = {"cookies": cookies}
    if body is not None:
        kwargs["json"] = body
    return client.request(method.upper(), path, **kwargs)


# --- H1 : les rôles sans accès aux tickets reçoivent 403 sur toutes les routes ---

@pytest.mark.parametrize("role", FORBIDDEN_ROLES)
def test_roles_without_ticket_access_are_forbidden_everywhere(client, role):
    ticket = seed_ticket(client)
    note = client.post(
        f"/api/tickets/{ticket['id']}/notes",
        json={"title": "Note", "content": "Contenu sensible"},
        cookies=h.session_cookies("helper"),
    ).json()

    for method, path, body in ticket_requests(ticket["id"], note["id"]):
        response = send(client, method, path, body, role)
        assert response.status_code == 403, (role, method, path, response.status_code, response.text)
        assert "Contenu sensible" not in response.text
        assert "besoin d'aide" not in response.text

    stored = h.run(h.db.tickets.find_one({"id": ticket["id"]}, {"_id": 0}))
    assert stored["notes"] == ""
    assert len(stored["notes_entries"]) == 1
    assert h.run(h.db.tickets.count_documents({})) == 1

    forbidden_logs = h.run(
        h.db.auth_logs.count_documents({"event_type": "authz.forbidden", "helper_id": h.USER_IDS[role]})
    )
    assert forbidden_logs >= len(ticket_requests(ticket["id"]))


def test_member_without_iris_role_is_forbidden(client):
    ticket = seed_ticket(client)
    for method, path, body in ticket_requests(ticket["id"]):
        assert send(client, method, path, body, "member").status_code == 403, path


def test_anonymous_requests_get_401(client):
    ticket = seed_ticket(client)
    for method, path, body in ticket_requests(ticket["id"]):
        assert send(client, method, path, body, None).status_code == 401, path


@pytest.mark.parametrize("role", ALLOWED_ROLES)
def test_helper_admin_and_responsable_keep_full_access(client, role):
    created = create_ticket(client, role)
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]
    cookies = h.session_cookies(role)

    listing = client.get("/api/tickets", cookies=cookies)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [ticket_id]

    assert client.get("/api/tickets/stats", cookies=cookies).json()["active_count"] == 1

    detail = client.get(f"/api/tickets/{ticket_id}", cookies=cookies)
    assert detail.status_code == 200
    assert detail.json()["transcript"][0]["content"] == "Bonjour, j'ai besoin d'aide"

    patched = client.patch(f"/api/tickets/{ticket_id}", json={"notes": "Suivi"}, cookies=cookies)
    assert patched.status_code == 200 and patched.json()["notes"] == "Suivi"

    note = client.post(f"/api/tickets/{ticket_id}/notes", json={"title": "T", "content": "C"}, cookies=cookies)
    assert note.status_code == 201
    deleted = client.delete(f"/api/tickets/{ticket_id}/notes/{note.json()['id']}", cookies=cookies)
    assert deleted.status_code == 204

    h.fake_discord.messages[TICKET_CHANNEL_ID].append(raw_message("600000000000000003", "Nouveau message"))
    synced = client.post(f"/api/tickets/{ticket_id}/sync", cookies=cookies)
    assert synced.status_code == 200, synced.text
    assert synced.json()["message_count"] == 2

    member = client.get(f"/api/members/{MEMBER_ID}", cookies=cookies)
    assert member.status_code == 200 and member.json()["id"] == MEMBER_ID


@pytest.mark.parametrize("extra_role", ["helper", "responsable"])
def test_staff_who_is_also_helper_or_responsable_keeps_access(client, extra_role):
    h.fake_discord.member_roles[h.USER_IDS["staff"]].append(h.ROLE_IDS[extra_role])
    seed_ticket(client)
    response = client.get("/api/tickets", cookies=h.session_cookies("staff"))
    assert response.status_code == 200
    assert len(response.json()) == 1


# --- H2 : import / synchronisation limités aux catégories de tickets ---

def test_create_ticket_from_channel_outside_ticket_category_is_refused(client):
    response = create_ticket(client, "helper", OTHER_CHANNEL_ID)
    assert response.status_code == 403
    assert "catégorie de tickets" in response.json()["detail"]
    assert "Discussion staff confidentielle" not in response.text
    assert h.run(h.db.tickets.count_documents({})) == 0
    assert f"/channels/{OTHER_CHANNEL_ID}/messages" not in h.fake_discord.calls


def test_create_ticket_from_channel_without_category_is_refused(client):
    h.fake_discord.add_channel(OTHER_CHANNEL_ID, parent_id=None, name="general")
    response = create_ticket(client, "admin", OTHER_CHANNEL_ID)
    assert response.status_code == 403
    assert h.run(h.db.tickets.count_documents({})) == 0


def test_create_ticket_from_other_guild_is_refused(client):
    h.fake_discord.add_channel(OTHER_CHANNEL_ID, guild_id="100000000000000999")
    response = create_ticket(client, "helper", OTHER_CHANNEL_ID)
    assert response.status_code == 403
    assert h.run(h.db.tickets.count_documents({})) == 0


def test_create_ticket_from_category_channel_itself_is_refused(client):
    h.fake_discord.add_channel(h.TICKET_CATEGORY_ID, parent_id=None, channel_type=4, name="Tickets")
    response = create_ticket(client, "helper", h.TICKET_CATEGORY_ID)
    assert response.status_code in (403, 422)
    assert h.run(h.db.tickets.count_documents({})) == 0


def test_thread_inside_ticket_channel_is_accepted(client):
    h.fake_discord.add_channel(PARENT_TEXT_CHANNEL_ID, parent_id=h.TICKET_CATEGORY_ID, name="ticket-0002")
    h.fake_discord.add_channel(THREAD_CHANNEL_ID, parent_id=PARENT_TEXT_CHANNEL_ID, channel_type=12, name="fil")
    h.fake_discord.messages[THREAD_CHANNEL_ID] = [raw_message("600000000000000010", "Message du fil")]
    response = create_ticket(client, "helper", THREAD_CHANNEL_ID)
    assert response.status_code == 201, response.text
    assert response.json()["transcript"][0]["content"] == "Message du fil"


def test_thread_inside_non_ticket_channel_is_refused(client):
    h.fake_discord.add_channel(PARENT_TEXT_CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="staff")
    h.fake_discord.add_channel(THREAD_CHANNEL_ID, parent_id=PARENT_TEXT_CHANNEL_ID, channel_type=11, name="fil")
    h.fake_discord.messages[THREAD_CHANNEL_ID] = [raw_message("600000000000000011", "Fil staff privé")]
    response = create_ticket(client, "helper", THREAD_CHANNEL_ID)
    assert response.status_code == 403
    assert "Fil staff privé" not in response.text
    assert h.run(h.db.tickets.count_documents({})) == 0


def test_sync_refuses_channel_moved_out_of_ticket_category(client):
    ticket = seed_ticket(client)
    h.fake_discord.add_channel(TICKET_CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="ticket-0001")
    h.fake_discord.messages[TICKET_CHANNEL_ID] = [raw_message("600000000000000020", "Contenu remplacé")]
    response = client.post(f"/api/tickets/{ticket['id']}/sync", cookies=h.session_cookies("helper"))
    assert response.status_code == 403
    stored = h.run(h.db.tickets.find_one({"id": ticket["id"]}, {"_id": 0}))
    assert stored["transcript"][0]["content"] == "Bonjour, j'ai besoin d'aide"


def test_extra_ticket_categories_from_config_are_allowed(client, monkeypatch):
    monkeypatch.setattr(
        discord_service,
        "ALLOWED_TICKET_CATEGORY_IDS",
        frozenset({h.TICKET_CATEGORY_ID, h.OTHER_CATEGORY_ID}),
    )
    response = create_ticket(client, "helper", OTHER_CHANNEL_ID)
    assert response.status_code == 201, response.text


def test_sync_works_again_once_archive_category_is_allowed(client, monkeypatch):
    # Ticket fermé déplacé par le bot dans une catégorie d'archives : lisible, et synchronisable
    # dès que cette catégorie est ajoutée à DISCORD_TICKET_CATEGORY_IDS.
    ticket = seed_ticket(client)
    h.fake_discord.add_channel(TICKET_CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="ticket-0001")
    h.fake_discord.messages[TICKET_CHANNEL_ID].append(raw_message("600000000000000021", "Après fermeture"))
    cookies = h.session_cookies("helper")
    assert client.get(f"/api/tickets/{ticket['id']}", cookies=cookies).status_code == 200
    assert client.post(f"/api/tickets/{ticket['id']}/sync", cookies=cookies).status_code == 403

    monkeypatch.setattr(
        discord_service,
        "ALLOWED_TICKET_CATEGORY_IDS",
        frozenset({h.TICKET_CATEGORY_ID, h.OTHER_CATEGORY_ID}),
    )
    synced = client.post(f"/api/tickets/{ticket['id']}/sync", cookies=cookies)
    assert synced.status_code == 200, synced.text
    assert synced.json()["message_count"] == 2


def test_category_refusal_is_logged_with_resolved_category(client, caplog):
    caplog.set_level("WARNING", logger="services.discord_service")
    response = create_ticket(client, "helper", OTHER_CHANNEL_ID)
    assert response.status_code == 403
    messages = [record.getMessage() for record in caplog.records if record.name == "services.discord_service"]
    assert len(messages) == 1
    assert OTHER_CHANNEL_ID in messages[0] and h.OTHER_CATEGORY_ID in messages[0]
    assert "DISCORD_TICKET_CATEGORY_IDS" in messages[0]
    assert "staff-prive" not in messages[0]


def test_thread_refusal_is_logged_with_parent_and_category(client, caplog):
    caplog.set_level("WARNING", logger="services.discord_service")
    h.fake_discord.add_channel(PARENT_TEXT_CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="staff")
    h.fake_discord.add_channel(THREAD_CHANNEL_ID, parent_id=PARENT_TEXT_CHANNEL_ID, channel_type=12, name="fil")
    assert create_ticket(client, "helper", THREAD_CHANNEL_ID).status_code == 403
    message = next(record.getMessage() for record in caplog.records if record.name == "services.discord_service")
    assert THREAD_CHANNEL_ID in message and PARENT_TEXT_CHANNEL_ID in message
    assert h.OTHER_CATEGORY_ID in message and "type 12" in message


def test_wrong_channel_type_refusal_is_logged(client, caplog):
    caplog.set_level("WARNING", logger="services.discord_service")
    h.fake_discord.add_channel(OTHER_CHANNEL_ID, parent_id=h.TICKET_CATEGORY_ID, channel_type=15, name="forum")
    response = create_ticket(client, "helper", OTHER_CHANNEL_ID)
    assert response.status_code == 422
    message = next(record.getMessage() for record in caplog.records if record.name == "services.discord_service")
    assert OTHER_CHANNEL_ID in message and "type 15" in message


def test_accepted_channel_logs_nothing(client, caplog):
    caplog.set_level("WARNING", logger="services.discord_service")
    assert create_ticket(client, "helper").status_code == 201
    assert not [record for record in caplog.records if record.name == "services.discord_service"]


def test_thread_whose_parent_channel_is_allow_listed_is_accepted(client, monkeypatch):
    # Déploiement où la liste autorisée désigne le salon qui héberge les fils de tickets.
    monkeypatch.setattr(
        discord_service,
        "ALLOWED_TICKET_CATEGORY_IDS",
        frozenset({h.TICKET_CATEGORY_ID, PARENT_TEXT_CHANNEL_ID}),
    )
    h.fake_discord.add_channel(PARENT_TEXT_CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="tickets")
    h.fake_discord.add_channel(THREAD_CHANNEL_ID, parent_id=PARENT_TEXT_CHANNEL_ID, channel_type=12, name="fil")
    h.fake_discord.messages[THREAD_CHANNEL_ID] = [raw_message("600000000000000012", "Message du fil privé")]
    response = create_ticket(client, "helper", THREAD_CHANNEL_ID)
    assert response.status_code == 201, response.text
    assert response.json()["transcript"][0]["content"] == "Message du fil privé"

    # Le salon parent lui-même reste refusé : sa catégorie n'est pas autorisée.
    h.fake_discord.messages[PARENT_TEXT_CHANNEL_ID] = [raw_message("600000000000000013", "Salon parent")]
    assert create_ticket(client, "helper", PARENT_TEXT_CHANNEL_ID).status_code == 403


def test_thread_parent_in_default_category_does_not_widen_access(client):
    # Par défaut la liste ne contient que des catégories : un fil n'a jamais une catégorie pour
    # parent direct, donc l'acceptation par parent direct n'ouvre rien de plus.
    h.fake_discord.add_channel(PARENT_TEXT_CHANNEL_ID, parent_id=h.OTHER_CATEGORY_ID, name="staff")
    h.fake_discord.add_channel(THREAD_CHANNEL_ID, parent_id=PARENT_TEXT_CHANNEL_ID, channel_type=11, name="fil")
    assert create_ticket(client, "helper", THREAD_CHANNEL_ID).status_code == 403
    assert f"/channels/{PARENT_TEXT_CHANNEL_ID}" in h.fake_discord.calls


def test_ticket_category_ids_env_parsing():
    assert config._parse_ids(" 1499495158469758976, 123 ,abc,,../x") == {"1499495158469758976", "123"}
    assert config._parse_ids("") == set()
    # Sans DISCORD_TICKET_CATEGORY_IDS, seule la catégorie principale est autorisée.
    assert config.ALLOWED_TICKET_CATEGORY_IDS == frozenset({h.TICKET_CATEGORY_ID})


def test_channel_archives_default_still_accepts_any_guild_channel(client):
    # channel_archives (responsables) utilise la valeur par défaut : aucun contrôle de catégorie.
    service = DiscordService()
    channel = h.run(service.fetch_text_channel(OTHER_CHANNEL_ID))
    assert channel["id"] == OTHER_CHANNEL_ID

    async def collect():
        return [page async for page in service.iter_channel_history(OTHER_CHANNEL_ID)]

    pages = h.run(collect())
    assert pages[0][0].content == "Discussion staff confidentielle"
    assert len(h.run(service.fetch_channel_history(OTHER_CHANNEL_ID))) == 1

    with pytest.raises(HTTPException) as error:
        h.run(service.fetch_channel_history(OTHER_CHANNEL_ID, require_ticket_category=True))
    assert error.value.status_code == 403

    async def collect_strict():
        return [page async for page in service.iter_channel_history(OTHER_CHANNEL_ID, require_ticket_category=True)]

    with pytest.raises(HTTPException) as error:
        h.run(collect_strict())
    assert error.value.status_code == 403


# --- L7 : pas de fuite d'erreurs internes dans le flux du résumé IA ---

def test_ai_summary_stream_hides_internal_errors(client, monkeypatch):
    ticket = seed_ticket(client)

    async def failing_summary(ticket, helper_id):
        yield "progress", "Gemini rédige la synthèse…"
        raise RuntimeError("clé=sk-secret-123 https://interne.example/llm")

    monkeypatch.setattr(tickets, "ensure_ai_configuration", lambda: None)
    monkeypatch.setattr(tickets, "stream_summary", failing_summary)
    response = client.post(f"/api/tickets/{ticket['id']}/ai-summary/stream", cookies=h.session_cookies("helper"))
    assert response.status_code == 200
    assert "sk-secret-123" not in response.text
    assert "interne.example" not in response.text
    event_type, payload = sse_events(response.text)[-1]
    assert event_type == "error"
    assert payload["message"] == "La génération du résumé a échoué. Réessayez dans un instant."


def test_ai_summary_stream_keeps_http_exception_detail(client, monkeypatch):
    ticket = seed_ticket(client)

    async def unavailable_summary(ticket, helper_id):
        raise HTTPException(status_code=503, detail="La clé Gemini n’est pas configurée.")
        yield  # pragma: no cover

    monkeypatch.setattr(tickets, "ensure_ai_configuration", lambda: None)
    monkeypatch.setattr(tickets, "stream_summary", unavailable_summary)
    response = client.post(f"/api/tickets/{ticket['id']}/ai-summary/stream", cookies=h.session_cookies("helper"))
    assert sse_events(response.text) == [("error", {"message": "La clé Gemini n’est pas configurée."})]


# --- L2 : identifiants Discord validés avant de construire l'URL ---

@pytest.mark.parametrize("member_id", ["%2E%2E", "..", "@me", "123", "abc", "4000000000000000990000000"])
def test_member_route_rejects_non_snowflake_ids(client, member_id):
    response = client.get(f"/api/members/{member_id}", cookies=h.session_cookies("helper"))
    assert response.status_code in (404, 422)
    assert all(".." not in call and "@me" not in call for call in h.fake_discord.calls)
    assert all(not call.endswith(f"/members/{member_id}") for call in h.fake_discord.calls)


@pytest.mark.parametrize("bad_id", ["..", "../../users/@me", "@me", "", None, "12a", "１２３", "١٢٣"])
def test_discord_service_rejects_non_digit_ids_before_any_call(bad_id):
    h.reset_db()
    h.reset_discord()
    service = DiscordService()
    calls = [
        lambda: service.fetch_member(bad_id),
        lambda: service.fetch_member_role_ids(bad_id),
        lambda: service.member_has_role(bad_id, h.ROLE_IDS["helper"]),
        lambda: service.fetch_text_channel(bad_id),
        lambda: service.fetch_channel_history(bad_id),
    ]
    for make_call in calls:
        with pytest.raises(HTTPException) as error:
            h.run(make_call())
        assert error.value.status_code == 404

    async def iterate():
        return [page async for page in service.iter_channel_history(bad_id)]

    with pytest.raises(HTTPException):
        h.run(iterate())
    assert h.fake_discord.calls == []


def test_ensure_discord_id_accepts_real_snowflakes():
    assert ensure_discord_id("1499495158469758976") == "1499495158469758976"
    assert ensure_discord_id(1499495158469758976) == "1499495158469758976"


@pytest.mark.parametrize("role", FORBIDDEN_ROLES + ["member"])
def test_resource_library_requires_helper_or_responsable(role):
    from routers import resources

    h.reset_db()
    h.reset_discord()
    resource_client = h.make_client(resources.router)
    assert resource_client.get("/api/resources", cookies=h.session_cookies(role)).status_code == 403
    assert resource_client.get("/api/resources/inconnue/download", cookies=h.session_cookies(role)).status_code == 403


@pytest.mark.parametrize("role", ALLOWED_ROLES)
def test_resource_library_still_open_to_helpers(role):
    from routers import resources

    h.reset_db()
    h.reset_discord()
    resource_client = h.make_client(resources.router)
    response = resource_client.get("/api/resources", cookies=h.session_cookies(role))
    assert response.status_code == 200
    assert response.json() == {"resources": []}
