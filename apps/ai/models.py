from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PlanRequest(BaseModel):
    onboarding_id: str = Field(min_length=1, max_length=100)
    client_name: str = Field(min_length=1, max_length=200)
    approved_scope: str = Field(min_length=10, max_length=20000)
    purchased_services: list[str] = Field(min_length=1, max_length=8)
    reference_date: date

    @field_validator("purchased_services")
    @classmethod
    def unique_services(cls, services: list[str]) -> list[str]:
        if len(set(services)) != len(services):
            raise ValueError("purchased_services must be unique")
        return services


class ChecklistDraft(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    title: str = Field(min_length=3, max_length=200)
    required: bool
    source: Literal["template", "scope"]
    service_code: str
    evidence: str = ""
    client_visible: bool = True
    due_date: date | None = None


class ExtractedItem(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    title: str = Field(min_length=3, max_length=200)
    service_code: str
    evidence: str = Field(min_length=3, max_length=500)
    required: bool = True


class Extraction(BaseModel):
    items: list[ExtractedItem] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=20)
    missing_inputs: list[str] = Field(default_factory=list, max_length=20)
    suggestions: list[str] = Field(default_factory=list, max_length=20)


class PlanResponse(BaseModel):
    checklist: list[ChecklistDraft]
    deliverables: list[str]
    risks: list[str]
    missing_inputs: list[str]
    welcome_draft: str
    summary: str = Field(min_length=1, max_length=5000)
    suggestions: list[str]
    model_mode: Literal["demo", "connected"]
    synthetic: bool
