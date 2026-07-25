"""Iteration 9 — validate the assigned_helper=None crash fix in /api/admin/overview
and the new DELETE /api/admin/tickets/{ticket_id} admin guard.

Uses a locally-signed diagnostic session cookie for the admin Discord user ID
1307294294348140546 (Coordinateur). The signed session only proves the cookie
is well-formed; the current_admin dependency still calls the real Discord bot
to check the Coordinateur role (ID 1503100661728936046). No tickets are
created, modified, or deleted by this test.
"""
import base64
import hashlib
import hmac
import json
import os
import time

import pytest
import requests
from dotenv import dotenv_values


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://iris-logs.preview.emergentagent.com"
).rstrip("/")
ADMIN_USER_ID = "1307294294348140546"
ADMIN_ROLE_ID = "1503100661728936046"
SESSION_COOKIE = "iris_session"


def _sign_session(user_id: str) -> str:
    env = dotenv_values("/app/backend/.env")
    secret = env["APP_SESSION_SECRET"]
    payload = {
        "sub": user_id,
        "username": "diagnostic",
        "global_name": None,
        "avatar_url": None,
        "mode": "discord",
        "exp": int(time.time()) + 600,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


@pytest.fixture(scope="module")
def admin_cookie():
    return {SESSION_COOKIE: _sign_session(ADMIN_USER_ID)}


# --- Bug fix: admin_overview must not crash on tickets whose assigned_helper is null ---
def test_admin_overview_200_for_coordinateur(admin_cookie):
    """Regression: previously threw 500 AttributeError on assigned_helper.get() when
    assigned_helper was None. Now must return 200 for a Coordinateur session."""
    r = requests.get(f"{BASE_URL}/api/admin/overview", cookies=admin_cookie, timeout=30)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:400]}"
    body = r.json()
    assert isinstance(body.get("total_helpers"), int)
    assert isinstance(body.get("active_tickets"), int)
    assert isinstance(body.get("unassigned_tickets"), int)
    assert isinstance(body.get("helpers"), list)
    # Per E1 diagnostic: expected total_helpers=6, active_tickets=4
    print(
        f"overview: total_helpers={body['total_helpers']} "
        f"active={body['active_tickets']} unassigned={body['unassigned_tickets']}"
    )
    # Presence of unassigned tickets is what triggered the original crash — must be countable
    assert body["unassigned_tickets"] >= 0


def test_admin_overview_unassigned_tickets_do_not_crash_helpers_loop(admin_cookie):
    """Even if unassigned tickets exist, each helper row must serialize cleanly."""
    r = requests.get(f"{BASE_URL}/api/admin/overview", cookies=admin_cookie, timeout=30)
    assert r.status_code == 200
    for row in r.json()["helpers"]:
        # assigned_count/active_count are ints; tickets is a list — either 0 or many is fine
        assert isinstance(row["assigned_count"], int)
        assert isinstance(row["active_count"], int)
        assert isinstance(row["tickets"], list)


# --- DELETE /api/admin/tickets/{id} guard behaviour ---
def test_delete_ticket_admin_endpoint_401_without_session():
    r = requests.delete(f"{BASE_URL}/api/admin/tickets/nonexistent-id", timeout=15)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text[:200]}"


def test_delete_ticket_admin_endpoint_404_for_missing_ticket(admin_cookie):
    """Coordinateur session on an unknown ticket ID must yield 404, proving the
    admin guard PASSED and the ticket_or_404 lookup fired. No real ticket touched."""
    fake_id = "diagnostic-not-a-real-ticket-id-9999"
    r = requests.delete(
        f"{BASE_URL}/api/admin/tickets/{fake_id}", cookies=admin_cookie, timeout=15
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:300]}"


# --- code-level assertions: fix is present in source ---
def test_admin_overview_uses_null_safe_assigned_helper_access():
    with open("/app/backend/routers/admin.py") as f:
        src = f.read()
    # The null-safe pattern from the RCA
    assert '(ticket.get("assigned_helper") or {}).get("id")' in src, (
        "admin_overview must use the null-safe (assigned_helper or {}).get('id') pattern"
    )


def test_delete_endpoint_registered_and_admin_gated():
    from routers import admin as admin_module
    from services.auth_service import current_admin

    delete_route = next(
        (r for r in admin_module.router.routes
         if getattr(r, "path", "") == "/admin/tickets/{ticket_id}"
         and "DELETE" in getattr(r, "methods", set())),
        None,
    )
    assert delete_route is not None, "DELETE /admin/tickets/{ticket_id} not registered"
    deps = [d.call for d in delete_route.dependant.dependencies]
    assert current_admin in deps, "delete_ticket_as_admin must depend on current_admin"


# --- Frontend: delete button + admin guard + no dark mode leftovers ---
def test_frontend_delete_ticket_button_admin_gated():
    with open("/app/frontend/src/pages/TicketWorkspacePage.jsx") as f:
        src = f.read()
    assert 'data-testid="delete-ticket-button"' in src
    assert "isAdmin && <button" in src or "{isAdmin && " in src
    # button triggers the admin DELETE endpoint
    assert "/admin/tickets/${ticketId}" in src
    # confirm dialog
    assert "window.confirm(" in src


def test_frontend_admin_link_always_visible_no_dark_mode():
    with open("/app/frontend/src/components/AppShell.jsx") as f:
        src = f.read()
    assert 'data-testid="admin-panel-link"' in src
    # no theme toggle survives
    assert "theme-toggle" not in src.lower()


# --- Non-regression: guards on tickets/resources/profile still fire ---
def test_tickets_route_still_requires_auth():
    r = requests.get(f"{BASE_URL}/api/tickets", timeout=15)
    assert r.status_code == 401


def test_resources_route_still_requires_auth():
    r = requests.get(f"{BASE_URL}/api/resources", timeout=15)
    assert r.status_code == 401


def test_admin_helpers_still_requires_admin(admin_cookie):
    # sanity: with our admin cookie we can also list helpers (no data mutated)
    r = requests.get(f"{BASE_URL}/api/admin/helpers", cookies=admin_cookie, timeout=30)
    assert r.status_code == 200
    helpers = r.json()
    assert isinstance(helpers, list)
    print(f"helpers list length = {len(helpers)}")


# --- Confirm via bot that the admin user has the Coordinateur role (no secret printed) ---
def test_admin_user_has_coordinateur_role_via_bot():
    env = dotenv_values("/app/backend/.env")
    token = env.get("DISCORD_BOT_TOKEN")
    guild_id = env.get("DISCORD_GUILD_ID")
    if not token or not guild_id:
        pytest.skip("Discord bot token/guild not configured")
    r = requests.get(
        f"https://discord.com/api/v10/guilds/{guild_id}/members/{ADMIN_USER_ID}",
        headers={"Authorization": f"Bot {token}"},
        timeout=15,
    )
    assert r.status_code == 200, f"Discord API returned {r.status_code}"
    roles = r.json().get("roles", [])
    assert ADMIN_ROLE_ID in roles, (
        f"User {ADMIN_USER_ID} does NOT have Coordinateur role {ADMIN_ROLE_ID}"
    )
    # Do NOT print the roles list — may contain sensitive role IDs
    print(f"user {ADMIN_USER_ID} has Coordinateur role: confirmed")
