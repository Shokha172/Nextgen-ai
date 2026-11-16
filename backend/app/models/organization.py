"""Organizations and membership (the tenant boundary)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin
from app.models.enums import Industry, Role


class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    industry: Mapped[str] = mapped_column(String(32), default=Industry.MANUFACTURING.value, server_default=Industry.MANUFACTURING.value, nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="UZ", server_default="UZ", nullable=False)
    region: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(400))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tashkent", server_default="Asia/Tashkent", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS", nullable=False)
    # Thresholds used by explainable anomaly detection (org-level defaults).
    anomaly_z_threshold: Mapped[float] = mapped_column(default=3.0, server_default=text("3.0"), nullable=False)
    anomaly_min_deviation_pct: Mapped[float] = mapped_column(default=25.0, server_default=text("25.0"), nullable=False)
    # DEMO orgs hold synthetic data only and are hard-blocked from production paths.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    settings: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", lazy="selectin")


class OrganizationMember(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organization_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    # NULL while an invitation is pending: the person may not have an account yet.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16), default=Role.VIEWER.value, server_default=Role.VIEWER.value, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active", nullable=False)  # active|invited|suspended
    invited_email: Mapped[str | None] = mapped_column(String(320))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # SHA-256 of the one-time invitation token handed to the admin for out-of-band
    # sharing (no SMTP in this build); NULL once accepted.
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization] = relationship(back_populates="members")
    user = relationship("User", back_populates="memberships", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
        Index("ix_org_members_lookup", "organization_id", "user_id", "status"),
    )
