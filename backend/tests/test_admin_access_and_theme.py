"""Iteration 9 — verify admin role env, admin route guards, no dark-mode leftovers."""
import os
import re
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://iris-logs.preview.emergentagent.com").rstrip("/")


# --- Config: Discord admin role ID must be the exact value ---
def test_discord_admin_role_id_is_expected():
    """The .env must configure DISCORD_ADMIN_ROLE_ID = 1503100661728936046 (Coordinateur)."""
    from dotenv import dotenv_values
    values = dotenv_values("/app/backend/.env")
    assert values.get("DISCORD_ADMIN_ROLE_ID") == "1503100661728936046"


# --- Admin routes: 401 without session ---
def test_admin_overview_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/overview", timeout=15)
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


def test_admin_helpers_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/helpers", timeout=15)
    assert r.status_code == 401


def test_admin_assignment_requires_auth():
    r = requests.patch(f"{BASE_URL}/api/admin/tickets/nonexistent/assignment",
                       json={"helper_id": None}, timeout=15)
    assert r.status_code == 401


# --- current_admin is still the guard on admin router ---
def test_current_admin_is_guard_on_admin_router():
    from routers import admin as admin_module
    from services.auth_service import current_admin
    for route in admin_module.router.routes:
        deps = getattr(route, "dependant", None)
        if deps is None:
            continue
        dep_callables = [d.call for d in deps.dependencies]
        assert current_admin in dep_callables, (
            f"Route {route.path} does not depend on current_admin"
        )


# --- AppShell renders admin-panel-link unconditionally ---
def test_appshell_renders_admin_link_unconditionally():
    with open("/app/frontend/src/components/AppShell.jsx") as f:
        source = f.read()
    assert 'data-testid="admin-panel-link"' in source
    # ensure no isAdmin conditional wrapping the admin link
    # find the line with admin-panel-link and preceding context
    idx = source.index('data-testid="admin-panel-link"')
    snippet = source[max(0, idx - 400):idx]
    assert "isAdmin &&" not in snippet, "admin link is still isAdmin-gated in AppShell"


# --- AdminDashboardPage: retry button + Coordinateur reconnect copy ---
def test_admin_dashboard_error_state_has_retry_and_role_copy():
    with open("/app/frontend/src/pages/AdminDashboardPage.jsx") as f:
        source = f.read()
    assert 'data-testid="admin-access-error"' in source
    assert 'data-testid="retry-admin-access-button"' in source
    assert "Coordinateur" in source
    assert "reconnect" in source.lower() or "reconnectez" in source.lower()


# --- Dark mode removal ---
def test_no_theme_toggle_buttons_in_source():
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "-E",
         "theme-toggle-button|mobile-theme-toggle-button|data-testid=\"theme-",
         "/app/frontend/src"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0 or result.stdout.strip() == "", (
        f"Found theme toggle refs: {result.stdout}"
    )


def test_app_js_clears_theme_and_localstorage_key():
    with open("/app/frontend/src/App.js") as f:
        source = f.read()
    assert 'removeAttribute("data-theme")' in source
    assert 'removeItem("iris-theme")' in source


def test_no_dark_theme_toggle_logic():
    """No setState/localStorage set for iris-theme anywhere."""
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "setItem.*iris-theme", "/app/frontend/src"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0 or result.stdout.strip() == ""


def test_html_has_no_data_theme_attribute():
    """The served HTML should not contain a data-theme attribute."""
    r = requests.get(BASE_URL, timeout=15)
    assert r.status_code == 200
    assert 'data-theme="dark"' not in r.text
    assert 'data-theme=dark' not in r.text


# --- Login page loads ---
def test_login_page_loads():
    r = requests.get(BASE_URL, timeout=15)
    assert r.status_code == 200
    # SPA shell — actual content is injected by React; verify HTML doc served
    assert "<!doctype html>" in r.text.lower()


# --- Resources & existing admin features do not regress ---
def test_resources_route_requires_auth():
    r = requests.get(f"{BASE_URL}/api/resources", timeout=15)
    assert r.status_code == 401


def test_tickets_route_requires_auth():
    r = requests.get(f"{BASE_URL}/api/tickets", timeout=15)
    assert r.status_code == 401


def test_auth_session_anonymous():
    r = requests.get(f"{BASE_URL}/api/auth/session", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("authenticated") is False
