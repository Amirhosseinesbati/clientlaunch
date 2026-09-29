"""The AI-only graph: n8n owns every business side effect."""

import json
from datetime import timedelta
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .adapters import ScopeExtractor
from .models import ChecklistDraft, Extraction, PlanRequest, PlanResponse


TEMPLATES = json.loads(Path(__file__).with_name("templates.json").read_text(encoding="utf-8"))
TEMPLATE_BY_CODE = {item["service_code"]: item for item in TEMPLATES}


class PlanState(TypedDict, total=False):
    request: PlanRequest
    scope: str
    templates: list[dict]
    extraction: Extraction
    checklist: list[ChecklistDraft]
    deliverables: list[str]
    risks: list[str]
    missing_inputs: list[str]
    welcome_draft: str
    summary: str
    suggestions: list[str]
    response: PlanResponse


def build_graph(extractor: ScopeExtractor, *, checkpointer=None):
    def parse_scope(state: PlanState) -> dict:
        return {"scope": " ".join(state["request"].approved_scope.split())}

    def retrieve_templates(state: PlanState) -> dict:
        services = state["request"].purchased_services
        unknown = set(services) - TEMPLATE_BY_CODE.keys()
        if unknown:
            raise ValueError(f"Unknown purchased service codes: {sorted(unknown)}")
        return {"templates": [TEMPLATE_BY_CODE[code] for code in services]}

    def extract_specifics(state: PlanState) -> dict:
        return {"extraction": extractor.extract(state["scope"], state["request"].purchased_services)}

    def identify_gaps(state: PlanState) -> dict:
        names = [item["title"] for template in state["templates"] for item in template["tasks"] if item["required"]]
        return {"missing_inputs": names + state["extraction"].missing_inputs, "risks": state["extraction"].risks}

    def draft_plan(state: PlanState) -> dict:
        request = state["request"]
        due = request.reference_date + timedelta(days=7)
        checklist = [
            ChecklistDraft(key=item["key"], title=item["title"],
                           required=item["required"], source="template", service_code=template["service_code"],
                           evidence="", due_date=due)
            for template in state["templates"] for item in template["tasks"]
        ]
        checklist.extend(
            ChecklistDraft(key=f"{item.service_code}_{item.key}", title=item.title,
                           required=item.required, source="scope", service_code=item.service_code,
                           evidence=item.evidence, due_date=due)
            for item in state["extraction"].items
        )
        service_names = ", ".join(template["name"] for template in state["templates"])
        welcome = (f"Hello {request.client_name},\n\nYour {service_names} project is ready to begin. "
                   "Please use your private onboarding portal link to complete the checklist, upload brand assets, "
                   "and share two options for kickoff availability. Your account owner will confirm next steps.\n\n"
                   "Thank you,\nThe delivery team")
        summary = f"{request.client_name}: {service_names}. Approved scope: {state['scope'][:800]}"
        return {"checklist": checklist, "deliverables": [template["name"] for template in state["templates"]],
                "welcome_draft": welcome, "summary": summary,
                "suggestions": state["extraction"].suggestions}

    def validate_scope(state: PlanState) -> dict:
        services = set(state["request"].purchased_services)
        scope = state["scope"].casefold()
        seen: set[tuple[str, str]] = set()
        accepted: list[ChecklistDraft] = []
        suggestions = list(state["suggestions"])
        for item in state["checklist"]:
            identity = (item.service_code, item.key)
            if identity in seen:
                continue
            seen.add(identity)
            if item.service_code not in services or (item.source == "scope" and item.evidence.casefold() not in scope):
                suggestions.append(f"Review unsupported proposed item: {item.title}")
                continue
            accepted.append(item)
        return {"response": PlanResponse(checklist=accepted, deliverables=state["deliverables"],
                                          risks=state["risks"], missing_inputs=state["missing_inputs"],
                                          welcome_draft=state["welcome_draft"], summary=state["summary"],
                                          suggestions=suggestions,
                                          model_mode=extractor.mode, synthetic=extractor.mode == "demo")}

    builder = StateGraph(PlanState)
    builder.add_node("parse_approved_scope", parse_scope)
    builder.add_node("retrieve_service_templates", retrieve_templates)
    builder.add_node("extract_scope_evidence", extract_specifics)
    builder.add_node("identify_missing_inputs_and_risks", identify_gaps)
    builder.add_node("draft_plan_and_welcome", draft_plan)
    builder.add_node("validate_against_purchased_services", validate_scope)
    builder.add_edge(START, "parse_approved_scope")
    builder.add_edge("parse_approved_scope", "retrieve_service_templates")
    builder.add_edge("retrieve_service_templates", "extract_scope_evidence")
    builder.add_edge("extract_scope_evidence", "identify_missing_inputs_and_risks")
    builder.add_edge("identify_missing_inputs_and_risks", "draft_plan_and_welcome")
    builder.add_edge("draft_plan_and_welcome", "validate_against_purchased_services")
    builder.add_edge("validate_against_purchased_services", END)
    return builder.compile(checkpointer=checkpointer)
