from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionPlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None = None
    price_kzt: int
    currency: str
    billing_period: str
    max_jobs_per_month: int
    max_records_per_month: int
    allowed_sources: list[str]
    is_active: bool
    is_public: bool
    is_default: bool


class SubscriptionPlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    price_kzt: int = Field(default=0, ge=0)
    currency: str = Field(default="KZT", max_length=8)
    billing_period: str = Field(default="monthly", max_length=32)
    max_jobs_per_month: int = Field(default=-1, ge=-1)
    max_records_per_month: int = Field(default=500, ge=-1)
    allowed_sources: list[str] = Field(default_factory=list)
    is_active: bool = True
    is_public: bool = True
    is_default: bool = False


class SubscriptionPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    price_kzt: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    billing_period: str | None = Field(default=None, max_length=32)
    max_jobs_per_month: int | None = Field(default=None, ge=-1)
    max_records_per_month: int | None = Field(default=None, ge=-1)
    allowed_sources: list[str] | None = None
    is_active: bool | None = None
    is_public: bool | None = None
    is_default: bool | None = None


class UserSubscriptionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    plan_id: UUID
    status: str
    starts_at: datetime
    ends_at: datetime | None = None
    plan: SubscriptionPlanPublic


class AssignSubscriptionRequest(BaseModel):
    plan_code: str | None = None
    plan_id: UUID | None = None
    ends_at: datetime | None = None


class UsageSummary(BaseModel):
    subscription: UserSubscriptionPublic
    jobs_used: int
    records_used: int
    jobs_remaining: int
    records_remaining: int
    month_started_at: datetime


class InvoiceCreateRequest(BaseModel):
    plan_id: UUID | None = None
    plan_code: str | None = None
    provider: str = Field(default="manual_qr", max_length=64)
    receipt_id: str | None = Field(default=None, max_length=128)


class InvoicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    plan_id: UUID
    status: str
    amount_kzt: int
    currency: str
    provider: str
    provider_invoice_id: str | None = None
    payment_url: str | None = None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None = None
    expires_at: datetime | None = None
    plan: SubscriptionPlanPublic


class PaymentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    user_id: UUID
    status: str
    amount_kzt: int
    currency: str
    provider: str
    provider_payment_id: str | None = None
    raw_payload: dict
    created_at: datetime
    updated_at: datetime


class InvoiceListResponse(BaseModel):
    items: list[InvoicePublic]
    total: int


class PaymentWebhookPayload(BaseModel):
    invoice_id: UUID | None = None
    provider_invoice_id: str | None = None
    provider_payment_id: str | None = None
    status: str
    amount_kzt: int | None = None
    currency: str = "KZT"
    raw_payload: dict = Field(default_factory=dict)


class PaymentProviderPublic(BaseModel):
    provider_name: str
    checkout_mode: str
    checkout_url_template: str | None = None
    success_url: str | None = None
    cancel_url: str | None = None
    webhook_secret_configured: bool
    kaspi_qr_enabled: bool = False
    kaspi_pos_base_url: str | None = None


class PaymentQrSettingPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    note: str | None = None
    image_data: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PaymentQrSettingUpdate(BaseModel):
    title: str = Field(default="Kaspi QR", min_length=2, max_length=255)
    note: str | None = None
    image_data: str | None = None
    is_active: bool = True
