"""Backend tests for the new POST /api/tickets/demo mental-health case
creation endpoint plus TicketUpdate follow_up_status support.

Covers:
- 401 without session
- 201 with demo session, returns SUIVI-* id
- Response has no _id (Mongo ObjectId leakage)
- Field validation (name/reason length, priority/follow_up_status enums)
- Persistence: created ticket is retrievable via GET /api/tickets/{id}
- follow_up_status can be updated via PATCH and persists after reload
"""
import os
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def demo_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    r = session.post(f"{BASE_URL}/api/auth/demo-session", timeout=15)
    assert r.status_code == 200, r.text
    return session


@pytest.fixture(scope="module")
def created_ids():
    return []


# --- Security ---
class TestDemoCreationAuth:
    def test_post_demo_requires_session(self):
        r = requests.post(
            f"{BASE_URL}/api/tickets/demo",
            json={"name": "Camille", "reason": "Écoute besoin"},
            timeout=15,
        )
        assert r.status_code == 401


# --- Happy path ---
class TestDemoCreationHappyPath:
    def test_create_minimal_case(self, demo_client, created_ids):
        payload = {"name": "TEST Camille", "reason": "Besoin d'écoute suite anxiété passagère"}
        r = demo_client.post(f"{BASE_URL}/api/tickets/demo", json=payload, timeout=15)
        assert r.status_code == 201, r.text
        body = r.json()
        # Response shape
        assert body["id"].startswith("SUIVI-")
        assert body["title"] == payload["reason"]
        assert body["member"]["display_name"] == "TEST Camille"
        assert body["status"] == "active"
        assert body["priority"] == "routine"
        assert body["follow_up_status"] == "à écouter"
        assert body["is_demo"] is True
        assert body["notes"] == ""
        assert body["vocal_summary"] == ""
        assert len(body["transcript"]) == 1
        # Mongo _id must not leak
        assert "_id" not in body
        assert '"_id"' not in r.text
        created_ids.append(body["id"])

    def test_create_with_all_fields(self, demo_client, created_ids):
        payload = {
            "name": "TEST Alex",
            "reason": "Isolement et sommeil difficile",
            "priority": "prioritaire",
            "follow_up_status": "en suivi",
        }
        r = demo_client.post(f"{BASE_URL}/api/tickets/demo", json=payload, timeout=15)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["priority"] == "prioritaire"
        assert body["follow_up_status"] == "en suivi"
        created_ids.append(body["id"])

    def test_created_case_is_retrievable(self, demo_client, created_ids):
        assert created_ids, "no case created in previous tests"
        for cid in created_ids:
            r = demo_client.get(f"{BASE_URL}/api/tickets/{cid}", timeout=15)
            assert r.status_code == 200, f"{cid} -> {r.status_code}"
            body = r.json()
            assert body["id"] == cid
            assert body["is_demo"] is True
            assert '"_id"' not in r.text

    def test_created_case_appears_in_list(self, demo_client, created_ids):
        r = demo_client.get(f"{BASE_URL}/api/tickets", timeout=15)
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        for cid in created_ids:
            assert cid in ids, f"{cid} not in list"


# --- Validation ---
class TestDemoCreationValidation:
    def test_name_too_short(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/tickets/demo",
            json={"name": "A", "reason": "Motif suffisamment long"},
            timeout=15,
        )
        assert r.status_code == 422

    def test_reason_too_short(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/tickets/demo",
            json={"name": "Camille", "reason": "ok"},
            timeout=15,
        )
        # min_length=3 -> "ok" is 2, should be 422; but 3 chars is boundary
        assert r.status_code == 422

    def test_invalid_priority(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/tickets/demo",
            json={"name": "Camille", "reason": "Motif adéquat", "priority": "invalid"},
            timeout=15,
        )
        assert r.status_code == 422

    def test_invalid_follow_up_status(self, demo_client):
        r = demo_client.post(
            f"{BASE_URL}/api/tickets/demo",
            json={"name": "Camille", "reason": "Motif adéquat", "follow_up_status": "en attente"},
            timeout=15,
        )
        assert r.status_code == 422


# --- PATCH follow_up_status persistence ---
class TestFollowUpStatusPersistence:
    def test_patch_follow_up_status(self, demo_client):
        # Create a case first
        create = demo_client.post(
            f"{BASE_URL}/api/tickets/demo",
            json={"name": "TEST Suivi", "reason": "Vérification statut suivi"},
            timeout=15,
        )
        assert create.status_code == 201
        cid = create.json()["id"]
        assert create.json()["follow_up_status"] == "à écouter"

        # PATCH follow_up_status
        patch = demo_client.patch(
            f"{BASE_URL}/api/tickets/{cid}",
            json={"follow_up_status": "stable", "notes": "TEST notes", "vocal_summary": "TEST vocal"},
            timeout=15,
        )
        assert patch.status_code == 200, patch.text
        body = patch.json()
        assert body["follow_up_status"] == "stable"
        assert body["notes"] == "TEST notes"
        assert body["vocal_summary"] == "TEST vocal"

        # GET verifies persistence
        get = demo_client.get(f"{BASE_URL}/api/tickets/{cid}", timeout=15)
        g = get.json()
        assert g["follow_up_status"] == "stable"
        assert g["notes"] == "TEST notes"
        assert g["vocal_summary"] == "TEST vocal"


# --- Mental-health vocabulary regression ---
class TestSeedMentalHealthVocabulary:
    def test_seed_titles_are_mental_health(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/tickets", timeout=15)
        assert r.status_code == 200
        by_id = {t["id"]: t for t in r.json()}
        assert "Anxiété" in by_id["TKT-0891"]["title"]
        assert "Isolement" in by_id["TKT-0890"]["title"]
        assert "proche" in by_id["TKT-0888"]["title"].lower()

    def test_seed_has_follow_up_and_priority(self, demo_client):
        for tid in ("TKT-0888", "TKT-0890", "TKT-0891"):
            r = demo_client.get(f"{BASE_URL}/api/tickets/{tid}", timeout=15)
            assert r.status_code == 200
            body = r.json()
            assert body["follow_up_status"] in {"à écouter", "en suivi", "stable"}
            assert body["priority"] in {"routine", "prioritaire", "urgent"}
