"""Iris backend API smoke + security tests.

These tests are executed against the public preview URL.

State expected in this iteration:
  - Discord bot token, OAuth client id/secret AND redirect uri are configured
    server-side. As a result:
      * GET /api/auth/discord/login must issue a 302 redirect to
        discord.com/oauth2/authorize with the correct scopes and set the
        iris_oauth_state cookie.
      * The response MUST NOT leak the client_secret or bot token.
      * Only members of the pinned guild who also carry the Helper role
        (verified via DiscordService.member_has_role) receive a session
        cookie after OAuth callback.
  - All /api/tickets and /api/members endpoints still require a session
    (401 without cookie, HMAC-signed cookie required).
  - The Discord bot API surface is scoped to a single guild (guild-id
    parametrised path) and pagination follows the limit=100 + before pattern.
"""
import os
import re
from urllib.parse import parse_qs, urlparse

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://iris-logs.preview.emergentagent.com").rstrip("/")

EXPECTED_GUILD_ID = "1081957992188088391"
EXPECTED_HELPER_ROLE_ID = "1499491909750755570"


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
    def test_session_unauthenticated_without_cookie(self):
        r = requests.get(f"{BASE_URL}/api/auth/session", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["authenticated"] is False
        assert data.get("helper") is None

    def test_discord_login_returns_302_to_discord_authorize(self):
        """OAuth is fully configured -> we must redirect to discord.com."""
        r = requests.get(
            f"{BASE_URL}/api/auth/discord/login",
            timeout=15,
            allow_redirects=False,
        )
        assert r.status_code == 302, f"expected 302, got {r.status_code}: {r.text[:200]}"
        location = r.headers.get("location", "")
        parsed = urlparse(location)
        assert parsed.scheme == "https"
        assert parsed.netloc == "discord.com"
        assert parsed.path == "/oauth2/authorize"
        qs = parse_qs(parsed.query)
        assert qs.get("response_type") == ["code"]
        assert qs.get("scope") == ["identify guilds"]
        assert qs.get("prompt") == ["consent"]
        # client_id must be present but no secret ever leaves the server
        assert qs.get("client_id")
        assert qs["client_id"][0].isdigit()
        # redirect_uri must be the /api/auth/discord/callback of THIS deploy
        assert qs.get("redirect_uri")
        assert qs["redirect_uri"][0].endswith("/api/auth/discord/callback")
        # A state cookie must be set (double-submit CSRF token)
        cookie_hdr = r.headers.get("set-cookie", "")
        assert "iris_oauth_state=" in cookie_hdr
        # Cookie must be HttpOnly + Secure
        assert re.search(r"iris_oauth_state=[^;]+.*HttpOnly", cookie_hdr, re.I | re.S)
        assert re.search(r"iris_oauth_state=[^;]+.*Secure", cookie_hdr, re.I | re.S)

    def test_discord_login_response_does_not_leak_secrets(self):
        """The redirect location + body must never contain the client_secret
        nor the bot token nor the session secret. We can't read them from
        env inside the test, so we just make sure nothing looks like the
        secret parameters."""
        r = requests.get(
            f"{BASE_URL}/api/auth/discord/login",
            timeout=15,
            allow_redirects=False,
        )
        location = r.headers.get("location", "")
        # The OAuth "authorize" endpoint must not receive client_secret
        assert "client_secret" not in location.lower()
        # No bearer/bot token should end up in body either
        assert "Bot " not in r.text
        assert "Bearer " not in r.text

    def test_discord_callback_rejects_state_mismatch(self):
        """When the state cookie doesn't match, the callback must NOT create
        a session; it should bounce back to the SPA with an error flag."""
        r = requests.get(
            f"{BASE_URL}/api/auth/discord/callback",
            params={"code": "fake", "state": "does-not-match"},
            timeout=15,
            allow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers.get("location", "").startswith("/?auth=failed")
        # No session cookie must be set
        assert "iris_session=" not in r.headers.get("set-cookie", "")

    def test_logout_returns_unauthenticated_body(self):
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
        """POST /api/tickets must be behind current_helper: no session -> 401.
        This is critical because that endpoint is the only entry point to the
        real Discord import."""
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
    """Enforce guild scoping, role gating, pagination and _id exclusion
    contracts by inspecting the backend source so future refactors don't
    silently regress the security-critical constraints."""

    BACKEND_DIR = "/app/backend"

    def _read(self, relative_path: str) -> str:
        with open(os.path.join(self.BACKEND_DIR, relative_path), encoding="utf-8") as fh:
            return fh.read()

    # --- discord_service.py contracts ---
    def test_discord_service_member_lookup_scoped_to_guild(self):
        source = self._read("services/discord_service.py")
        assert "/guilds/{DISCORD_GUILD_ID}/members/{member_id}" in source

    def test_discord_service_member_has_role_uses_guild_scope(self):
        source = self._read("services/discord_service.py")
        # member_has_role must fetch via /guilds/{GUILD}/members/{id} too,
        # not via /users/@me endpoints (which would rely on the callee).
        assert "async def member_has_role" in source
        member_has_role_block = source.split("async def member_has_role", 1)[1].split("async def", 1)[0]
        assert "/guilds/{DISCORD_GUILD_ID}/members/{member_id}" in member_has_role_block
        assert 'role_id in payload.get("roles"' in member_has_role_block

    def test_discord_service_validates_channel_guild_and_type(self):
        source = self._read("services/discord_service.py")
        assert 'channel.get("guild_id") != DISCORD_GUILD_ID' in source
        # 0=GUILD_TEXT, 5=GUILD_ANNOUNCEMENT, 15=FORUM
        assert "channel.get(\"type\") not in {0, 5, 15}" in source

    def test_discord_history_uses_limit_100_and_before_pagination(self):
        source = self._read("services/discord_service.py")
        assert '"limit": 100' in source
        assert '"before"' in source
        assert "page[-1][\"id\"]" in source
        assert "if len(page) < 100" in source  # explicit exhaustion condition

    def test_discord_service_uses_bot_auth_header(self):
        """The bot token must be used with a `Bot <token>` scheme and only
        server-side; no OAuth user token is ever used for import."""
        source = self._read("services/discord_service.py")
        assert 'Authorization": f"Bot {DISCORD_BOT_TOKEN}"' in source

    # --- auth_service.py contracts ---
    def test_auth_service_enforces_guild_and_helper_role(self):
        source = self._read("services/auth_service.py")
        # After a successful token exchange, presence in the guild AND an
        # authorized Discord role (helper OR admin) MUST both be checked
        # before any session is minted.
        assert 'guild.get("id") == DISCORD_GUILD_ID' in source
        # Iteration 7: the helper-role gate is now delegated to
        # has_iris_access(profile_id), which checks helper role first and
        # falls back to admin role. Both role IDs must be involved.
        assert "has_iris_access(profile[\"id\"])" in source
        assert "member_has_role(helper_id, DISCORD_HELPER_ROLE_ID)" in source
        assert "member_has_role(helper_id, DISCORD_ADMIN_ROLE_ID)" in source
        # Both checks must raise 403 when they fail
        assert "status_code=403" in source
        # The scope requested must be identify+guilds only
        assert '"scope": "identify guilds"' in source

    # --- tickets.py contracts ---
    def test_tickets_router_excludes_mongo_object_id(self):
        source = self._read("routers/tickets.py")
        # Every find_one / find call must project out _id
        assert source.count('{"_id": 0') >= 3

    def test_create_ticket_uses_current_helper_dependency(self):
        source = self._read("routers/tickets.py")
        # POST /api/tickets must depend on current_helper (Discord-scoped
        # helper session). Also, must call DiscordService's guild-scoped
        # fetch_member and fetch_text_channel.
        assert "helper: AuthenticatedHelper = Depends(current_helper)" in source
        assert "discord.fetch_member(input_data.member_id)" in source
        assert "discord.fetch_text_channel(input_data.channel_id)" in source
        assert "discord.fetch_channel_history(input_data.channel_id)" in source

    # --- .env contracts ---
    def test_env_pins_guild_and_role(self):
        env_path = os.path.join(self.BACKEND_DIR, ".env")
        with open(env_path, encoding="utf-8") as fh:
            env = fh.read()
        assert f'DISCORD_GUILD_ID="{EXPECTED_GUILD_ID}"' in env
        assert f'DISCORD_HELPER_ROLE_ID="{EXPECTED_HELPER_ROLE_ID}"' in env

    def test_env_has_oauth_and_bot_configured(self):
        """Iteration 5 baseline: OAuth + bot are configured server-side."""
        env_path = os.path.join(self.BACKEND_DIR, ".env")
        with open(env_path, encoding="utf-8") as fh:
            env = fh.read()
        for key in (
            "DISCORD_CLIENT_ID=",
            "DISCORD_CLIENT_SECRET=",
            "DISCORD_REDIRECT_URI=",
            "DISCORD_BOT_TOKEN=",
            "APP_SESSION_SECRET=",
        ):
            match = re.search(rf"^{key}(.*)$", env, re.M)
            assert match, f"{key} not present in backend/.env"
            value = match.group(1).strip().strip('"').strip("'")
            assert value, f"{key} present but empty in backend/.env"


# --- Frontend static invariants (kept small to avoid CI flakiness) ---
class TestFrontendStaticInvariants:
    FRONTEND_DIR = "/app/frontend"

    def _read(self, relative_path: str) -> str:
        with open(os.path.join(self.FRONTEND_DIR, relative_path), encoding="utf-8") as fh:
            return fh.read()

    def test_new_ticket_form_posts_member_and_channel_ids(self):
        source = self._read("src/components/NewTicketForm.jsx")
        assert 'api.post("/tickets"' in source
        assert "member_id: memberId.trim()" in source
        assert "channel_id: channelId.trim()" in source

    def test_dashboard_renders_import_button_when_not_demo(self):
        source = self._read("src/pages/DashboardPage.jsx")
        # When helper is Discord-authenticated (isDemo === false) the CTA
        # switches to "Importer un salon Discord".
        assert "Importer un salon Discord" in source
        assert 'to="/new"' in source

    def test_new_ticket_page_switches_wording_when_not_demo(self):
        source = self._read("src/pages/NewTicketPage.jsx")
        assert "IMPORT DISCORD" in source
        assert "Importer un dossier depuis Discord" in source
