import unittest
from datetime import date

from apps.ai.adapters import DemoScopeExtractor
from apps.ai.graph import build_graph
from apps.ai.models import PlanRequest


class PlanGraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph(DemoScopeExtractor())

    def test_scope_item_requires_purchased_service(self):
        result = self.graph.invoke({"request": PlanRequest(
            onboarding_id="demo-1", client_name="Maple Studio", reference_date=date(2026, 9, 28),
            approved_scope="We will build a bilingual website with a booking form for Maple Studio.",
            purchased_services=["website"])})["response"]
        self.assertIn("website_language_versions", [item.key for item in result.checklist])
        self.assertIn("website_booking_rules", [item.key for item in result.checklist])
        self.assertTrue(all(item.evidence.lower() in "we will build a bilingual website with a booking form for maple studio." for item in result.checklist if item.source == "scope"))

    def test_unpurchased_work_is_only_suggestion(self):
        result = self.graph.invoke({"request": PlanRequest(
            onboarding_id="demo-2", client_name="Maple Studio", reference_date=date(2026, 9, 28),
            approved_scope="Build a website with a product catalog, but commerce was not purchased.",
            purchased_services=["website"])})["response"]
        self.assertFalse(any(item.service_code == "ecommerce" for item in result.checklist))
        self.assertTrue(result.suggestions)

    def test_unknown_service_fails_closed(self):
        with self.assertRaises(ValueError):
            self.graph.invoke({"request": PlanRequest(
                onboarding_id="demo-3", client_name="Maple Studio", reference_date=date(2026, 9, 28),
                approved_scope="This is a sufficiently long approved scope.", purchased_services=["unknown"])})

    def test_excluded_feature_does_not_become_contractual_input(self):
        result = self.graph.invoke({"request": PlanRequest(
            onboarding_id="demo-4", client_name="Maple Studio", reference_date=date(2026, 9, 28),
            approved_scope="Build an informational website. No booking flow is included in this scope.",
            purchased_services=["website"])})["response"]
        self.assertNotIn("website_booking_rules", [item.key for item in result.checklist])

    def test_background_booking_reference_is_not_a_booking_feature(self):
        result = self.graph.invoke({"request": PlanRequest(
            onboarding_id="demo-5", client_name="Maple Studio", reference_date=date(2026, 9, 28),
            approved_scope="Our hotel gets most bookings from German and Spanish travelers; the new site should serve both languages.",
            purchased_services=["website"])})["response"]
        keys = [item.key for item in result.checklist]
        self.assertIn("website_language_versions", keys)
        self.assertNotIn("website_booking_rules", keys)

    def test_template_keys_match_business_api_contract_and_summary_is_present(self):
        result = self.graph.invoke({"request": PlanRequest(
            onboarding_id="demo-6", client_name="Willow Harbor Studio", reference_date=date(2026, 9, 28),
            approved_scope="Launch a website and brand identity for Willow Harbor Studio.",
            purchased_services=["website", "brand"])})["response"]
        template_keys = {(item.service_code, item.key) for item in result.checklist if item.source == "template"}
        self.assertIn(("website", "brand_logo"), template_keys)
        self.assertIn(("brand", "existing_brand_files"), template_keys)
        self.assertNotIn(("website", "website_brand_logo"), template_keys)
        self.assertEqual(len(template_keys), len([item for item in result.checklist if item.source == "template"]))
        self.assertIn("Willow Harbor Studio", result.summary)
        self.assertIn("website and brand identity", result.summary.lower())


if __name__ == "__main__":
    unittest.main()
