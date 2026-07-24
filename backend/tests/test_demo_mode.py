"""Iris demo-mode API tests.

These tests exercise the POST /api/auth/demo-session flow, verify the 3
demo tickets are exposed via the tickets API, and confirm demo
isolation (sync doesn't call Discord, notes/vocal persist, demo scope
does not leak to non-demo tickets).
"""
import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def demo_client():
    """Session cookie signed by the backend for the demo helper."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/demo-session", timeout=15)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["authenticated"] is True
    assert body["helper"]["id"] == "iris-demo-helper"
    assert body["helper"]["mode"] == "demo"
    assert body["helper"]["global_name"] == "Lina · Helper"
    return session


# --- Demo session lifecycle ---
class TestDemoSession:
    def test_demo_session_sets_cookie(self):
        session = requests.Session()
        r = session.post(f"{BASE_URL}/api/auth/demo-session", timeout=15)
        assert r.status_code == 200
        assert "iris_session" in session.cookies
        # /api/auth/session must then report authenticated=true, mode=demo
        me = session.get(f"{BASE_URL}/api/auth/session", timeout=15)
        assert me.status_code == 200
        data = me.json()
        assert data["authenticated"] is True
        assert data["helper"]["mode"] == "demo"
        assert data["helper"]["id"] == "iris-demo-helper"

    def test_logout_clears_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/demo-session", timeout=15)
        session.post(f"{BASE_URL}/api/auth/logout", timeout=15)
        # After logout, tickets endpoint must be 401 again
        r = session.get(f"{BASE_URL}/api/tickets", timeout=15)
        assert r.status_code == 401


# --- Demo tickets exposure ---
class TestDemoTickets:
    def test_stats_include_seed(self, demo_client):
        # Seed has 2 active + 1 archived at minimum; SUIVI-* cases add on top.
        r = demo_client.get(f"{BASE_URL}/api/tickets/stats", timeout=15)
        assert r.status_code == 200
        stats = r.json()
        assert stats["active_count"] >= 2
        assert stats["archived_count"] >= 1
        assert stats["total_messages"] >= 10

    def test_three_demo_tickets_present(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/tickets", timeout=15)
        assert r.status_code == 200
        tickets = r.json()
        ids = {t["id"] for t in tickets}
        assert {"TKT-0888", "TKT-0890", "TKT-0891"} <= ids
        # Statuses match the seed
        statuses = {t["id"]: t["status"] for t in tickets}
        assert statuses["TKT-0891"] == "active"
        assert statuses["TKT-0890"] == "active"
        assert statuses["TKT-0888"] == "archived"

    def test_ticket_detail_TKT_0891_has_full_content(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/tickets/TKT-0891", timeout=15)
        assert r.status_code == 200
        detail = r.json()
        assert detail["id"] == "TKT-0891"
        assert "Anxiété" in detail["title"]
        assert detail["member"]["display_name"] == "Alexandre D."
        assert len(detail["transcript"]) == 4
        # Helper messages must be present (demo-891-2 and demo-891-4)
        msg_ids = [m["id"] for m in detail["transcript"]]
        assert "demo-891-2" in msg_ids
        assert "demo-891-4" in msg_ids
        helper_msgs = [m for m in detail["transcript"] if m["author"]["id"] == "iris-demo-helper"]
        assert len(helper_msgs) == 2
        # Helper message content must not be empty (the bubble-width fix targets these)
        for m in helper_msgs:
            assert isinstance(m["content"], str) and len(m["content"]) > 20
        assert detail["notes"] is not None
        assert detail["vocal_summary"] is not None

    def test_all_three_demo_tickets_return_detail(self, demo_client):
        for tid in ("TKT-0888", "TKT-0890", "TKT-0891"):
            r = demo_client.get(f"{BASE_URL}/api/tickets/{tid}", timeout=15)
            assert r.status_code == 200, f"{tid} -> {r.status_code}"
            body = r.json()
            assert body["id"] == tid
            assert body["notes"]
            assert body["vocal_summary"]

    def test_response_never_leaks_mongo_id(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/tickets/TKT-0891", timeout=15)
        # Mongo's ObjectId key ("_id") must be projected out.
        assert '"_id"' not in r.text


# --- Persistence of notes / vocal summary in demo mode ---
class TestDemoPersistence:
    def test_patch_notes_and_vocal_persist(self, demo_client):
        payload = {"notes": "TEST_note demo persistance", "vocal_summary": "TEST_vocal demo persistance"}
        p = demo_client.patch(f"{BASE_URL}/api/tickets/TKT-0891", json=payload, timeout=15)
        assert p.status_code == 200
        after = p.json()
        assert after["notes"] == payload["notes"]
        assert after["vocal_summary"] == payload["vocal_summary"]

        # GET should reflect persisted values
        g = demo_client.get(f"{BASE_URL}/api/tickets/TKT-0891", timeout=15)
        assert g.status_code == 200
        assert g.json()["notes"] == payload["notes"]
        assert g.json()["vocal_summary"] == payload["vocal_summary"]

    def test_sync_demo_ticket_does_not_hit_discord(self, demo_client):
        # Even though DISCORD_BOT_TOKEN is not set, sync of a demo ticket must
        # succeed and preserve the demo transcript.
        before = demo_client.get(f"{BASE_URL}/api/tickets/TKT-0891", timeout=15).json()
        r = demo_client.post(f"{BASE_URL}/api/tickets/TKT-0891/sync", timeout=15)
        assert r.status_code == 200, r.text
        after = r.json()
        assert after["message_count"] == before["message_count"]
        assert len(after["transcript"]) == len(before["transcript"])
        # Notes/vocal preserved
        assert after["notes"] == before["notes"]
        assert after["vocal_summary"] == before["vocal_summary"]
        # last_synced_at must be refreshed (present, may be earlier than
        # seeded future timestamp because seed uses 2026-07 dates)
        assert isinstance(after["last_synced_at"], str) and len(after["last_synced_at"]) > 10
        assert after["last_synced_at"] != before["last_synced_at"]

    def test_archive_and_reactivate_demo_ticket(self, demo_client):
        # Archive TKT-0891
        r1 = demo_client.patch(f"{BASE_URL}/api/tickets/TKT-0891", json={"status": "archived"}, timeout=15)
        assert r1.status_code == 200
        assert r1.json()["status"] == "archived"
        # Reactivate
        r2 = demo_client.patch(f"{BASE_URL}/api/tickets/TKT-0891", json={"status": "active"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] == "active"


# --- Isolation: demo helper must NOT see real tickets, and vice versa ---
class TestDemoIsolation:
    def test_create_ticket_denied_for_demo_helper(self, demo_client):
        # Demo helper trying to create a real (non-demo) ticket must fail
        # because DiscordService cannot fetch without a bot token.
        r = demo_client.post(
            f"{BASE_URL}/api/tickets",
            json={"member_id": "123456789012345678", "channel_id": "999999999999999999"},
            timeout=15,
        )
        # Either 409/500/503 depending on config -- must NOT be 201.
        assert r.status_code != 201

    def test_no_real_tickets_appear_in_demo_scope(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/tickets", timeout=15)
        assert r.status_code == 200
        for ticket in r.json():
            assert ticket["id"].startswith("TKT-08") or ticket["id"].startswith("SUIVI-"), (
                f"non-demo ticket leaked: {ticket['id']}"
            )


# --- Guards still enforced against unauthenticated callers ---
class TestUnauthenticatedStillBlocked:
    def test_tickets_stats_401_without_cookie(self):
        r = requests.get(f"{BASE_URL}/api/tickets/stats", timeout=15)
        assert r.status_code == 401

    def test_ticket_detail_401_without_cookie(self):
        r = requests.get(f"{BASE_URL}/api/tickets/TKT-0891", timeout=15)
        assert r.status_code == 401
