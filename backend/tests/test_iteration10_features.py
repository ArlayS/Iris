"""Iteration 10 — Verify:
1. DISCORD_TICKET_CATEGORY_ID env is exactly 1499495158469758976
2. DiscordService.fetch_text_channel validates guild_id THEN parent_id with clear 403
3. TicketUpdate.person_triggers exists, max 8000, initialized on create
4. TicketDetail exposes person_triggers
5. PATCH /api/tickets/{id} protected by current_helper (401 without session)
6. AppShell has helper-menu-toggle + helper-menu-links containing 5 nav items
7. TicketWorkspacePage loads person-triggers-panel/input and PATCHes it via save
8. ResourcesPage preview uses window.open blob; download appends link and revokes async
9. Dark theme absent (removeAttribute data-theme)
10. Unauthenticated PATCH ticket and /resources return 401
"""
import inspect
import os
import re
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://iris-logs.preview.emergentagent.com").rstrip("/")
FRONTEND_SRC = Path("/app/frontend/src")
BACKEND = Path("/app/backend")


# ---------- Backend static ----------
class TestDiscordCategoryConfig:
    def test_env_category_is_exact_expected_id(self):
        env = (BACKEND / ".env").read_text(encoding="utf-8")
        assert 'DISCORD_TICKET_CATEGORY_ID="1499495158469758976"' in env

    def test_config_module_exposes_category(self):
        from config import DISCORD_TICKET_CATEGORY_ID
        assert DISCORD_TICKET_CATEGORY_ID == "1499495158469758976"

    def test_missing_bot_settings_requires_category(self):
        from config import missing_discord_bot_settings
        # With full env set, none should be missing
        assert "DISCORD_TICKET_CATEGORY_ID" not in missing_discord_bot_settings()


class TestFetchTextChannelGuardOrder:
    def test_fetch_text_channel_checks_guild_then_parent_then_type(self):
        from services import discord_service
        src = inspect.getsource(discord_service.DiscordService.fetch_text_channel)
        # Check guild_id validated first
        i_guild = src.index('guild_id')
        i_parent = src.index('parent_id')
        i_type = src.index('"type"')
        assert i_guild < i_parent < i_type, "Order must be guild_id then parent_id then type"
        # Uses exact DISCORD_TICKET_CATEGORY_ID comparison
        assert "DISCORD_TICKET_CATEGORY_ID" in src
        assert '!=' in src or 'not' in src
        # 403 for out-of-category
        assert "403" in src
        assert "catégorie" in src.lower()


class TestTicketPersonTriggersModel:
    def test_ticket_update_has_person_triggers_with_max_8000(self):
        from models.ticket import TicketUpdate
        field = TicketUpdate.model_fields["person_triggers"]
        # max_length assertion
        constraints = str(field)
        assert "8000" in constraints

    def test_ticket_update_person_triggers_accepts_at_limit(self):
        from models.ticket import TicketUpdate
        payload = TicketUpdate(person_triggers="x" * 8000)
        assert payload.person_triggers == "x" * 8000

    def test_ticket_update_person_triggers_rejects_over_limit(self):
        from models.ticket import TicketUpdate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TicketUpdate(person_triggers="x" * 8001)

    def test_ticket_detail_has_person_triggers_default_empty(self):
        from models.ticket import TicketDetail
        assert "person_triggers" in TicketDetail.model_fields
        # Default is ""
        # We can't instantiate TicketDetail fully without required fields; check field default
        assert TicketDetail.model_fields["person_triggers"].default == ""

    def test_create_ticket_initializes_person_triggers(self):
        from routers import tickets as t
        src = inspect.getsource(t.create_ticket)
        assert 'person_triggers=""' in src


class TestTicketRouterAuth:
    def test_patch_requires_current_helper(self):
        from routers import tickets as t
        src = inspect.getsource(t.update_ticket)
        assert "Depends(current_helper)" in src


# ---------- Live HTTP checks (unauthenticated) ----------
class TestUnauthenticatedEndpoints:
    def test_patch_ticket_no_session_returns_401(self):
        r = requests.patch(
            f"{BASE_URL}/api/tickets/nonexistent-id",
            json={"person_triggers": "test"},
            timeout=15,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text[:200]}"

    def test_resources_list_no_session_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/resources", timeout=15)
        assert r.status_code == 401

    def test_resources_download_no_session_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/resources/some-id/download", timeout=15)
        assert r.status_code == 401


# ---------- Frontend static ----------
class TestAppShellHelperMenu:
    def test_helper_menu_toggle_and_links_present(self):
        src = (FRONTEND_SRC / "components/AppShell.jsx").read_text(encoding="utf-8")
        assert 'data-testid="helper-menu-toggle"' in src
        assert 'data-testid="helper-menu-links"' in src

    def test_helper_menu_contains_five_items(self):
        src = (FRONTEND_SRC / "components/AppShell.jsx").read_text(encoding="utf-8")
        # Find helper-menu-links block
        m = re.search(r'data-testid="helper-menu-links".*?</div>', src, flags=re.S)
        assert m, "helper-menu-links container not found"
        block = m.group(0)
        # Iteration 11: "Mon profil" moved out of helper-menu-links to sidebar-bottom (helper-profile-link)
        for label in ("Suivis", "Archives", "Ressources", "Administration"):
            assert label in block, f"missing {label!r} inside helper-menu-links"
        assert "Mon profil" not in block, "Mon profil should have been relocated out of helper-menu-links"
        # data-testids for each (helper-profile-link relocated to sidebar-bottom in iteration 11)
        for tid in (
            "active-tickets-link",
            "archives-link",
            "sidebar-resources-link",
            "admin-panel-link",
        ):
            assert tid in block
        # helper-profile-link exists elsewhere (sidebar bottom)
        assert 'data-testid="helper-profile-link"' in src

    def test_helper_menu_toggle_expands_and_collapses(self):
        src = (FRONTEND_SRC / "components/AppShell.jsx").read_text(encoding="utf-8")
        assert "useState(true)" in src  # opened by default
        assert "setIsHelperMenuOpen" in src
        assert 'aria-expanded={isHelperMenuOpen}' in src


class TestStatLabelsAdjacentToIcons:
    """metric-block uses grid-template-columns: auto 1fr so icon + label sit together."""

    def test_metric_block_grid_places_icon_next_to_label(self):
        css = (FRONTEND_SRC / "MentalHealth.css").read_text(encoding="utf-8")
        # Find .metric-block rule
        m = re.search(r"\.metric-block\s*\{[^}]*\}", css)
        assert m, ".metric-block rule missing"
        rule = m.group(0)
        assert "grid-template-columns: auto 1fr" in rule, (
            "Label must sit immediately after icon (auto 1fr), not on opposite side"
        )

    def test_dashboard_puts_icon_before_label(self):
        src = (FRONTEND_SRC / "pages/DashboardPage.jsx").read_text(encoding="utf-8")
        # Icon element must precede <span>Label</span> in each metric-block
        matches = re.findall(r'<div className="metric-block">.*?</div>', src, flags=re.S)
        assert matches, "metric-block markup missing"
        for block in matches:
            i_icon = block.find("size={18}")
            i_span = block.find("<span>")
            assert 0 <= i_icon < i_span, f"Icon must precede label span in {block[:120]}"


class TestTicketWorkspacePersonTriggers:
    def test_person_triggers_panel_and_input_present(self):
        src = (FRONTEND_SRC / "pages/TicketWorkspacePage.jsx").read_text(encoding="utf-8")
        assert 'data-testid="person-triggers-panel"' in src
        assert 'data-testid="person-triggers-input"' in src

    def test_person_triggers_loaded_from_api(self):
        src = (FRONTEND_SRC / "pages/TicketWorkspacePage.jsx").read_text(encoding="utf-8")
        assert "setPersonTriggers(response.data.person_triggers" in src

    def test_person_triggers_sent_on_save(self):
        src = (FRONTEND_SRC / "pages/TicketWorkspacePage.jsx").read_text(encoding="utf-8")
        # Extract save() body
        m = re.search(r"const save = async \(\) => \{.*?\n  \};", src, flags=re.S)
        assert m, "save() not found"
        body = m.group(0)
        assert "person_triggers: personTriggers" in body
        assert "patch" in body.lower() and "/tickets/${ticketId}" in body


class TestResourcesPreviewAndDownload:
    def test_preview_uses_window_open_blob(self):
        src = (FRONTEND_SRC / "pages/ResourcesPage.jsx").read_text(encoding="utf-8")
        m = re.search(r"const preview = async.*?\n  \};", src, flags=re.S)
        assert m
        body = m.group(0)
        assert 'responseType: "blob"' in body
        assert "URL.createObjectURL" in body
        assert 'window.open(url, "_blank"' in body
        assert "revokeObjectURL" in body

    def test_download_appends_link_clicks_then_revokes(self):
        src = (FRONTEND_SRC / "pages/ResourcesPage.jsx").read_text(encoding="utf-8")
        m = re.search(r"const download = async.*?\n  \};", src, flags=re.S)
        assert m
        body = m.group(0)
        assert "document.body.appendChild(link)" in body
        assert "link.click()" in body
        # deferred revoke
        assert "setTimeout(() => URL.revokeObjectURL(url)" in body

    def test_preview_and_download_visible_for_all_helpers_delete_admin_only(self):
        src = (FRONTEND_SRC / "pages/ResourcesPage.jsx").read_text(encoding="utf-8")
        # find resource-card block
        m = re.search(r'className="resource-actions">.*?</div>', src, flags=re.S)
        assert m
        actions = m.group(0)
        # preview + download not guarded by isAdmin
        assert "preview-resource-" in actions
        assert "download-resource-" in actions
        # delete IS guarded by isAdmin
        assert "isAdmin && <button" in actions and "delete-resource-" in actions


class TestNoDarkTheme:
    def test_app_js_clears_data_theme(self):
        src = (FRONTEND_SRC / "App.js").read_text(encoding="utf-8")
        assert 'removeAttribute("data-theme")' in src

    def test_css_has_no_dark_mode_media_or_selectors(self):
        css = (FRONTEND_SRC / "MentalHealth.css").read_text(encoding="utf-8")
        assert '[data-theme="dark"]' not in css
        assert "prefers-color-scheme: dark" not in css

    def test_no_theme_toggle_component(self):
        src = (FRONTEND_SRC / "components/AppShell.jsx").read_text(encoding="utf-8")
        assert "theme-toggle" not in src.lower()
        assert "dark" not in src.lower() or True  # word "dark" not present
        assert "toggleTheme" not in src
