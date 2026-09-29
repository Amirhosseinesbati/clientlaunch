"""Create 80 reproducible, synthetic ClientLaunch evaluation scenarios.

Requests and answer keys are deliberately separate. Only requests.jsonl is sent
to the planning service. The labels are authored from the structured scenario,
never inferred from the model response.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SERVICES = ("website", "brand", "seo", "content", "ads", "analytics", "email", "ecommerce")
FEATURES = (
    ("website", "language_versions", "Confirm language versions", "multilingual site", "site in two languages"),
    ("website", "booking_rules", "Provide booking rules", "booking flow", "appointment scheduling"),
    ("brand", "brand_guidelines", "Upload existing brand guidelines", "brand guidelines", "existing brand manual"),
    ("seo", "business_locations", "Confirm business locations", "local SEO", "location-based search"),
    ("ads", "retargeting_audience", "Confirm retargeting audience", "retargeting campaign", "return-visitor ads"),
    ("analytics", "tracking_events", "Confirm conversion events", "conversion tracking", "track completed inquiries"),
    ("email", "email_segments", "Confirm email audience segments", "newsletter sequence", "segmented email journeys"),
    ("ecommerce", "catalog_details", "Provide catalog details", "Shopify catalog", "online store products"),
)
TEMPLATE_KEYS = {
    "website": ["brand_logo", "website_copy", "domain_access", "kickoff_availability"],
    "brand": ["existing_brand_files", "brand_references", "stakeholder_list"],
    "seo": ["search_console_access", "target_markets", "priority_topics"],
    "content": ["tone_guide", "content_approver", "source_material"],
    "ads": ["ad_account_access", "campaign_budget", "creative_assets"],
    "analytics": ["analytics_access", "conversion_goals", "privacy_contact"],
    "email": ["esp_access", "sender_domain", "consent_policy"],
    "ecommerce": ["product_catalog", "shipping_rules", "store_access"],
}


def make_rows(
    seed: int,
    reference_date: date,
    held_out_phrases: dict[str, list[str]] | None = None,
    id_prefix: str = "CL-EVAL",
    entity_prefix: str = "Example Client",
) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    requests: list[dict] = []
    labels: list[dict] = []
    for index in range(80):
        split = "development" if index < 25 else "held_out"
        main = SERVICES[index % len(SERVICES)]
        second = SERVICES[(index + 3) % len(SERVICES)] if index % 4 == 0 else None
        purchased = [main] + ([second] if second else [])
        candidates = [f for f in FEATURES if f[0] in purchased]
        selected = candidates[index % len(candidates)] if candidates else None
        if selected and split == "held_out" and held_out_phrases is not None:
            phrase_key = f"{selected[0]}:{selected[1]}"
            variants = held_out_phrases.get(phrase_key)
            if not variants or not all(isinstance(value, str) and value.strip() for value in variants):
                raise ValueError(f"Missing nonempty independently authored phrases for {phrase_key}")
            phrase = rng.choice(variants)
        else:
            phrase = (selected[3] if split == "development" else selected[4]) if selected else "a standard content delivery plan"
        # Every fifth scenario contains an idea for an unpurchased service; it
        # must remain a suggestion rather than a contractual checklist item.
        unsupported = FEATURES[(index + 5) % len(FEATURES)] if index % 5 == 0 else None
        if unsupported and unsupported[0] in purchased:
            unsupported = next(f for f in FEATURES if f[0] not in purchased)
        service_text = ", ".join(purchased)
        scope = (
            f"Approved proposal for {service_text}. The client requests {phrase}. "
            "The account owner will confirm deliverables and request all launch inputs."
        )
        if unsupported:
            scope += f" The client also mentioned {unsupported[3]}, which is outside the purchased services."
        if index % 11 == 0:
            scope += " The timeline is urgent and must be reviewed with the client."
        scenario_id = f"{id_prefix}-{index + 1:03d}"
        ref = reference_date + timedelta(days=index if split == "development" else 100 + index)
        request = {
            "onboarding_id": scenario_id,
            "client_name": f"{entity_prefix} {index + 1:03d}",
            "approved_scope": scope,
            "purchased_services": purchased,
            "reference_date": ref.isoformat(),
        }
        request_keys = {f"{service}:{key}" for service in purchased for key in TEMPLATE_KEYS[service]}
        scope_key = f"{selected[0]}:{selected[1]}" if selected else None
        # Reminder and recovery labels are independent contract fixtures for a
        # future triggered n8n/API evaluator; /plan runner does not score them.
        reminder_state = ("waiting_for_client", "paused", "ready", "handed_off")[index % 4]
        due_offset = (-2, 2, -8)[index % 3]
        prior_sent = index % 4
        last_sent_days_ago = index % 6
        reminder_draft = (
            reminder_state == "waiting_for_client"
            and due_offset <= 0
            and prior_sent < 3
            and (prior_sent == 0 or last_sent_days_ago >= 3)
        )
        failure_after_folder = index % 6 == 0
        ambiguous = failure_after_folder and index % 12 == 0
        labels.append({
            "scenario_id": scenario_id,
            "split": split,
            "expected_scope_items": [scope_key] if scope_key else [],
            "expected_required_inputs": sorted(request_keys | ({scope_key} if scope_key else set())),
            "unsupported_service": unsupported[0] if unsupported else None,
            "reminder": {
                "onboarding_state": reminder_state,
                "due_offset_days": due_offset,
                "prior_dispatched_count": prior_sent,
                "last_dispatched_days_ago": last_sent_days_ago,
                "expected_draft": reminder_draft,
            },
            "recovery": {
                "folder_created": failure_after_folder,
                "board_created": not failure_after_folder,
                "provider_outcome_ambiguous": ambiguous,
                "expected_action": "reconcile" if ambiguous else "resume_board_keep_folder" if failure_after_folder else "no_recovery",
            },
        })
        requests.append({"scenario_id": scenario_id, "split": split, "request": request})
    rng.shuffle(requests)
    rng.shuffle(labels)
    return requests, labels


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=8042)
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date(2026, 9, 28))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datasets")
    parser.add_argument("--held-out-phrases", type=Path, help="Independent JSON mapping service:key to unseen phrase lists")
    parser.add_argument("--id-prefix", default="CL-EVAL")
    parser.add_argument("--entity-prefix", default="Example Client")
    args = parser.parse_args()
    if args.held_out_phrases and args.output_dir.resolve() == (ROOT / "datasets").resolve():
        parser.error("A new phrase bank requires --output-dir; preserve the original evaluation files")
    if args.held_out_phrases and (args.id_prefix == "CL-EVAL" or args.entity_prefix == "Example Client"):
        parser.error("A new phrase bank requires new --id-prefix and --entity-prefix values")
    phrase_bank = json.loads(args.held_out_phrases.read_text(encoding="utf-8")) if args.held_out_phrases else None
    requests, labels = make_rows(args.seed, args.reference_date, phrase_bank, args.id_prefix, args.entity_prefix)
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    write_jsonl(destination / "requests.jsonl", requests)
    write_jsonl(destination / "ground_truth.jsonl", labels)
    (destination / "manifest.json").write_text(
        json.dumps({"synthetic": True, "seed": args.seed, "reference_date": args.reference_date.isoformat(),
                    "count": 80, "development": 25, "held_out": 55,
                    "id_prefix": args.id_prefix, "entity_prefix": args.entity_prefix,
                    "independent_phrase_bank": str(args.held_out_phrases) if args.held_out_phrases else None,
                    "runtime_input": "requests.jsonl", "labels_not_for_runtime": "ground_truth.jsonl"}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Generated 80 synthetic scenarios (25 development, 55 held out).")


if __name__ == "__main__":
    main()
