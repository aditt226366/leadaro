"""Request/response shapes. Field names match apps/web/lib/mock.ts exactly."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Mode = Literal["voice", "call"]
VoiceType = Literal["ai", "human", "hybrid"]


# ── auth ─────────────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    token: str
    user: dict


# ── campaigns ────────────────────────────────────────────────────────────────

class CampaignIn(BaseModel):
    mode: Mode
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    type: str | None = None
    goal: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    tags: list[str] = []
    timezone: str = "UTC"
    country: str | None = None
    language: str = "en"
    department: str | None = None
    caller_number_id: str | None = None
    caller_id: str | None = None

    voice_type: VoiceType = "ai"
    voice_id: str | None = None
    voice_config: dict[str, Any] = {}
    script: dict[str, Any] = {}
    flow: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    compliance: dict[str, Any] = {}

    schedule_mode: Literal[
        "immediate", "one_time", "recurring", "drip", "behavior", "workflow"
    ] = "immediate"
    start_date: datetime | None = None
    end_date: datetime | None = None
    business_hours: dict[str, Any] = {"start": "09:00", "end": "18:00"}
    weekdays_only: bool = True
    weekends_only: bool = False
    holiday_rules: dict[str, Any] = {}
    recurrence: dict[str, Any] = {}
    max_daily_calls: int | None = None
    concurrent_calls: int = 5
    calls_per_minute: int = 10
    queue_size: int | None = None
    warmup_mode: bool = False


class CampaignPatch(BaseModel):
    """Wizard steps save incrementally — every field optional."""
    model_config = {"extra": "forbid"}

    name: str | None = None
    description: str | None = None
    type: str | None = None
    goal: str | None = None
    status: Literal[
        "draft", "scheduled", "active", "paused", "completed", "archived"
    ] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    tags: list[str] | None = None
    timezone: str | None = None
    country: str | None = None
    language: str | None = None
    department: str | None = None
    caller_number_id: str | None = None
    caller_id: str | None = None
    voice_type: VoiceType | None = None
    voice_id: str | None = None
    voice_config: dict[str, Any] | None = None
    script: dict[str, Any] | None = None
    flow: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None
    schedule_mode: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    business_hours: dict[str, Any] | None = None
    weekdays_only: bool | None = None
    weekends_only: bool | None = None
    holiday_rules: dict[str, Any] | None = None
    recurrence: dict[str, Any] | None = None
    max_daily_calls: int | None = None
    concurrent_calls: int | None = None
    calls_per_minute: int | None = None
    queue_size: int | None = None
    warmup_mode: bool | None = None


# ── leads ────────────────────────────────────────────────────────────────────

class LeadIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str
    email: str | None = None
    company: str | None = None
    designation: str | None = None
    industry: str | None = None
    city: str | None = None
    country: str | None = None
    website: str | None = None
    source: str = "manual"
    lead_score: int = 0
    tags: list[str] = []
    custom_fields: dict[str, Any] = {}


class AudiencePreview(BaseModel):
    """FRD §5 step 2 — the preview panel before committing an audience."""
    total: int
    reachable: int
    duplicates: int
    invalid: int
    dnc: int
    blacklisted: int
    estimated_cost_usd: float
    predicted_success_rate: float


# ── scripts / voices ─────────────────────────────────────────────────────────

class ScriptGenerateIn(BaseModel):
    """Feature 1 — AI Script Generator, 'Generate with AI' path."""
    prompt: str | None = None
    company_website: str | None = None
    goal: Literal[
        "book_meeting", "qualify_lead", "follow_up", "collect_payment",
        "survey", "reengage", "confirm_verify",
    ]
    offer: str
    audience: str | None = None
    tone: Literal[
        "friendly", "professional", "confident", "energetic",
        "calm", "urgent", "happy", "empathetic",
    ] = "professional"
    cta: str | None = None
    length: Literal["short", "medium", "long"] = "short"
    language: str = "en"


class ScriptImproveIn(BaseModel):
    text: str
    action: Literal[
        "rewrite", "shorten", "professional", "friendly", "urgent",
        "funny", "luxury", "sales", "support", "recruitment",
    ]


# ── calls ────────────────────────────────────────────────────────────────────

class DialIn(BaseModel):
    campaign_id: str
    lead_ids: list[str] | None = None
    limit: int = 50


class OriginateCallIn(BaseModel):
    """
    Dashboard 'Call now' — manual counterpart to the automated dialer.

    Either name an existing `lead_id`, or give a raw `phone` (+ optional `name`)
    to dial a number that isn't a lead yet. The phone path upserts a lead so the
    call is still tied to a person and shows up in history like any other.
    """
    lead_id: str | None = None
    phone: str | None = None
    name: str | None = None
    campaign_id: str | None = None


class BatchContact(BaseModel):
    phone: str
    name: str | None = None


class BatchCallIn(BaseModel):
    """Dial a list of numbers pulled from an uploaded sheet."""
    contacts: list[BatchContact]
    campaign_id: str | None = None
