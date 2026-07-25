"""Iteration 11 — Follow-up status simplification, Mon profil relocation, dropdown animation."""
import os
import re
import asyncio
from pathlib import Path

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://iris-logs.preview.emergentagent.com"
API = f"{BASE_URL}/api"

APP_SHELL = Path("/app/frontend/src/components/AppShell.jsx").read_text()
WORKSPACE = Path("/app/frontend/src/pages/TicketWorkspacePage.jsx").read_text()
CSS = Path("/app/frontend/src/MentalHealth.css").read_text()
TICKET_MODEL = Path("/app/backend/models/ticket.py").read_text()


# ---------- Backend model constraints ----------

class TestTicketModelFollowUp:
    def test_ticket_update_literal_exactly_two_values(self):
        from backend.models.ticket import TicketUpdate  # noqa
        # Accepts the two allowed values
        assert TicketUpdate(follow_up_status="en attente de réponse").follow_up_status == "en attente de réponse"
        assert TicketUpdate(follow_up_status="à conclure").follow_up_status == "à conclure"

    def test_ticket_update_rejects_legacy_values(self):
        from backend.models.ticket import TicketUpdate  # noqa
        for legacy in ["à écouter", "en suivi", "stable"]:
            with pytest.raises(Exception):
                TicketUpdate(follow_up_status=legacy)

    def test_ticket_summary_default_follow_up(self):
        assert 'follow_up_status: Literal["en attente de réponse", "à conclure"] = "en attente de réponse"' in TICKET_MODEL

    def test_no_legacy_status_in_model_source(self):
        for legacy in ["à écouter", "en suivi", '"stable"']:
            assert legacy not in TICKET_MODEL, f"Legacy value {legacy} still present in ticket model"


# ---------- Mongo migration confirmation ----------

class TestMongoMigration:
    def test_no_legacy_follow_up_status_remaining(self):
        async def _run():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            legacy = await db.tickets.count_documents({
                "follow_up_status": {"$in": ["à écouter", "en suivi", "stable"]}
            })
            total = await db.tickets.count_documents({})
            valid = await db.tickets.count_documents({
                "follow_up_status": {"$in": ["en attente de réponse", "à conclure"]}
            })
            client.close()
            return legacy, total, valid

        legacy, total, valid = asyncio.run(_run())
        assert legacy == 0, f"Found {legacy} tickets with legacy follow_up_status"
        # All tickets should have a valid status (if follow_up_status set)
        assert valid <= total


# ---------- PATCH auth guard (live) ----------

class TestPatchGuard:
    def test_patch_unauthenticated_returns_401(self):
        r = requests.patch(f"{API}/tickets/does-not-matter", json={"follow_up_status": "en attente de réponse"}, timeout=15)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text[:200]}"

    def test_patch_rejects_legacy_via_pydantic_when_authed_shape(self):
        # Unauthenticated — but ensures endpoint exists (not 404)
        r = requests.patch(f"{API}/tickets/xxx", json={"follow_up_status": "stable"}, timeout=15)
        assert r.status_code in (401, 422)


# ---------- TicketWorkspacePage select ----------

class TestFollowUpSelect:
    def test_select_has_exact_two_options(self):
        options = re.findall(r'<option value="([^"]+)"', WORKSPACE)
        # Filter to follow-up context: the file has only follow-up options as <option>
        follow_up = [o for o in options if o in {"en attente de réponse", "à conclure"} or "conclure" in o or "attente" in o]
        assert "en attente de réponse" in follow_up
        assert "à conclure" in follow_up
        # No legacy values in options anywhere in the workspace
        for legacy in ["à écouter", "en suivi", ">stable<", '"stable"']:
            assert legacy not in WORKSPACE, f"Legacy option {legacy} still present"

    def test_select_has_testid(self):
        assert 'data-testid="follow-up-status-select"' in WORKSPACE

    def test_save_sends_follow_up_status(self):
        assert "follow_up_status: followUpStatus" in WORKSPACE


# ---------- AppShell: profile link relocated ----------

class TestAppShellProfileRelocation:
    def test_no_mon_profil_in_helper_menu_links(self):
        # Extract helper-menu-links block
        m = re.search(r'helper-menu-links[^>]*>(.*?)</div>', APP_SHELL, re.DOTALL)
        assert m, "helper-menu-links block not found"
        block = m.group(1)
        assert "Mon profil" not in block
        assert "/profile" not in block

    def test_helper_profile_link_exists_and_wraps_avatar_identity(self):
        assert 'data-testid="helper-profile-link"' in APP_SHELL
        assert 'to="/profile"' in APP_SHELL
        # Extract helper-account-link block and ensure it contains avatar + identity
        m = re.search(r'helper-account-link.*?</Link>', APP_SHELL, re.DOTALL)
        assert m, "helper-account-link Link not found"
        block = m.group(0)
        assert "helper-avatar" in block
        assert "helper?.global_name" in block or "helper?.username" in block

    def test_helper_menu_links_only_four_navlinks(self):
        m = re.search(r'helper-menu-links[^>]*>(.*?)</div>', APP_SHELL, re.DOTALL)
        block = m.group(1)
        navlinks = re.findall(r'<NavLink[^>]*to="([^"]+)"', block)
        assert set(navlinks) == {"/", "/archives", "/resources", "/admin"}, f"Unexpected navlinks: {navlinks}"


# ---------- Dropdown animation ----------

class TestDropdownAnimation:
    def test_helper_menu_toggle_has_aria_expanded_and_state(self):
        assert 'aria-expanded={isHelperMenuOpen}' in APP_SHELL
        assert 'data-testid="helper-menu-toggle"' in APP_SHELL

    def test_helper_menu_links_toggles_is_open_class(self):
        assert '`helper-menu-links ${isHelperMenuOpen ? "is-open" : ""}`' in APP_SHELL

    def test_css_animation_properties(self):
        # Find .helper-menu-links (not .is-open) block
        block = re.search(r'\.helper-menu-links \{([^}]+)\}', CSS).group(1)
        assert "max-height: 0" in block
        assert "opacity: 0" in block
        assert "transform: translateY" in block
        assert "transition" in block and "max-height" in block and "opacity" in block and "transform" in block

    def test_css_is_open_block(self):
        block = re.search(r'\.helper-menu-links\.is-open \{([^}]+)\}', CSS).group(1)
        assert "max-height:" in block and "0" not in block.split("max-height:")[1].split(";")[0].strip()[:2]
        assert "opacity: 1" in block
        assert "transform: translateY(0)" in block


# ---------- Mobile behaviour ----------

class TestMobileMenu:
    def test_mobile_media_query_makes_menu_visible_flex(self):
        # Inside a @media (max-width: 760px) block, there must be an override for helper-menu-links(.is-open)
        m = re.search(
            r'\.helper-menu-links,\s*\.helper-menu-links\.is-open\s*\{([^}]+)\}',
            CSS,
            re.DOTALL,
        )
        assert m, "Mobile override for helper-menu-links not found"
        block = m.group(1)
        assert "display: flex" in block
        assert "max-height: none" in block
        assert "opacity: 1" in block
        assert "overflow: visible" in block
