"""
Iteration 8 regression tests.

Covers:
  1. Contrast fix: MentalHealth.css sets explicit color on .column-header /
     .category-badge / theme-toggle in light AND dark mode (no white-on-white).
  2. RBAC on /api/profile/me (GET+PUT) - 401 without session, no cross-helper
     read path exists in profiles router.
  3. Notes endpoints - POST /api/tickets/{id}/notes and DELETE both require a
     session (401) and delete enforces "author OR admin".
  4. Admin overview is the ONLY place that surfaces triggers to another helper.
  5. Frontend static invariants for the theme toggle, HelperProfilePage,
     multi-note form, profile link, admin trigger card.
  6. Theme persistence via localStorage 'iris-theme' + data-theme attribute.
  7. Discord admin role id from env is what current_admin checks.
"""

import inspect
import os
import re
from pathlib import Path

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://iris-logs.preview.emergentagent.com").rstrip("/")
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


# -------- 1. Contrast (light + dark) --------
class TestContrastFix:
    def setup_method(self):
        self.css = (FRONTEND_SRC / "MentalHealth.css").read_text(encoding="utf-8")

    def test_column_header_has_explicit_dark_text_in_light_mode(self):
        # .column-header block (light) must set a non-white color.
        match = re.search(r"^\.column-header\s*\{([^}]*)\}", self.css, re.MULTILINE)
        assert match, ".column-header rule not found"
        body = match.group(1)
        assert "color:" in body
        assert "#fff" not in body.lower() and "#ffffff" not in body.lower()

    def test_category_badge_has_white_on_dark_background(self):
        match = re.search(r"^\.category-badge\s*\{([^}]*)\}", self.css, re.MULTILINE)
        assert match
        body = match.group(1).lower()
        # Dark green bg + white text.
        assert "background:" in body
        assert "color: #ffffff" in body or "color:#ffffff" in body or "color: #fff" in body

    def test_dark_mode_overrides_column_header_text(self):
        # In dark mode, column-header must be overridden (not left white on white).
        assert '.App[data-theme="dark"] .column-header' in self.css
        assert '.App[data-theme="dark"] .category-badge' in self.css


# -------- 2. Profile RBAC --------
class TestProfileRbac:
    def test_get_profile_me_requires_session(self):
        r = requests.get(f"{BASE_URL}/api/profile/me", timeout=15)
        assert r.status_code == 401

    def test_put_profile_me_requires_session(self):
        r = requests.put(
            f"{BASE_URL}/api/profile/me", json={"triggers": "x"}, timeout=15
        )
        assert r.status_code == 401

    def test_profiles_router_has_no_cross_helper_read_route(self):
        """A helper must NOT be able to fetch another helper's profile.
        There should be no GET /profile/{helper_id} route."""
        from routers import profiles as profiles_router

        for route in profiles_router.router.routes:
            path = getattr(route, "path", "")
            # Only /me is exposed - no path parameter.
            assert "{" not in path, f"Unexpected parametrized profile route: {path}"
            assert path in ("/profile/me",), f"Unexpected profile route: {path}"

    def test_profile_put_only_writes_own_helper_id(self):
        """update_my_profile must always key by helper.id (never a client-supplied id)."""
        from routers import profiles as profiles_router

        src = inspect.getsource(profiles_router.update_my_profile)
        assert "helper.id" in src
        # No user-controlled helper_id path or body key routed to storage.
        assert "input_data.helper_id" not in src


# -------- 3. Notes RBAC --------
class TestNotesRbac:
    def test_create_note_requires_session(self):
        r = requests.post(
            f"{BASE_URL}/api/tickets/does-not-matter/notes",
            json={"title": "t", "content": "c"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_delete_note_requires_session(self):
        r = requests.delete(
            f"{BASE_URL}/api/tickets/x/notes/y", timeout=15
        )
        assert r.status_code == 401

    def test_delete_note_enforces_author_or_admin(self):
        from routers import tickets as tickets_router

        src = inspect.getsource(tickets_router.delete_ticket_note)
        # The code path must check "author.id != helper.id AND not admin" before 403.
        assert 'note["author"]["id"] != helper.id' in src
        assert "is_admin_helper" in src
        assert "403" in src

    def test_create_note_stores_all_required_fields(self):
        from models.ticket import TicketNote
        fields = set(TicketNote.model_fields.keys())
        assert {"id", "title", "content", "author", "created_at", "updated_at"} <= fields

    def test_note_create_validates_title_and_content(self):
        from models.ticket import TicketNoteCreate

        # Empty title -> validation error
        with pytest.raises(Exception):
            TicketNoteCreate(title="", content="hello")
        with pytest.raises(Exception):
            TicketNoteCreate(title="hi", content="")


# -------- 4. Triggers exposure --------
class TestTriggersExposure:
    def test_only_admin_overview_surfaces_triggers_of_others(self):
        """AdminOverview embeds triggers per helper; no other endpoint does."""
        from routers import admin as admin_router
        from routers import profiles as profiles_router
        from routers import tickets as tickets_router
        from routers import members as members_router

        admin_src = inspect.getsource(admin_router)
        assert "triggers=" in admin_src  # admin_overview reads triggers
        # And it's guarded by current_admin (not current_helper).
        assert "current_admin" in admin_src

        for r in (profiles_router, tickets_router, members_router):
            src = inspect.getsource(r)
            # Only /profile/me returns HelperProfile; make sure no other router
            # leaks triggers.
            if r is profiles_router:
                continue
            assert "triggers" not in src.lower(), (
                f"Non-admin router {r.__name__} references triggers"
            )

    def test_admin_helper_overview_model_has_triggers(self):
        from models.ticket import AdminHelperOverview

        assert "triggers" in AdminHelperOverview.model_fields


# -------- 5 + 6. Frontend static invariants --------
class TestFrontendStatic:
    def read(self, rel):
        return (FRONTEND_SRC / rel).read_text(encoding="utf-8")

    def test_helper_profile_page_has_triggers_input_and_save_button(self):
        src = self.read("pages/HelperProfilePage.jsx")
        assert 'data-testid="helper-triggers-input"' in src
        assert 'data-testid="save-helper-profile-button"' in src
        assert "/profile/me" in src

    def test_app_shell_has_profile_link_and_two_theme_toggles(self):
        src = self.read("components/AppShell.jsx")
        assert 'data-testid="helper-profile-link"' in src
        assert 'data-testid="theme-toggle-button"' in src
        assert 'data-testid="mobile-theme-toggle-button"' in src
        assert 'to="/profile"' in src

    def test_ticket_workspace_has_multi_note_form_and_cards(self):
        src = self.read("pages/TicketWorkspacePage.jsx")
        assert 'data-testid="new-ticket-note-form"' in src
        assert 'data-testid="ticket-note-title-input"' in src
        assert 'data-testid="ticket-note-content-input"' in src
        assert 'data-testid="add-ticket-note-button"' in src
        # per-note card + delete button templated with note id
        assert "data-testid={`ticket-note-${note.id}`}" in src
        assert "data-testid={`delete-note-${note.id}`}" in src
        # delete button visible only for admin or author (defense-in-depth UX)
        assert "isAdmin || note.author.id === helper.id" in src

    def test_admin_dashboard_shows_helper_triggers(self):
        src = self.read("pages/AdminDashboardPage.jsx")
        assert "admin-helper-triggers-" in src
        # Falls back to a French label when triggers are empty.
        assert "Non renseignés" in src

    def test_app_persists_theme_in_localStorage_and_data_theme(self):
        src = self.read("App.js")
        assert 'localStorage.getItem("iris-theme")' in src
        assert 'localStorage.setItem("iris-theme"' in src
        assert 'document.documentElement.dataset.theme = theme' in src
        assert 'data-theme={theme}' in src


# -------- 7. Discord admin role id --------
class TestAdminRoleFromEnv:
    def test_admin_role_id_is_read_from_env(self):
        from config import DISCORD_ADMIN_ROLE_ID
        from services import auth_service

        assert DISCORD_ADMIN_ROLE_ID  # non-empty
        # is_admin_helper checks membership against that role id.
        src = inspect.getsource(auth_service.is_admin_helper)
        assert "DISCORD_ADMIN_ROLE_ID" in src

    def test_admin_endpoints_all_depend_on_current_admin(self):
        from routers import admin as admin_router
        for route in admin_router.router.routes:
            # Each admin endpoint's dependency stack must include current_admin.
            deps = [d.call.__name__ for d in getattr(route, "dependant", None).dependencies]  # type: ignore[union-attr]
            assert "current_admin" in deps, f"admin route {route.path} missing current_admin"


# -------- 8. Guard-rail smoke against the live URL --------
class TestGuardRailsLive:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/admin/overview"),
            ("GET", "/api/admin/helpers"),
            ("PATCH", "/api/admin/tickets/xxx/assignment"),
            ("GET", "/api/profile/me"),
            ("PUT", "/api/profile/me"),
            ("POST", "/api/tickets/xxx/notes"),
            ("DELETE", "/api/tickets/xxx/notes/yyy"),
            ("POST", "/api/tickets/xxx/ai-summary/stream"),
        ],
    )
    def test_endpoint_requires_session(self, method, path):
        r = requests.request(
            method, f"{BASE_URL}{path}", json={}, timeout=15
        )
        assert r.status_code in (401,), (
            f"{method} {path} returned {r.status_code}, expected 401"
        )
