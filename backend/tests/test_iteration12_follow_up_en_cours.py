"""Iteration 12 — validate 'en cours' intermediate follow_up_status."""
import os
import re
from pathlib import Path

import pytest
import requests
from pydantic import ValidationError

from models.ticket import TicketSummary, TicketUpdate

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ALLOWED = ("en attente de réponse", "en cours", "à conclure")
LEGACY = ("à écouter", "en suivi", "stable")


# --- backend Pydantic models ---
class TestTicketUpdateModel:
    @pytest.mark.parametrize("value", ALLOWED)
    def test_accepts_all_three_values(self, value):
        m = TicketUpdate(follow_up_status=value)
        assert m.follow_up_status == value

    @pytest.mark.parametrize("value", LEGACY + ("random", "En Cours", "EN COURS", ""))
    def test_rejects_legacy_and_invalid(self, value):
        with pytest.raises(ValidationError):
            TicketUpdate(follow_up_status=value)


class TestTicketSummaryModel:
    _base = dict(
        id="TKT-1",
        title="t",
        member={"id": "1" * 18, "username": "u"},
        channel_id="1" * 18,
        channel_name="c",
        status="active",
        message_count=0,
        updated_at="2025-01-01T00:00:00Z",
        created_at="2025-01-01T00:00:00Z",
    )

    @pytest.mark.parametrize("value", ALLOWED)
    def test_accepts_all_three(self, value):
        m = TicketSummary(**self._base, follow_up_status=value)
        assert m.follow_up_status == value

    @pytest.mark.parametrize("value", LEGACY)
    def test_rejects_legacy(self, value):
        with pytest.raises(ValidationError):
            TicketSummary(**self._base, follow_up_status=value)

    def test_default_is_en_attente(self):
        m = TicketSummary(**self._base)
        assert m.follow_up_status == "en attente de réponse"


# --- frontend JSX select ---
JSX = Path("/app/frontend/src/pages/TicketWorkspacePage.jsx").read_text(encoding="utf-8")


class TestFrontendSelect:
    def test_testid_present(self):
        assert 'data-testid="follow-up-status-select"' in JSX

    def test_three_options_in_order(self):
        # Extract options inside the select
        select_block = re.search(
            r'data-testid="follow-up-status-select".*?</select>',
            JSX,
            re.DOTALL,
        )
        assert select_block, "select block not found"
        opts = re.findall(r'<option value="([^"]+)"', select_block.group(0))
        assert opts == list(ALLOWED), f"got {opts}"

    def test_no_legacy_strings_in_file(self):
        for legacy in LEGACY:
            assert legacy not in JSX, f"legacy value '{legacy}' leaked in JSX"

    def test_save_sends_follow_up_status_via_patch(self):
        assert re.search(
            r"api\.patch\(`/tickets/\$\{ticketId\}`,\s*\{[^}]*follow_up_status",
            JSX,
            re.DOTALL,
        ), "PATCH payload does not include follow_up_status"


# --- backend router: guard current_helper + no legacy strings ---
ROUTER = Path("/app/backend/routers/tickets.py").read_text(encoding="utf-8")
MODEL_FILE = Path("/app/backend/models/ticket.py").read_text(encoding="utf-8")


class TestBackendGuards:
    def test_patch_endpoint_uses_current_helper(self):
        # Find update_ticket function and its dependency
        m = re.search(
            r'@router\.patch\("/\{ticket_id\}".*?async def update_ticket\([^)]*\)',
            ROUTER,
            re.DOTALL,
        )
        assert m, "update_ticket not found"
        assert "Depends(current_helper)" in m.group(0)

    def test_no_legacy_strings_in_backend(self):
        for legacy in LEGACY:
            assert legacy not in MODEL_FILE
            assert legacy not in ROUTER

    def test_model_has_three_values_literal(self):
        # both TicketUpdate and TicketSummary should list all three
        for name in ("TicketUpdate", "TicketSummary"):
            block = re.search(rf"class {name}.*?(?=\nclass |\Z)", MODEL_FILE, re.DOTALL).group(0)
            for v in ALLOWED:
                assert v in block, f"{v} missing in {name}"


# --- live PATCH endpoint requires auth (401) ---
class TestLiveAuthGuard:
    def test_patch_unauthenticated_returns_401(self):
        r = requests.patch(
            f"{API}/tickets/does-not-matter",
            json={"follow_up_status": "en cours"},
            timeout=10,
        )
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_patch_with_invalid_value_still_401_unauth(self):
        # unauthenticated shortcut - won't reach validation
        r = requests.patch(
            f"{API}/tickets/x",
            json={"follow_up_status": "à écouter"},
            timeout=10,
        )
        assert r.status_code == 401


# --- non-regression: helper profile relocation ---
APPSHELL = Path("/app/frontend/src/components/AppShell.jsx")


class TestAppShellRegression:
    def test_appshell_exists(self):
        assert APPSHELL.exists()

    def test_helper_profile_link_present(self):
        content = APPSHELL.read_text(encoding="utf-8")
        assert 'data-testid="helper-profile-link"' in content or 'to="/profile"' in content
