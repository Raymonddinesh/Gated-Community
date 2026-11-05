"""Phase 21 — Commercial SaaS Platform Administration & Subscription Models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.src.database.base import ArchiveMixin, Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from apps.api.src.database.models.identity import User
    from apps.api.src.database.models.society import Society


class PlatformSubscriptionPlan(Base, TimestampMixin, ArchiveMixin):
    """
    Global Subscription Plan Catalog (e.g. FREE, STANDARD, ENTERPRISE).
    Not tenant-scoped.
    """

    __tablename__ = "platform_subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    plan_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    monthly_price: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0.00,
    )
    annual_price: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0.00,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    trial_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=14,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    entitlements: Mapped[list["SubscriptionPlanEntitlement"]] = relationship(
        "SubscriptionPlanEntitlement",
        back_populates="plan",
        cascade="all, delete-orphan",
    )
    subscriptions: Mapped[list["SocietySubscription"]] = relationship(
        "SocietySubscription",
        back_populates="plan",
    )


class SubscriptionPlanEntitlement(Base, TimestampMixin):
    """
    Entitlements provided by a PlatformSubscriptionPlan.
    """

    __tablename__ = "subscription_plan_entitlements"
    __table_args__ = (
        UniqueConstraint("plan_id", "entitlement_key", name="uq_plan_entitlement_key"),
        CheckConstraint("entitlement_type IN ('BOOLEAN', 'NUMERIC', 'UNLIMITED')", name="ck_entitlement_type_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_subscription_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entitlement_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    entitlement_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="BOOLEAN",
    )
    entitlement_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    plan: Mapped["PlatformSubscriptionPlan"] = relationship(
        "PlatformSubscriptionPlan",
        back_populates="entitlements",
    )


class SocietySubscription(Base, TimestampMixin, TenantScopedMixin):
    """
    Subscription details for a tenant Society.
    """

    __tablename__ = "society_subscriptions"
    __table_args__ = (
        UniqueConstraint("society_id", name="uq_society_subscriptions_society_id"),
        Index("ix_society_subscriptions_status", "society_id", "status"),
        Index("ix_society_subscriptions_gateway_customer", "gateway_customer_id"),
        Index("ix_society_subscriptions_gateway_sub", "gateway_subscription_id"),
        Index("ix_society_subscriptions_next_billing", "next_billing_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("platform_subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="TRIAL",
    )
    billing_cycle: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="MONTHLY",
    )
    auto_renew: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    gateway_customer_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    gateway_subscription_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    next_billing_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    past_due_since: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    plan: Mapped["PlatformSubscriptionPlan"] = relationship("PlatformSubscriptionPlan", back_populates="subscriptions")


class SocietyFeatureOverride(Base, TimestampMixin, TenantScopedMixin):
    """
    Tenant-specific feature override.
    """

    __tablename__ = "society_feature_overrides"
    __table_args__ = (
        UniqueConstraint("society_id", "feature_key", name="uq_society_feature_override_key"),
        Index("ix_society_feature_overrides_lookup", "society_id", "feature_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    feature_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    override_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    creator: Mapped["User | None"] = relationship("User")


class SocietyQuotaOverride(Base, TimestampMixin, TenantScopedMixin):
    """
    Tenant-specific quota override limit.
    """

    __tablename__ = "society_quota_overrides"
    __table_args__ = (
        UniqueConstraint("society_id", "quota_key", name="uq_society_quota_override_key"),
        CheckConstraint("max_limit >= 0", name="ck_society_quota_override_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    quota_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    max_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    override_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
    creator: Mapped["User | None"] = relationship("User")


class SocietyUsageMetric(Base, TimestampMixin, TenantScopedMixin):
    """
    Race-safe usage counter metrics for tenant societies.
    """

    __tablename__ = "society_usage_metrics"
    __table_args__ = (
        UniqueConstraint("society_id", "metric_key", name="uq_society_usage_metric_key"),
        CheckConstraint("current_value >= 0", name="ck_society_usage_metric_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    metric_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    current_value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    society: Mapped["Society"] = relationship("Society")


class SocietyProvisioningLog(Base, TimestampMixin, TenantScopedMixin):
    """
    Audit log of provisioning attempts and status steps.
    """

    __tablename__ = "society_provisioning_logs"
    __table_args__ = (
        Index("ix_society_provisioning_logs_request", "provisioning_request_id"),
        Index("ix_society_provisioning_logs_society", "society_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    provisioning_request_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    step_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="STARTED",
    )
    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    society: Mapped["Society"] = relationship("Society")
