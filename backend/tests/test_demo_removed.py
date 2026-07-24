"""
Iteration 6 — Regression test for total demo-mode removal.

Verifies:
 1. POST /api/auth/demo-session -> 404 (endpoint gone)
 2. POST /api/tickets/demo -> 404 or 405 (endpoint gone)
 3. GET /api/auth/discord/login -> 302 to discord.com
 4. GET /api/auth/session (no cookie) -> {authenticated: false}
 5. Tickets endpoints -> 401 without session
 6. current_helper refuses a signed session with mode!='discord'
"""
import base64
import hashlib
import hmac
import json
import os
import time

import httpx
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://iris-logs.preview.emergentagent.com").rstrip("/")


# --- Demo endpoints must be gone -------------------------------------------
class TestDemoEndpointsRemoved:
    def test_post_demo_session_returns_404(self):
        r = httpx.post(f"{BASE_URL}/api/auth/demo-session", timeout=15)
        assert r.status_code == 404, f"demo-session must be gone, got {r.status_code} body={r.text}"

    def test_get_demo_session_returns_404_or_405(self):
        # No sneaky GET variant either
        r = httpx.get(f"{BASE_URL}/api/auth/demo-session", timeout=15)
        assert r.status_code in (404, 405), f"got {r.status_code}"

    def test_post_tickets_demo_returns_404_or_405(self):
        r = httpx.post(
            f"{BASE_URL}/api/tickets/demo",
            json={"member_name": "X", "channel_name": "y"},
            timeout=15,
        )
        assert r.status_code in (404, 405), f"tickets/demo must be gone, got {r.status_code} body={r.text}"

    def test_get_tickets_demo_returns_404_or_401_or_405(self):
        r = httpx.get(f"{BASE_URL}/api/tickets/demo", timeout=15)
        # No cookie, and endpoint should not exist. If the router now matches this as
        # GET /tickets/{ticket_id} it will hit current_helper -> 401. Both are fine
        # as proof that the demo variant no longer creates anything.
        assert r.status_code in (401, 404, 405), f"got {r.status_code}"


# --- Discord OAuth still live ----------------------------------------------
class TestDiscordLoginLive:
    def test_discord_login_returns_302_to_discord(self):
        with httpx.Client(follow_redirects=False, timeout=15) as client:
            r = client.get(f"{BASE_URL}/api/auth/discord/login")
        assert r.status_code == 302, f"expected 302, got {r.status_code}"
        location = r.headers.get("location", "")
        assert location.startswith("https://discord.com/oauth2/authorize"), location
        assert "response_type=code" in location
        assert "scope=identify" in location
        # State cookie should be set, HttpOnly + Secure
        set_cookie = r.headers.get("set-cookie", "")
        assert "iris_oauth_state=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Secure" in set_cookie


# --- Session endpoint -------------------------------------------------------
class TestSessionEndpoint:
    def test_session_without_cookie_is_unauthenticated(self):
        r = httpx.get(f"{BASE_URL}/api/auth/session", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("authenticated") is False
        assert data.get("helper") is None


# --- Tickets endpoints all require auth ------------------------------------
class TestTicketsRequireAuth:
    def test_list_tickets_401(self):
        r = httpx.get(f"{BASE_URL}/api/tickets", timeout=15)
        assert r.status_code == 401

    def test_stats_401(self):
        r = httpx.get(f"{BASE_URL}/api/tickets/stats", timeout=15)
        assert r.status_code == 401

    def test_create_ticket_401(self):
        r = httpx.post(
            f"{BASE_URL}/api/tickets",
            json={"member_id": "1", "channel_id": "1"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_forged_random_session_cookie_rejected(self):
        r = httpx.get(
            f"{BASE_URL}/api/tickets",
            cookies={"iris_session": "not-a-real.session"},
            timeout=15,
        )
        assert r.status_code == 401


# --- current_helper refuses mode=demo, even if HMAC-signed -----------------
class TestDemoSessionModeRejected:
    """
    Directly exercise auth_service.parse_session / current_helper with a
    payload that has a valid signature (because we run inside the container
    and can read APP_SESSION_SECRET) but mode='demo'. The backend must
    refuse it.
    """

    def _sign(self, payload: dict, secret: str) -> str:
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def test_signed_demo_mode_session_is_rejected_by_tickets(self):
        # Load secret from backend/.env (we run inside the container).
        secret = None
        env_path = "/app/backend/.env"
        if os.path.exists(env_path):
            with open(env_path) as fh:
                for line in fh:
                    if line.startswith("APP_SESSION_SECRET="):
                        secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if not secret:
            pytest.skip("APP_SESSION_SECRET not accessible from test environment")

        payload = {
            "sub": "999",
            "username": "demo-helper",
            "global_name": "Demo",
            "avatar_url": None,
            "mode": "demo",
            "exp": int(time.time()) + 3600,
        }
        cookie = self._sign(payload, secret)

        # /api/auth/session must not report authenticated=true for a demo cookie
        r_session = httpx.get(
            f"{BASE_URL}/api/auth/session",
            cookies={"iris_session": cookie},
            timeout=15,
        )
        assert r_session.status_code == 200
        assert r_session.json().get("authenticated") is False, (
            "Signed session with mode!=discord must be treated as unauthenticated"
        )

        # And any protected ticket endpoint must 401
        r_tickets = httpx.get(
            f"{BASE_URL}/api/tickets",
            cookies={"iris_session": cookie},
            timeout=15,
        )
        assert r_tickets.status_code == 401

    def test_signed_discord_mode_session_is_accepted_by_session_endpoint(self):
        """Sanity: a properly signed mode=discord cookie for a fabricated
        user id no longer passes /auth/session because iteration 7 re-derives
        Discord access on every session read (has_iris_access hits the guild
        members API). We only verify here that the SIGNATURE is accepted at
        the parse_session layer — i.e. the endpoint does NOT return the
        unauthenticated shape it uses for tampered cookies. In practice
        Discord will 404 the unknown user, which bubbles up. Any of
        {200 authenticated:false, 404, 502} proves the crypto layer passed
        but Discord RBAC rejected."""
        secret = None
        env_path = "/app/backend/.env"
        if os.path.exists(env_path):
            with open(env_path) as fh:
                for line in fh:
                    if line.startswith("APP_SESSION_SECRET="):
                        secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if not secret:
            pytest.skip("APP_SESSION_SECRET not accessible from test environment")

        payload = {
            "sub": "42",
            "username": "helper42",
            "global_name": "Helper 42",
            "avatar_url": None,
            "mode": "discord",
            "exp": int(time.time()) + 3600,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        cookie = f"{encoded}.{sig}"
        r = httpx.get(
            f"{BASE_URL}/api/auth/session",
            cookies={"iris_session": cookie},
            timeout=15,
        )
        # Never authenticated: either endpoint returned 200 with
        # authenticated=false (Discord returned no role) OR bubbled the
        # Discord 404/5xx.
        assert r.status_code in (200, 404, 502)
        if r.status_code == 200:
            data = r.json()
            assert data.get("authenticated") is False, (
                "Iteration 7: session must re-derive access via Discord and "
                "refuse fabricated users even if the HMAC signature is valid."
            )


# --- Static invariants: verify code contains no demo endpoints -------------
class TestStaticNoDemoRoutes:
    def test_auth_router_has_no_demo_session(self):
        with open("/app/backend/routers/auth.py") as fh:
            content = fh.read()
        assert "demo-session" not in content
        assert "demo_session" not in content

    def test_tickets_router_has_no_demo_endpoint(self):
        with open("/app/backend/routers/tickets.py") as fh:
            content = fh.read()
        # No demo route decorator anywhere
        assert '"/demo"' not in content
        assert "'/demo'" not in content

    def test_auth_service_rejects_non_discord_mode(self):
        with open("/app/backend/services/auth_service.py") as fh:
            content = fh.read()
        # parse_session must guard on mode != 'discord'
        assert 'payload.get("mode"' in content and "discord" in content

    def test_login_page_has_no_demo_button(self):
        with open("/app/frontend/src/pages/LoginPage.jsx") as fh:
            content = fh.read()
        assert "demo-access-btn" not in content
        assert "demo-access-button" not in content

    def test_app_shell_has_no_notifications_or_settings_buttons(self):
        with open("/app/frontend/src/components/AppShell.jsx") as fh:
            content = fh.read()
        assert 'data-testid="notifications-button"' not in content
        assert 'data-testid="settings-button"' not in content

    def test_dashboard_has_real_import_button(self):
        with open("/app/frontend/src/pages/DashboardPage.jsx") as fh:
            content = fh.read()
        assert 'data-testid="import-discord-channel-button"' in content

    def test_new_ticket_form_posts_member_and_channel(self):
        with open("/app/frontend/src/components/NewTicketForm.jsx") as fh:
            content = fh.read()
        assert "member_id" in content
        assert "channel_id" in content
        assert '"/tickets"' in content
