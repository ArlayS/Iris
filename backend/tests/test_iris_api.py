"""Iris backend API smoke tests.

These tests are executed against the public preview URL. OAuth credentials
are intentionally not configured so:
  - /api/auth/discord/login must return 503 with a clear French message
  - /api/tickets and /api/members must require a session (401)
Discord bot token / API is NEVER used from tests.
"""
import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://iris-logs.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session


# --- Health / root ---
class TestHealth:
    def test_root_ok(self, api_client):
        response = api_client.get(f"{BASE_URL}/api/", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Iris" in data["message"]


# --- Auth flows ---
class TestAuth:
    def test_session_unauthenticated_without_cookie(self, api_client):
        # Use a fresh session to avoid any prior cookies leaking in
        r = requests.get(f"{BASE_URL}/api/auth/session", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["authenticated"] is False
        assert data.get("helper") in (None,)

    def test_discord_login_returns_503_when_oauth_not_configured(self, api_client):
        # allow_redirects=False so we can see the raw 503
        r = requests.get(
            f"{BASE_URL}/api/auth/discord/login",
            timeout=15,
            allow_redirects=False,
        )
        assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        detail = data.get("detail", "")
        # Should mention missing configuration items
        assert "DISCORD_CLIENT_ID" in detail
        assert "DISCORD_CLIENT_SECRET" in detail
        # APP_SESSION_SECRET may or may not be listed depending on env config.
        # Must never leak any actual secret value
        assert "Bot " not in detail
        assert "token" not in detail.lower()

    def test_logout_returns_unauthenticated_body(self, api_client):
        r = requests.post(f"{BASE_URL}/api/auth/logout", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["authenticated"] is False
        assert data.get("helper") is None


# --- Protected routes must require a session ---
class TestAuthGuards:
    """Members and tickets routes must NOT be accessible without a session."""

    def test_members_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/members/123456789012345678", timeout=15)
        assert r.status_code == 401, f"members must require auth, got {r.status_code}"

    def test_list_tickets_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/tickets", timeout=15)
        assert r.status_code == 401

    def test_tickets_stats_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/tickets/stats", timeout=15)
        assert r.status_code == 401

    def test_create_ticket_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/tickets",
            json={"member_id": "123456789012345678", "channel_id": "123456789012345678"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_get_ticket_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/tickets/does-not-exist", timeout=15)
        assert r.status_code == 401

    def test_patch_ticket_requires_auth(self):
        r = requests.patch(
            f"{BASE_URL}/api/tickets/does-not-exist",
            json={"notes": "x"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_sync_ticket_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/tickets/does-not-exist/sync", timeout=15)
        assert r.status_code == 401

    def test_forged_cookie_still_rejected(self):
        # Even with a bogus cookie, the HMAC-signed session must reject it as 401
        r = requests.get(
            f"{BASE_URL}/api/tickets",
            cookies={"iris_session": "invalid.badsig"},
            timeout=15,
        )
        assert r.status_code == 401


# --- Static verification of backend source code assumptions ---
class TestStaticInvariants:
    """Enforce guild scoping, pagination and _id exclusion contracts by
    inspecting the backend source so future refactors don't silently
    regress the security-critical constraints."""

    BACKEND_DIR = "/app/backend"

    def _read(self, relative_path: str) -> str:
        with open(os.path.join(self.BACKEND_DIR, relative_path), encoding="utf-8") as fh:
            return fh.read()

    def test_discord_service_scopes_member_lookup_to_guild(self):
        source = self._read("services/discord_service.py")
        assert "/guilds/{DISCORD_GUILD_ID}/members/{member_id}" in source

    def test_discord_service_validates_channel_guild(self):
        source = self._read("services/discord_service.py")
        assert 'channel.get("guild_id") != DISCORD_GUILD_ID' in source

    def test_discord_history_uses_limit_100_and_before_pagination(self):
        source = self._read("services/discord_service.py")
        assert '"limit": 100' in source
        assert '"before"' in source
        assert "page[-1][\"id\"]" in source

    def test_tickets_router_excludes_mongo_object_id(self):
        source = self._read("routers/tickets.py")
        # Every find_one / find call must project out _id
        assert source.count('{"_id": 0') >= 3

    def test_guild_id_matches_expected_server(self):
        # The server must be pinned to the documented guild.
        env_path = os.path.join(self.BACKEND_DIR, ".env")
        with open(env_path, encoding="utf-8") as fh:
            env = fh.read()
        assert 'DISCORD_GUILD_ID="1081957992188088391"' in env

    def test_bot_token_not_present_in_env(self):
        env_path = os.path.join(self.BACKEND_DIR, ".env")
        with open(env_path, encoding="utf-8") as fh:
            env = fh.read()
        # per the review request, the bot token must not be exposed
        for line in env.splitlines():
            if line.startswith("DISCORD_BOT_TOKEN="):
                # If present, it must be empty
                assert line.strip() in {'DISCORD_BOT_TOKEN=""', "DISCORD_BOT_TOKEN="}
