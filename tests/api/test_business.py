from __future__ import annotations

import hashlib
import hmac
import json
import os
import unittest
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select


TEST_DB = Path(f"test-api-{uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB.as_posix()}"
os.environ["APP_MODE"] = "DEMO"
os.environ["CONNECTOR_MODE"] = "demo"
os.environ["INTERNAL_KEY"] = "test-internal-key"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["AUTO_CREATE_SCHEMA"] = "false"

from apps.api.database import Base, SessionLocal, engine  # noqa: E402
from apps.api.main import app  # noqa: E402
from apps.api.models import (ChecklistItem, ExternalResource, Onboarding, OnboardingTemplateVersion,
                             OutboxEmail, PortalInvite, SimResource, TaskCard, User, WorkflowDispatch,
                             Workspace, utcnow)  # noqa: E402
from apps.api.security import hash_password  # noqa: E402


def signed(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256=" + hmac.new(b"test-webhook-secret", canonical, hashlib.sha256).hexdigest()


class BusinessAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert TEST_DB.parent.exists(), f"Test database parent missing: {TEST_DB.parent.resolve()}"
        TEST_DB.touch()
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            north = Workspace(slug="north", name="North Studio", is_demo=True)
            cedar = Workspace(slug="cedar", name="Cedar Studio", is_demo=True)
            db.add_all([north, cedar])
            db.flush()
            for workspace in (north, cedar):
                db.add(User(workspace_id=workspace.id, email=f"operator@{workspace.slug}.example.com", name="Operator", password_hash=hash_password("A-good-demo-password"), role="operator"))
                db.add(User(workspace_id=workspace.id, email=f"viewer@{workspace.slug}.example.com", name="Viewer", password_hash=hash_password("A-good-demo-password"), role="viewer"))
                db.add(OnboardingTemplateVersion(workspace_id=workspace.id, service_code="website", version=1, name="Website", description="Website delivery", checklist=[{"key": "logo", "title": "Upload logo", "required": True}, {"key": "kickoff", "title": "Share kickoff availability", "required": True}], folder_blueprint=["Brand", "Content"], board_blueprint=["To do", "Done"]))
            db.commit()
        cls.client = TestClient(app)
        cls.client.__enter__()
        login = cls.client.post("/api/auth/login", json={"email": "operator@north.example.com", "password": "A-good-demo-password"})
        assert login.status_code == 200, login.text
        cls.csrf = login.json()["csrf_token"]
        cls.internal = {"X-Internal-Key": "test-internal-key"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)
        engine.dispose()
        TEST_DB.unlink(missing_ok=True)

    def _event(self, suffix: str) -> tuple[dict, str]:
        payload = {
            "workspace_slug": "north", "event_id": f"event-{suffix}", "external_deal_id": f"deal-{suffix}",
            "client": {"name": "Maple Studio", "email": f"maple-{suffix}@example.com"},
            "services": ["website"], "approved_scope": "Build a website. Client provides a logo and kickoff availability.",
            "proposal_text": "Approved website proposal and deliverables.",
            "timeline": {"target_date": "2026-10-31"},
            "account_owner_email": "operator@north.example.com",
        }
        return payload, signed(payload)

    def _provision_service_folders(self, onboarding_id: str) -> list[dict]:
        created = []
        for _ in range(20):
            next_response = self.client.get(f"/api/onboardings/{onboarding_id}/provisioning/folders/next", headers=self.internal)
            self.assertEqual(next_response.status_code, 200, next_response.text)
            step = next_response.json()
            if step["done"]:
                return created
            self.assertFalse(step["blocked"], step)
            folder = step["folder"]
            claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={"system": "drive", "action": "create_child_folder", "folder_id": folder["id"]}, headers=self.internal)
            self.assertEqual(claim.status_code, 200, claim.text)
            self.assertTrue(claim.json()["execute"])
            payload = claim.json()["request_payload"]
            simulated = self.client.post("/sim/drive/folders", json={**payload, "idempotency_key": claim.json()["idempotency_key"]}, headers=self.internal)
            self.assertEqual(simulated.status_code, 200, simulated.text)
            completed = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/{claim.json()['operation_id']}/complete", json={"external_id": simulated.json()["external_id"], "url": simulated.json()["url"], "name": simulated.json()["name"]}, headers=self.internal)
            self.assertEqual(completed.status_code, 200, completed.text)
            created.append({**folder, **simulated.json(), "operation_id": claim.json()["operation_id"]})
        self.fail("Service folder provisioning did not converge")

    def test_service_folder_tree_timeout_reconciliation_and_resume(self) -> None:
        login = self.client.post("/api/auth/login", json={"email": "operator@north.example.com", "password": "A-good-demo-password"})
        self.assertEqual(login.status_code, 200, login.text)
        csrf = login.json()["csrf_token"]
        with SessionLocal() as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == "north"))
            db.add(OnboardingTemplateVersion(
                workspace_id=workspace.id, service_code="brand", version=1, name="Brand identity",
                description="Brand work", checklist=[], folder_blueprint=["Concepts", "Final assets"],
                board_blueprint=["To do", "Done"],
            ))
            db.commit()
        payload, signature = self._event(f"folders-{uuid4().hex}")
        payload["services"] = ["website", "brand"]
        signature = signed(payload)
        event = self.client.post("/api/events/won-deal", json=payload, headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        preview = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()["folder_structure"]
        self.assertEqual(preview["planned_count"], 6)
        self.assertEqual({folder["service_code"] for folder in preview["folders"]}, {"website", "brand"})

        plan = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json={
            "welcome_draft": "Hello Maple Studio", "summary": "Website and brand intake",
        }, headers=self.internal).json()
        with SessionLocal() as db:
            brand_template = db.scalar(select(OnboardingTemplateVersion).where(OnboardingTemplateVersion.service_code == "brand"))
            brand_template.folder_blueprint = ["Changed after proposal"]
            db.commit()
        frozen_preview = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()["folder_structure"]
        self.assertEqual(frozen_preview["planned_count"], 6)
        self.assertIn("Final assets", [folder["name"] for folder in frozen_preview["folders"]])
        approved = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={
            "plan_revision_id": plan["id"], "proposal_hash": plan["proposal_hash"], "decision": "approve",
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(approved.status_code, 200, approved.text)
        before_root = self.client.get(f"/api/onboardings/{onboarding_id}/provisioning/folders/next", headers=self.internal).json()
        self.assertTrue(before_root["blocked"])
        first_folder_id = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()["folder_structure"]["folders"][0]["id"]
        premature = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={
            "system": "drive", "action": "create_child_folder", "folder_id": first_folder_id,
        }, headers=self.internal)
        self.assertEqual(premature.status_code, 409)
        paused = self.client.post(f"/api/onboardings/{onboarding_id}/state", json={"action": "pause"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(paused.json()["status"], "paused")
        resumed = self.client.post(f"/api/onboardings/{onboarding_id}/state", json={"action": "resume"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(resumed.json()["status"], "provisioning")

        for system, action, endpoint in [("drive", "create_folder", "/sim/drive/folders"), ("trello", "create_board", "/sim/trello/boards")]:
            claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={
                "system": system, "action": action, "request_payload": {"name": "Maple Project"},
            }, headers=self.internal).json()
            simulated = self.client.post(endpoint, json={"name": "Maple Project", "idempotency_key": claim["idempotency_key"]}, headers=self.internal).json()
            completed = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/{claim['operation_id']}/complete", json={
                "external_id": simulated["external_id"], "url": simulated["url"], "name": simulated["name"],
            }, headers=self.internal)
            self.assertEqual(completed.status_code, 200, completed.text)
            if system == "drive":
                root_external_id = simulated["external_id"]
        self.assertEqual(self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()["onboarding"]["status"], "provisioning")

        next_folder = self.client.get(f"/api/onboardings/{onboarding_id}/provisioning/folders/next", headers=self.internal).json()["folder"]
        self.assertEqual(next_folder["parent_external_id"], root_external_id)
        claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={
            "system": "drive", "action": "create_child_folder", "folder_id": next_folder["id"],
        }, headers=self.internal).json()
        self.assertEqual(claim["request_payload"]["parent_id"], root_external_id)
        wrong_parent = self.client.post("/sim/drive/folders", json={
            "name": next_folder["name"], "parent_id": "wrong", "idempotency_key": claim["idempotency_key"],
        }, headers=self.internal)
        self.assertEqual(wrong_parent.status_code, 422)
        in_flight = self.client.post(f"/api/onboardings/{onboarding_id}/recover", json={}, headers=self.internal)
        self.assertEqual(in_flight.status_code, 200, in_flight.text)
        self.assertIn({"operation_id": claim["operation_id"], "result": "claim_still_in_flight"}, in_flight.json()["results"])
        self.assertFalse(in_flight.json()["resume_needed"])
        timeout = self.client.post("/sim/drive/folders", json={
            **claim["request_payload"], "idempotency_key": claim["idempotency_key"], "simulate_timeout": True,
        }, headers=self.internal)
        self.assertEqual(timeout.status_code, 504)
        blocked = self.client.get(f"/api/onboardings/{onboarding_id}/provisioning/folders/next", headers=self.internal).json()
        self.assertEqual(blocked["reason"], "unknown")
        recovered = self.client.post(f"/api/onboardings/{onboarding_id}/recover", json={}, headers=self.internal)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertFalse(recovered.json()["can_retry"])
        self.assertTrue(recovered.json()["resume_needed"])
        same_claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={
            "system": "drive", "action": "create_child_folder", "folder_id": next_folder["id"],
        }, headers=self.internal).json()
        self.assertFalse(same_claim["execute"])
        self.assertEqual(same_claim["status"], "succeeded")
        with SessionLocal() as db:
            self.assertEqual(len(db.scalars(select(SimResource).where(SimResource.idempotency_key == claim["idempotency_key"])).all()), 1)
        self.assertEqual(len(self._provision_service_folders(onboarding_id)), 5)
        detail = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()
        structure = detail["folder_structure"]
        self.assertTrue(structure["complete"])
        self.assertEqual(structure["complete_count"], 6)
        self.assertEqual(detail["onboarding"]["status"], "waiting_for_client")
        by_id = {folder["id"]: folder for folder in structure["folders"]}
        for folder in structure["folders"]:
            expected_parent = by_id[folder["parent_id"]]["external_id"] if folder["parent_id"] else root_external_id
            self.assertEqual(folder["parent_external_id"], expected_parent)
        self.client.post(f"/api/onboardings/{onboarding_id}/state", json={"action": "pause"}, headers={"X-CSRF-Token": csrf})
        resumed_complete = self.client.post(f"/api/onboardings/{onboarding_id}/state", json={"action": "resume"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(resumed_complete.json()["status"], "waiting_for_client")

    def test_operator_reconciled_board_timeout_resumes_task_sync_and_welcome(self) -> None:
        login = self.client.post("/api/auth/login", json={
            "email": "operator@north.example.com", "password": "A-good-demo-password",
        })
        self.assertEqual(login.status_code, 200, login.text)
        csrf = login.json()["csrf_token"]
        payload, signature = self._event(f"board-reconcile-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=payload, headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        plan = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json={
            "welcome_draft": "Hello Maple Studio", "summary": "Website intake",
        }, headers=self.internal).json()
        approval = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={
            "plan_revision_id": plan["id"], "proposal_hash": plan["proposal_hash"], "decision": "approve",
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(approval.status_code, 200, approval.text)

        root_claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={
            "system": "drive", "action": "create_folder", "request_payload": {"name": "Maple Project"},
        }, headers=self.internal).json()
        root = self.client.post("/sim/drive/folders", json={
            "onboarding_id": onboarding_id, "name": "Maple Project", "idempotency_key": root_claim["idempotency_key"],
        }, headers=self.internal).json()
        completed_root = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/{root_claim['operation_id']}/complete", json={
            "external_id": root["external_id"], "url": root["url"], "name": root["name"],
        }, headers=self.internal)
        self.assertEqual(completed_root.status_code, 200, completed_root.text)
        self.assertEqual(len(self._provision_service_folders(onboarding_id)), 3)

        board_claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={
            "system": "trello", "action": "create_board", "request_payload": {"name": "Maple Board"},
        }, headers=self.internal).json()
        timeout = self.client.post("/sim/trello/boards", json={
            "onboarding_id": onboarding_id, "name": "Maple Board", "idempotency_key": board_claim["idempotency_key"],
            "simulate_timeout": True,
        }, headers=self.internal)
        self.assertEqual(timeout.status_code, 504)
        with SessionLocal() as db:
            board_resource = db.scalar(select(SimResource).where(SimResource.system == "trello", SimResource.idempotency_key == board_claim["idempotency_key"]))
            self.assertIsNotNone(board_resource)
            board_id = board_resource.id

        reconciled = self.client.post(f"/api/onboardings/{onboarding_id}/recover", json={
            "operation_id": board_claim["operation_id"], "decision": "reconcile", "external_id": board_id,
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(reconciled.status_code, 200, reconciled.text)
        self.assertEqual(reconciled.json()["onboarding_status"], "waiting_for_client")
        self.assertIsNotNone(reconciled.json()["dispatch_status"])
        recovery_run = self.client.post(f"/api/onboardings/{onboarding_id}/recover", json={}, headers=self.internal)
        self.assertEqual(recovery_run.status_code, 200, recovery_run.text)
        self.assertFalse(recovery_run.json()["can_retry"])
        self.assertTrue(recovery_run.json()["resume_needed"])
        self.assertIsNone(recovery_run.json()["substate"])
        self.assertEqual(len(self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending", headers=self.internal).json()), 2)
        detail = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()
        board = next(item for item in detail["resources"] if item["system"] == "trello")
        self.assertEqual(board["todo_list_id"], board_resource.payload["todo_list_id"])
        self.assertEqual(detail["welcome"], [])

    def test_plan_coalesces_legacy_template_keys_and_fills_missing_summary(self) -> None:
        payload, signature = self._event("template-contract")
        event = self.client.post("/api/events/won-deal", json=payload, headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        draft = {
            "checklist": [
                {"key": "website_logo", "title": "Upload logo", "source": "template", "service_code": "website"},
                {"key": "logo", "title": "Upload logo", "source": "template", "service_code": "website"},
                {"key": "website_old_task", "title": "Old task", "source": "template", "service_code": "website"},
            ],
            "deliverables": ["Website"], "welcome_draft": "Hello Maple Studio, welcome to your project.",
        }
        stored = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json=draft, headers=self.internal)
        self.assertEqual(stored.status_code, 200, stored.text)
        detail = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal)
        self.assertEqual(detail.status_code, 200, detail.text)
        plan = detail.json()["plan"]
        self.assertEqual([item["key"] for item in plan["checklist"]], ["logo", "kickoff"])
        self.assertIn("Maple Studio", plan["summary"])

    def test_end_to_end_with_ambiguous_timeout_and_client_isolation(self) -> None:
        payload, signature = self._event("main")
        event = self.client.post("/api/events/won-deal", json=payload, headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        duplicate = self.client.post("/api/events/won-deal", json=payload, headers={"X-ClientLaunch-Signature": signature})
        self.assertTrue(duplicate.json()["duplicate"])
        changed = {**payload, "approved_scope": payload["approved_scope"] + " Extra work."}
        conflict = self.client.post("/api/events/won-deal", json=changed, headers={"X-ClientLaunch-Signature": signed(changed)})
        self.assertEqual(conflict.status_code, 409)

        plan_body = {"checklist": [{"key": "logo", "title": "Upload logo", "source": "template", "service_code": "website", "required": True}, {"key": "kickoff", "title": "Share kickoff availability", "source": "template", "service_code": "website", "required": True}], "deliverables": ["Website"], "risks": [], "missing_inputs": ["Logo"], "welcome_draft": "Hello Maple Studio, welcome to your website project.", "summary": "Website intake", "suggestions": []}
        plan = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json=plan_body, headers=self.internal)
        self.assertEqual(plan.status_code, 200, plan.text)
        plan_id = plan.json()["id"]
        stale = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={"plan_revision_id": plan_id, "proposal_hash": "wrong", "decision": "approve"}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(stale.status_code, 409)
        approval = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={"plan_revision_id": plan_id, "proposal_hash": plan.json()["proposal_hash"], "decision": "approve"}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(approval.status_code, 200, approval.text)
        replay = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={"plan_revision_id": plan_id, "proposal_hash": plan.json()["proposal_hash"], "decision": "approve"}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(replay.status_code, 409)

        drive_claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={"system": "drive", "action": "create_folder", "request_payload": {"name": "Maple Project"}}, headers=self.internal)
        self.assertTrue(drive_claim.json()["execute"])
        key = drive_claim.json()["idempotency_key"]
        timeout = self.client.post("/sim/drive/folders", json={"name": "Maple Project", "idempotency_key": key, "simulate_timeout": True}, headers=self.internal)
        self.assertEqual(timeout.status_code, 504)
        self.assertEqual(self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()["operations"][0]["status"], "unknown")
        unsafe_retry = self.client.post(f"/api/onboardings/{onboarding_id}/recover", json={"operation_id": drive_claim.json()["operation_id"], "decision": "retry"}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(unsafe_retry.status_code, 409)
        reconcile = self.client.post(f"/api/onboardings/{onboarding_id}/recover", json={}, headers=self.internal)
        self.assertEqual(reconcile.status_code, 200, reconcile.text)
        self.assertFalse(reconcile.json()["can_retry"])
        known = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={"system": "drive", "action": "create_folder", "request_payload": {"name": "Maple Project"}}, headers=self.internal)
        self.assertFalse(known.json()["execute"])
        self.assertEqual(len(self._provision_service_folders(onboarding_id)), 3)
        with SessionLocal() as db:
            self.assertEqual(len(db.scalars(select(SimResource).where(SimResource.system == "drive", SimResource.idempotency_key == key)).all()), 1)

        board_claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={"system": "trello", "action": "create_board", "request_payload": {"name": "Maple Board"}}, headers=self.internal)
        self.assertEqual(board_claim.status_code, 200, board_claim.text)
        armed = self.client.post("/sim/faults/next", json={"onboarding_id": onboarding_id, "system": "trello", "kind": "failure"}, headers=self.internal)
        self.assertEqual(armed.status_code, 200, armed.text)
        failed_board = self.client.post("/sim/trello/boards", json={"onboarding_id": onboarding_id, "name": "Maple Board", "idempotency_key": board_claim.json()["idempotency_key"]}, headers=self.internal)
        self.assertEqual(failed_board.status_code, 503)
        retry = self.client.post(f"/api/onboardings/{onboarding_id}/recover", json={}, headers=self.internal)
        self.assertTrue(retry.json()["can_retry"])
        retry_claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={"system": "trello", "action": "create_board", "request_payload": {"name": "Maple Board"}}, headers=self.internal)
        self.assertTrue(retry_claim.json()["execute"])
        self.assertEqual(retry_claim.json()["idempotency_key"], board_claim.json()["idempotency_key"])
        board = self.client.post("/sim/trello/boards", json={"onboarding_id": onboarding_id, "name": "Maple Board", "idempotency_key": board_claim.json()["idempotency_key"]}, headers=self.internal)
        self.assertEqual(board.status_code, 200, board.text)
        completed = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/{board_claim.json()['operation_id']}/complete", json={"external_id": board.json()["external_id"], "url": board.json()["url"], "name": board.json()["name"]}, headers=self.internal)
        self.assertEqual(completed.status_code, 200, completed.text)
        with SessionLocal() as db:
            self.assertEqual(len(db.scalars(select(SimResource).where(SimResource.system == "trello", SimResource.kind == "board", SimResource.idempotency_key == board_claim.json()["idempotency_key"])).all()), 1)
        pending_cards = self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending", headers=self.internal).json()
        self.assertEqual(len(pending_cards), 2)
        for operation in pending_cards:
            claim = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{operation['operation_id']}/claim", json={
                "expected_status": operation["status"], "expected_idempotency_key": operation["idempotency_key"],
            }, headers=self.internal)
            self.assertTrue(claim.json()["execute"])
            card = self.client.post("/sim/trello/cards", json={"board_id": operation["external_board_id"], "name": operation["title"], "description": operation["description"], "due_date": operation["due_date"], "status": operation["status"], "idempotency_key": operation["idempotency_key"]}, headers=self.internal)
            self.assertEqual(card.status_code, 200, card.text)
            ack = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{operation['operation_id']}/complete", json={"external_id": card.json()["id"], "status": operation["status"]}, headers=self.internal)
            self.assertEqual(ack.status_code, 200, ack.text)
        self.assertEqual(self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending", headers=self.internal).json(), [])
        welcome = self.client.post(f"/api/onboardings/{onboarding_id}/welcome", json={"recipient": payload["client"]["email"], "subject": "Welcome", "body": plan_body["welcome_draft"]}, headers=self.internal)
        self.assertEqual(welcome.status_code, 200, welcome.text)
        self.assertFalse(welcome.json()["dispatch_required"])
        self.assertIn("token=", welcome.json()["body"])

        viewer_login = self.client.post("/api/auth/login", json={"email": "viewer@north.example.com", "password": "A-good-demo-password"})
        self.assertEqual(viewer_login.status_code, 200)
        viewer_detail = self.client.get(f"/api/onboardings/{onboarding_id}")
        self.assertEqual(viewer_detail.status_code, 200)
        self.assertNotIn("portal_link", viewer_detail.json()["onboarding"])
        self.assertTrue(all(message["body"] is None for message in viewer_detail.json()["welcome"]))
        self.assertNotIn("token=", viewer_detail.text)
        operator_login = self.client.post("/api/auth/login", json={"email": "operator@north.example.com", "password": "A-good-demo-password"})
        self.assertEqual(operator_login.status_code, 200)
        operator_csrf = operator_login.json()["csrf_token"]

        detail = self.client.get(f"/api/onboardings/{onboarding_id}").json()
        portal_token = detail["onboarding"]["portal_link"].split("token=")[1]
        exchanged = self.client.post("/api/client/exchange", json={"portal_token": portal_token})
        self.assertEqual(exchanged.status_code, 200, exchanged.text)
        client_headers = {"Authorization": f"Bearer {exchanged.json()['token']}"}
        client_view = self.client.get("/api/client/onboarding", headers=client_headers)
        self.assertEqual(client_view.status_code, 200)
        self.assertNotIn("risks", client_view.json())
        ids = [item["id"] for item in client_view.json()["checklist"]]
        invalid_upload = self.client.post("/api/client/assets", files={"file": ("bad.exe", b"MZevil", "application/octet-stream")}, data={"checklist_item_id": ids[0]}, headers=client_headers)
        self.assertEqual(invalid_upload.status_code, 415)
        submission = self.client.post("/api/client/submissions", json={"answers": [{"checklist_item_id": ids[0], "value": "Logo is attached"}, {"checklist_item_id": ids[1], "value": "Tuesday at 10"}]}, headers=client_headers)
        self.assertEqual(submission.status_code, 200, submission.text)
        self.assertEqual(submission.json()["onboarding_status"], "waiting_for_client")
        processed = self.client.post(f"/api/client-submissions/{submission.json()['id']}/process", json={}, headers=self.internal)
        self.assertEqual(processed.status_code, 200, processed.text)
        self.assertEqual(len(processed.json()["pending_operations"]), 2)
        duplicate_process = self.client.post(f"/api/client-submissions/{submission.json()['id']}/process", json={}, headers=self.internal)
        self.assertTrue(duplicate_process.json()["duplicate"])
        for operation in processed.json()["pending_operations"]:
            self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{operation['operation_id']}/claim", json={
                "expected_status": operation["status"], "expected_idempotency_key": operation["idempotency_key"],
            }, headers=self.internal)
            card = self.client.patch(f"/sim/trello/cards/{operation['external_card_id']}", json={"status": operation["status"], "idempotency_key": operation["idempotency_key"]}, headers=self.internal)
            self.assertEqual(card.status_code, 200, card.text)
            ack = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{operation['operation_id']}/complete", json={"external_id": card.json()["id"], "status": operation["status"]}, headers=self.internal)
            self.assertEqual(ack.status_code, 200, ack.text)
        self.assertEqual(self.client.get(f"/api/onboardings/{onboarding_id}").json()["onboarding"]["status"], "ready")
        handoff = self.client.post(f"/api/onboardings/{onboarding_id}/handoff", json={"summary": "Logo and kickoff availability were provided by the client."}, headers={"X-CSRF-Token": operator_csrf})
        self.assertEqual(handoff.status_code, 200, handoff.text)
        self.assertEqual(handoff.json()["status"], "handed_off")
        recorded = self.client.get(f"/api/onboardings/{onboarding_id}")
        self.assertEqual(recorded.status_code, 200, recorded.text)
        self.assertEqual(recorded.json()["handoff"]["summary"], "Logo and kickoff availability were provided by the client.")
        self.assertEqual(recorded.json()["handoff"]["evidence"], handoff.json()["evidence"])

        cedar_login = self.client.post("/api/auth/login", json={"email": "operator@cedar.example.com", "password": "A-good-demo-password"})
        self.assertEqual(cedar_login.status_code, 200)
        self.assertEqual(self.client.get(f"/api/onboardings/{onboarding_id}").status_code, 404)

    def test_reminders_pause_and_expired_portal(self) -> None:
        payload, signature = self._event("reminder")
        result = self.client.post("/api/events/won-deal", json=payload, headers={"X-ClientLaunch-Signature": signature})
        onboarding_id = result.json()["onboarding_id"]
        plan = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json={"checklist": [], "deliverables": [], "risks": [], "missing_inputs": [], "welcome_draft": "Hello Maple Studio", "summary": "Website intake", "suggestions": []}, headers=self.internal).json()
        self.client.post("/api/auth/login", json={"email": "operator@north.example.com", "password": "A-good-demo-password"})
        csrf = self.client.get("/api/auth/me").json()["csrf_token"]
        self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={"plan_revision_id": plan["id"], "proposal_hash": plan["proposal_hash"], "decision": "approve"}, headers={"X-CSRF-Token": csrf})
        for system, action, endpoint in [("drive", "create_folder", "/sim/drive/folders"), ("trello", "create_board", "/sim/trello/boards")]:
            claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={"system": system, "action": action, "request_payload": {"name": "Project"}}, headers=self.internal).json()
            simulated = self.client.post(endpoint, json={"name": "Project", "idempotency_key": claim["idempotency_key"]}, headers=self.internal).json()
            self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/{claim['operation_id']}/complete", json={"external_id": simulated["external_id"], "url": simulated["url"], "name": simulated["name"]}, headers=self.internal)
        self.assertEqual(len(self._provision_service_folders(onboarding_id)), 3)
        reminders = self.client.post("/api/reminders/evaluate", json={"onboarding_id": onboarding_id}, headers=self.internal)
        self.assertEqual(reminders.status_code, 200, reminders.text)
        self.assertEqual(reminders.json()["drafted_count"], 2)
        reminder_id = reminders.json()["items"][0]["id"]
        approved = self.client.post(f"/api/reminders/{reminder_id}/approval", json={"decision": "approve"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(approved.status_code, 200)
        paused = self.client.post(f"/api/onboardings/{onboarding_id}/state", json={"action": "pause"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(paused.json()["status"], "paused")
        self.assertEqual(self.client.get("/api/reminders/approved-pending", headers=self.internal).json(), [])
        blocked = self.client.post(f"/api/reminders/{reminder_id}/dispatch", json={}, headers=self.internal)
        self.assertEqual(blocked.status_code, 409)
        with SessionLocal() as db:
            invite = db.scalar(select(PortalInvite).where(PortalInvite.onboarding_id == onboarding_id))
            invite.expires_at = utcnow() - timedelta(minutes=1)
            db.commit()
        token = self.client.get(f"/api/onboardings/{onboarding_id}").json()["onboarding"].get("portal_link")
        self.assertIsNone(token)

    def test_unattributed_n8n_error_is_operationally_visible_without_tenant_leak(self) -> None:
        execution_id = f"execution-{uuid4().hex}"
        payload = {"workflow_id": "CL08DealIntake01", "execution_id": execution_id,
                   "node": "Draft AI plan", "message": "Synthetic n8n execution failed"}
        recorded = self.client.post("/api/workflow-errors", json=payload, headers=self.internal)
        self.assertEqual(recorded.status_code, 200, recorded.text)
        duplicate = self.client.post("/api/workflow-errors", json=payload, headers=self.internal)
        self.assertTrue(duplicate.json()["duplicate"])

        self.assertEqual(self.client.get("/api/workflow-errors/unattributed").status_code, 401)
        queue = self.client.get("/api/workflow-errors/unattributed", headers=self.internal)
        self.assertEqual(queue.status_code, 200, queue.text)
        self.assertEqual([item["id"] for item in queue.json()["items"] if item["execution_id"] == execution_id],
                         [recorded.json()["id"]])

        north = self.client.post("/api/auth/login", json={"email": "operator@north.example.com", "password": "A-good-demo-password"})
        self.assertEqual(north.status_code, 200, north.text)
        self.assertNotIn(recorded.json()["id"], [item["id"] for item in self.client.get("/api/exceptions").json()["items"]])

        event_payload, signature = self._event(f"exception-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=event_payload,
                                 headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        scoped = self.client.post("/api/workflow-errors", json={**payload, "execution_id": f"scoped-{execution_id}",
                                                            "onboarding_id": event.json()["onboarding_id"]},
                                  headers=self.internal)
        self.assertEqual(scoped.status_code, 200, scoped.text)
        self.assertIn(scoped.json()["id"], [item["id"] for item in self.client.get("/api/exceptions").json()["items"]])
        self.assertNotIn(scoped.json()["id"], [item["id"] for item in self.client.get("/api/workflow-errors/unattributed", headers=self.internal).json()["items"]])

        cedar = self.client.post("/api/auth/login", json={"email": "operator@cedar.example.com", "password": "A-good-demo-password"})
        self.assertEqual(cedar.status_code, 200, cedar.text)
        cedar_ids = [item["id"] for item in self.client.get("/api/exceptions").json()["items"]]
        self.assertNotIn(recorded.json()["id"], cedar_ids)
        self.assertNotIn(scoped.json()["id"], cedar_ids)

    def test_dispatch_sweep_moves_failed_attempt_behind_new_work(self) -> None:
        payload, signature = self._event(f"dispatch-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=payload,
                                 headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        with SessionLocal() as db:
            for row in db.scalars(select(WorkflowDispatch).where(WorkflowDispatch.status == "pending")):
                row.attempt_count = 100
            rows = [WorkflowDispatch(onboarding_id=onboarding_id, kind="submission",
                                     dedupe_key=f"sweep-{uuid4().hex}", payload={"submission_id": str(index)})
                    for index in range(21)]
            db.add_all(rows)
            db.commit()
            new_ids = {row.id for row in rows}
        self.assertEqual(self.client.get("/api/workflow-dispatches/pending").status_code, 401)
        first = self.client.get("/api/workflow-dispatches/pending", headers=self.internal).json()["items"]
        self.assertEqual(len(first), 20)
        self.assertTrue({row["id"] for row in first}.issubset(new_ids))
        attempted_id = first[0]["id"]
        attempted = self.client.post(f"/api/workflow-dispatches/{attempted_id}/attempt", headers=self.internal)
        self.assertEqual(attempted.status_code, 200, attempted.text)
        self.assertTrue(attempted.json()["execute"])
        self.assertEqual(attempted.json()["attempt_count"], 1)
        second_ids = {row["id"] for row in self.client.get("/api/workflow-dispatches/pending", headers=self.internal).json()["items"]}
        self.assertEqual(len(second_ids), 20)
        self.assertNotIn(attempted_id, second_ids)
        self.assertTrue(second_ids.issubset(new_ids))
        self.assertEqual(self.client.post(f"/api/workflow-dispatches/{attempted_id}/ack", headers=self.internal).status_code, 200)
        duplicate = self.client.post(f"/api/workflow-dispatches/{attempted_id}/attempt", headers=self.internal)
        self.assertFalse(duplicate.json()["execute"])

    def test_accepted_webhook_with_no_operations_returns_to_sweep(self) -> None:
        payload, signature = self._event(f"stale-accepted-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=payload,
                                 headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        plan = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json={
            "welcome_draft": "Hello Maple Studio", "summary": "Website intake",
        }, headers=self.internal).json()
        login = self.client.post("/api/auth/login", json={
            "email": "operator@north.example.com", "password": "A-good-demo-password",
        })
        self.__class__.csrf = login.json()["csrf_token"]
        approved = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={
            "plan_revision_id": plan["id"], "proposal_hash": plan["proposal_hash"], "decision": "approve",
        }, headers={"X-CSRF-Token": login.json()["csrf_token"]})
        self.assertEqual(approved.status_code, 200, approved.text)
        with SessionLocal() as db:
            dispatch = db.scalar(select(WorkflowDispatch).where(
                WorkflowDispatch.onboarding_id == onboarding_id, WorkflowDispatch.kind == "approval",
            ))
            dispatch.status = "delivered"
            dispatch.delivered_at = utcnow() - timedelta(minutes=6)
            db.commit()
            dispatch_id = dispatch.id
        pending = self.client.get("/api/workflow-dispatches/pending", headers=self.internal)
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertIn(dispatch_id, {row["id"] for row in pending.json()["items"]})
        with SessionLocal() as db:
            self.assertEqual(db.get(WorkflowDispatch, dispatch_id).status, "pending")

        # If connected SMTP has prepared a welcome, an uncertain send must
        # never be replayed just because the webhook's business run is stale.
        with SessionLocal() as db:
            dispatch = db.get(WorkflowDispatch, dispatch_id)
            dispatch.status = "delivered"
            dispatch.delivered_at = utcnow() - timedelta(minutes=6)
            db.add(OutboxEmail(onboarding_id=onboarding_id, kind="welcome", dedupe_key=plan["id"],
                               recipient=payload["client"]["email"], subject="Welcome", body="Hello",
                               status="queued"))
            db.commit()
        pending = self.client.get("/api/workflow-dispatches/pending", headers=self.internal).json()["items"]
        self.assertNotIn(dispatch_id, {row["id"] for row in pending})

    def test_expired_demo_card_claim_reconciles_existing_or_absent(self) -> None:
        payload, signature = self._event(f"card-reconcile-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=payload,
                                 headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        with SessionLocal() as db:
            onboarding = db.get(Onboarding, onboarding_id)
            items = [ChecklistItem(onboarding_id=onboarding_id, item_key=f"test:{index}",
                                   title=f"Task {index}", required=True, status="open",
                                   source="template", client_visible=True)
                     for index in range(2)]
            db.add_all(items)
            board = SimResource(system="trello", kind="board", idempotency_key=f"board:{onboarding_id}",
                                payload={"name": "Test board", "url": "https://trello.example.test/board/test"})
            db.add(board)
            db.flush()
            db.add(ExternalResource(onboarding_id=onboarding_id, system="trello", kind="board",
                                    external_id=board.id, preview={"tasks": []}))
            cards = [TaskCard(onboarding_id=onboarding_id, checklist_item_id=item.id,
                              board_external_id=board.id, desired_status="open", sync_state="claimed",
                              idempotency_key=f"card:{item.id}",
                              lease_until=utcnow() - timedelta(minutes=1), attempt_count=1)
                     for item in items]
            db.add_all(cards)
            db.flush()
            db.add(SimResource(system="trello", kind="card", idempotency_key=cards[0].idempotency_key,
                               payload={"board_id": board.id, "checklist_item_id": items[0].id,
                                        "name": items[0].title, "status": "open",
                                        "url": "https://trello.example.test/card/test"}))
            onboarding.status = "waiting_for_client"
            db.commit()
            existing_id, absent_id = cards[0].id, cards[1].id
        reconciled = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/reconcile",
                                      json={}, headers=self.internal)
        self.assertEqual(reconciled.status_code, 200, reconciled.text)
        self.assertEqual({r["result"] for r in reconciled.json()["results"]},
                         {"existing_card_found", "simulator_confirmed_absent"})
        with SessionLocal() as db:
            self.assertEqual(db.get(TaskCard, existing_id).sync_state, "synced")
            self.assertEqual(db.get(TaskCard, absent_id).sync_state, "retryable")
            preview = db.scalar(select(ExternalResource).where(
                ExternalResource.onboarding_id == onboarding_id,
                ExternalResource.system == "trello",
            )).preview
            self.assertEqual(len(preview["tasks"]), 1)
        pending = next(item for item in self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending",
                                                     headers=self.internal).json() if item["operation_id"] == absent_id)
        retry = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{absent_id}/claim",
                                 json={"expected_status": pending["status"], "expected_idempotency_key": pending["idempotency_key"]},
                                 headers=self.internal)
        self.assertTrue(retry.json()["execute"])
        again = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/reconcile",
                                 json={}, headers=self.internal)
        self.assertEqual(again.json()["results"], [])

    def test_connected_unknown_card_requires_explicit_operator_outcome(self) -> None:
        payload, signature = self._event(f"connected-card-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=payload,
                                 headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        with SessionLocal() as db:
            item = ChecklistItem(onboarding_id=onboarding_id, item_key="test:connected",
                                 title="Connected card", required=True, status="completed",
                                 source="template", client_visible=True)
            db.add(item)
            db.flush()
            db.add(ExternalResource(onboarding_id=onboarding_id, system="trello", kind="board",
                                    external_id="connected-board", preview={"tasks": []}))
            card = TaskCard(onboarding_id=onboarding_id, checklist_item_id=item.id,
                            board_external_id="connected-board", desired_status="completed",
                            sync_state="unknown", idempotency_key=f"card:{item.id}", attempt_count=1)
            db.add(card)
            db.commit()
            card_id = card.id
        prior_mode = os.environ["CONNECTOR_MODE"]
        os.environ["CONNECTOR_MODE"] = "connected"
        try:
            internal = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/reconcile",
                                        json={}, headers=self.internal)
            self.assertEqual(internal.status_code, 200, internal.text)
            self.assertEqual(internal.json()["results"], [])
            login = self.client.post("/api/auth/login", json={
                "email": "operator@north.example.com", "password": "A-good-demo-password",
            })
            self.assertEqual(login.status_code, 200, login.text)
            self.__class__.csrf = login.json()["csrf_token"]
            missing_status = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/reconcile",
                                              json={"operation_id": card_id, "external_id": "connected-card"},
                                              headers={"X-CSRF-Token": login.json()["csrf_token"]})
            self.assertEqual(missing_status.status_code, 422)
            confirmed = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/reconcile",
                                         json={"operation_id": card_id, "external_id": "connected-card",
                                               "status": "open"},
                                         headers={"X-CSRF-Token": login.json()["csrf_token"]})
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            self.assertEqual(confirmed.json()["sync_state"], "pending")
            pending = self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending",
                                      headers=self.internal).json()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["action"], "update")
        finally:
            os.environ["CONNECTOR_MODE"] = prior_mode

    def test_client_change_during_card_create_preserves_claim_and_schedules_one_update(self) -> None:
        payload, signature = self._event(f"card-race-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=payload,
                                 headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        plan = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json={
            "welcome_draft": "Hello Maple Studio", "summary": "Website intake",
        }, headers=self.internal).json()
        login = self.client.post("/api/auth/login", json={
            "email": "operator@north.example.com", "password": "A-good-demo-password",
        })
        self.assertEqual(login.status_code, 200, login.text)
        approval = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={
            "plan_revision_id": plan["id"], "proposal_hash": plan["proposal_hash"], "decision": "approve",
        }, headers={"X-CSRF-Token": login.json()["csrf_token"]})
        self.assertEqual(approval.status_code, 200, approval.text)
        with SessionLocal() as db:
            onboarding = db.get(Onboarding, onboarding_id)
            item = db.scalar(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding_id))
            board = SimResource(system="trello", kind="board", idempotency_key=f"manual-board:{onboarding_id}",
                                payload={"name": "Test board", "url": "https://trello.example.test/board/test",
                                         "todo_list_id": "test-todo-list"})
            db.add(board)
            db.flush()
            db.add(ExternalResource(onboarding_id=onboarding_id, system="trello", kind="board",
                                    external_id=board.id, preview={"todo_list_id": "test-todo-list", "tasks": []}))
            card = TaskCard(onboarding_id=onboarding_id, checklist_item_id=item.id,
                            board_external_id=board.id, desired_status="open", sync_state="pending",
                            idempotency_key=f"clientlaunch:{onboarding_id}:trello:card:{item.id}")
            db.add(card)
            onboarding.status = "waiting_for_client"
            db.commit()
            item_id, board_id, card_id = item.id, board.id, card.id

        pending = next(row for row in self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending",
                                                   headers=self.internal).json() if row["operation_id"] == card_id)
        old_claim = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{card_id}/claim", json={
            "expected_status": pending["status"], "expected_idempotency_key": pending["idempotency_key"],
        }, headers=self.internal)
        self.assertTrue(old_claim.json()["execute"])
        portal_link = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()["onboarding"]["portal_link"]
        exchanged = self.client.post("/api/client/exchange", json={"portal_token": portal_link.split("token=")[1]})
        self.assertEqual(exchanged.status_code, 200, exchanged.text)
        client_headers = {"Authorization": f"Bearer {exchanged.json()['token']}"}
        submitted = self.client.post("/api/client/submissions", json={"answers": [{
            "checklist_item_id": item_id, "value": "Approved logo file will follow",
        }]}, headers=client_headers)
        self.assertEqual(submitted.status_code, 200, submitted.text)
        processed = self.client.post(f"/api/client-submissions/{submitted.json()['id']}/process",
                                     json={}, headers=self.internal)
        self.assertEqual(processed.status_code, 200, processed.text)
        self.assertFalse(any(row["operation_id"] == card_id for row in processed.json()["pending_operations"]))
        with SessionLocal() as db:
            card = db.get(TaskCard, card_id)
            self.assertEqual((card.sync_state, card.desired_status, card.idempotency_key),
                             ("claimed", "completed", pending["idempotency_key"]))

        created = self.client.post("/sim/trello/cards", json={
            "board_id": board_id, "name": pending["title"], "description": pending["description"],
            "due_date": pending["due_date"], "status": pending["status"],
            "idempotency_key": pending["idempotency_key"],
        }, headers=self.internal)
        self.assertEqual(created.status_code, 200, created.text)
        old_ack = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{card_id}/complete", json={
            "external_id": created.json()["id"], "status": pending["status"],
        }, headers=self.internal)
        self.assertEqual(old_ack.status_code, 200, old_ack.text)
        self.assertEqual(old_ack.json()["status"], "pending")
        stale_claim = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{card_id}/claim", json={
            "expected_status": pending["status"], "expected_idempotency_key": pending["idempotency_key"],
        }, headers=self.internal)
        self.assertEqual(stale_claim.json()["status"], "stale")
        self.assertFalse(stale_claim.json()["execute"])
        updated = next(row for row in self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending",
                                                   headers=self.internal).json() if row["operation_id"] == card_id)
        self.assertEqual((updated["action"], updated["status"]), ("update", "completed"))
        fresh_claim = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{card_id}/claim", json={
            "expected_status": updated["status"], "expected_idempotency_key": updated["idempotency_key"],
        }, headers=self.internal)
        self.assertTrue(fresh_claim.json()["execute"])
        changed = self.client.patch(f"/sim/trello/cards/{created.json()['id']}", json={
            "status": updated["status"], "idempotency_key": updated["idempotency_key"],
        }, headers=self.internal)
        self.assertEqual(changed.status_code, 200, changed.text)
        final_ack = self.client.post(f"/api/onboardings/{onboarding_id}/task-sync/{card_id}/complete", json={
            "external_id": created.json()["id"], "status": updated["status"],
        }, headers=self.internal)
        self.assertEqual(final_ack.json()["status"], "synced")
        with SessionLocal() as db:
            cards = db.scalars(select(SimResource).where(SimResource.system == "trello", SimResource.kind == "card")).all()
            self.assertEqual(sum(row.payload.get("board_id") == board_id for row in cards), 1)

    def test_connected_board_reconciliation_requires_todo_list_id(self) -> None:
        payload, signature = self._event(f"board-list-{uuid4().hex}")
        event = self.client.post("/api/events/won-deal", json=payload,
                                 headers={"X-ClientLaunch-Signature": signature})
        self.assertEqual(event.status_code, 200, event.text)
        onboarding_id = event.json()["onboarding_id"]
        plan = self.client.post(f"/api/onboardings/{onboarding_id}/plan", json={
            "welcome_draft": "Hello Maple Studio", "summary": "Website intake",
        }, headers=self.internal).json()
        login = self.client.post("/api/auth/login", json={
            "email": "operator@north.example.com", "password": "A-good-demo-password",
        })
        self.assertEqual(login.status_code, 200, login.text)
        csrf = login.json()["csrf_token"]
        approval = self.client.post(f"/api/onboardings/{onboarding_id}/approval", json={
            "plan_revision_id": plan["id"], "proposal_hash": plan["proposal_hash"], "decision": "approve",
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(approval.status_code, 200, approval.text)
        board_claim = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/claim", json={
            "system": "trello", "action": "create_board", "request_payload": {"name": "Maple Board"},
        }, headers=self.internal).json()
        uncertain = self.client.post(f"/api/onboardings/{onboarding_id}/provisioning/{board_claim['operation_id']}/complete",
                                     json={"outcome": "unknown", "error": "Provider response lost"}, headers=self.internal)
        self.assertEqual(uncertain.status_code, 200, uncertain.text)
        prior_mode = os.environ["CONNECTOR_MODE"]
        os.environ["CONNECTOR_MODE"] = "connected"
        try:
            url = f"/api/onboardings/{onboarding_id}/recover"
            without_list = self.client.post(url, json={
                "operation_id": board_claim["operation_id"], "decision": "reconcile",
                "external_id": "connected-board",
            }, headers={"X-CSRF-Token": csrf})
            self.assertEqual(without_list.status_code, 422, without_list.text)
            blank_list = self.client.post(url, json={
                "operation_id": board_claim["operation_id"], "decision": "reconcile",
                "external_id": "connected-board", "todo_list_id": "   ",
            }, headers={"X-CSRF-Token": csrf})
            self.assertEqual(blank_list.status_code, 422, blank_list.text)
            confirmed = self.client.post(url, json={
                "operation_id": board_claim["operation_id"], "decision": "reconcile",
                "external_id": "connected-board", "todo_list_id": "verified-todo-list",
                "url": "https://trello.com/b/example", "name": "Maple Board",
            }, headers={"X-CSRF-Token": csrf})
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            detail = self.client.get(f"/api/onboardings/{onboarding_id}", headers=self.internal).json()
            board = next(row for row in detail["resources"] if row["system"] == "trello")
            self.assertEqual(board["todo_list_id"], "verified-todo-list")
            pending = self.client.get(f"/api/onboardings/{onboarding_id}/task-sync/pending",
                                      headers=self.internal).json()
            self.assertEqual(len(pending), 2)
            self.assertEqual({row["todo_list_id"] for row in pending}, {"verified-todo-list"})
        finally:
            os.environ["CONNECTOR_MODE"] = prior_mode


if __name__ == "__main__":
    unittest.main()
