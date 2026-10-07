"""Isolated SQLite checks: python -m unittest discover -s tests/customization."""
import os
import unittest
from pathlib import Path
from uuid import uuid4

TEST_DB = Path('.runtime') / f'customization-{uuid4().hex}.db'
os.environ.update(DATABASE_URL=f'sqlite:///{TEST_DB.as_posix()}', APP_MODE='DEMO', CONNECTOR_MODE='demo',
                  INTERNAL_KEY='settings-test-internal', WEBHOOK_SECRET='settings-test-webhook', AUTO_CREATE_SCHEMA='false')

from fastapi.testclient import TestClient
from sqlalchemy import select
from apps.api.database import Base, SessionLocal, engine
from apps.api.main import app
from apps.api.models import Workspace, User, OnboardingTemplateVersion, WorkspaceBrand, Client, WonDeal, Onboarding, ChecklistItem, IntakeSubmission
from apps.api.security import hash_password
from apps.api.services import client_detail


class SettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_DB.parent.mkdir(exist_ok=True)
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            for slug in ('first', 'second'):
                workspace = Workspace(slug=slug, name=slug.title(), is_demo=True)
                db.add(workspace)
                db.flush()
                for role in ('operator', 'viewer'):
                    db.add(User(workspace_id=workspace.id, email=f'{role}@{slug}.example.com', name=role,
                                password_hash=hash_password('local-test-password'), role=role))
                db.add(OnboardingTemplateVersion(workspace_id=workspace.id, service_code='website', version=1,
                       name='Website', description='Original', checklist=[{'key': 'logo', 'title': 'Upload logo', 'required': True}],
                       folder_blueprint=['Brand', 'Copy'], board_blueprint=['To do', 'Done']))
            db.commit()
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        engine.dispose()
        TEST_DB.unlink(missing_ok=True)

    def login(self, role='operator', workspace='first'):
        response = self.client.post('/api/auth/login', json={'email': f'{role}@{workspace}.example.com', 'password': 'local-test-password'})
        self.assertEqual(response.status_code, 200)
        return {'X-CSRF-Token': response.json()['csrf_token']}

    def brand_body(self, version):
        return dict(agency_name='Harbor Studio', accent='#fedcba', welcome_heading='Start here',
                    welcome_message='A calm beginning.', support_email='help@harbor.example.com', expected_version=version)

    def test_brand_scope_csrf_validation_and_lost_update(self):
        headers = self.login()
        initial = self.client.get('/api/workspace/brand').json()
        self.assertEqual(initial['version'], 0)
        self.assertEqual(self.client.patch('/api/workspace/brand', json=self.brand_body(0)).status_code, 403)
        invalid = {**self.brand_body(0), 'accent': 'url(evil)'}
        self.assertEqual(self.client.patch('/api/workspace/brand', headers=headers, json=invalid).status_code, 422)
        saved = self.client.patch('/api/workspace/brand', headers=headers, json=self.brand_body(0))
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['version'], 1)
        self.assertEqual(self.client.patch('/api/workspace/brand', headers=headers, json=self.brand_body(0)).status_code, 409)
        self.assertEqual(self.client.patch('/api/workspace/brand', headers=headers, json=self.brand_body(1)).json()['version'], 2)
        self.login(workspace='second')
        second = self.client.get('/api/workspace/brand').json()
        self.assertEqual(second['agency_name'], 'Second')
        self.assertEqual(second['version'], 0)
        with SessionLocal() as db:
            self.assertEqual(len(db.scalars(select(WorkspaceBrand)).all()), 1)

    def test_viewer_cannot_change_brand_or_templates(self):
        headers = self.login('viewer')
        self.assertEqual(self.client.get('/api/templates').status_code, 200)
        self.assertEqual(self.client.patch('/api/workspace/brand', headers=headers, json=self.brand_body(0)).status_code, 403)
        body = self.template_body(1)
        self.assertEqual(self.client.patch('/api/templates/website', headers=headers, json=body).status_code, 403)

    def template_body(self, version):
        return dict(expected_version=version, name='Website launch', description='Client-owned assets',
                    checklist=[dict(key='logo', title='Share brand logo', description='PNG or PDF, no credentials.', required=True)],
                    folder_blueprint=['Brand', 'Content'])

    def test_template_versions_retained_and_stale_save_rejected(self):
        headers = self.login()
        first = self.client.get('/api/templates').json()['items'][0]
        saved = self.client.patch('/api/templates/website', headers=headers, json=self.template_body(first['version']))
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['version'], first['version'] + 1)
        self.assertEqual(saved.json()['board_blueprint'], first['board_blueprint'])
        self.assertEqual(self.client.patch('/api/templates/website', headers=headers, json=self.template_body(first['version'])).status_code, 409)
        with SessionLocal() as db:
            original = db.get(OnboardingTemplateVersion, first['id'])
            self.assertEqual(original.checklist[0]['title'], 'Upload logo')
            self.assertFalse(original.active)
        self.login(workspace='second')
        self.assertEqual(self.client.get('/api/templates').json()['items'][0]['version'], 1)
        self.assertEqual(self.client.patch('/api/templates/unknown', headers=self.login(), json=self.template_body(1)).status_code, 404)

    def test_reject_duplicate_keys_empty_names_and_paths(self):
        headers = self.login()
        version = self.client.get('/api/templates').json()['items'][0]['version']
        body = self.template_body(version)
        for folders in (['Brand', 'brand'], ['../folder'], ['   ']):
            response = self.client.patch('/api/templates/website', headers=headers, json={**body, 'folder_blueprint': folders})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.patch('/api/templates/website', headers=headers,
                         json={**body, 'checklist': body['checklist'] * 2}).status_code, 422)
        self.assertEqual(self.client.patch('/api/templates/website', headers=headers, json={**body, 'name': '   '}).status_code, 422)

    def test_client_progress_uses_visible_items_and_intake_closes_on_substate(self):
        with SessionLocal() as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == 'second'))
            owner = db.scalar(select(User).where(User.workspace_id == workspace.id, User.role == 'operator'))
            client = Client(workspace_id=workspace.id, name='Scoped client', email='client@second.example.com')
            db.add(client)
            db.flush()
            deal = WonDeal(workspace_id=workspace.id, client_id=client.id, external_deal_id='scoped-progress',
                           business_hash='test-hash', services=['website'], approved_scope='A website launch',
                           proposal_text='Approved scope', timeline={}, account_owner_id=owner.id)
            db.add(deal)
            db.flush()
            onboarding = Onboarding(workspace_id=workspace.id, deal_id=deal.id, client_id=client.id, status='waiting_for_client')
            db.add(onboarding)
            db.flush()
            for key, visible, status in [('public', True, 'completed'), ('internal', False, 'open')]:
                db.add(ChecklistItem(onboarding_id=onboarding.id, item_key=key, title=key, required=True,
                                    status=status, source='template', client_visible=visible))
            db.commit()
            items = db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding.id)).all()
            db.add(IntakeSubmission(onboarding_id=onboarding.id, answers=[{"checklist_item_id": item.id, "value": f"{item.item_key} answer"} for item in items]))
            db.commit()
            scoped = client_detail(db, onboarding)
            self.assertEqual(scoped['onboarding']['required_total'], 1)
            self.assertEqual(scoped['onboarding']['progress_percent'], 100)
            self.assertTrue(scoped['onboarding']['intake_open'])
            self.assertEqual([i['title'] for i in scoped['checklist']], ['public'])
            self.assertEqual(scoped['brand']['agency_name'], 'Second')
            self.assertEqual(len(scoped['submissions'][0]['answers']), 1)
            self.assertEqual(scoped['submissions'][0]['answers'][0]['value'], 'public answer')
            self.assertNotIn('portal_link', scoped['onboarding'])
            onboarding.substate = 'uncertain'
            db.commit()
            self.assertFalse(client_detail(db, onboarding)['onboarding']['intake_open'])


if __name__ == '__main__':
    unittest.main()
