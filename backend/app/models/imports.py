"""Import jobs: uploaded file -> detected mapping -> validation -> confirmed readings."""
from __future__ import annotations

import uuid
from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin


class ImportJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "import_jobs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    meter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meters.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="uploaded", server_default="uploaded", nullable=False)
    reading_type: Mapped[str] = mapped_column(String(16), default="interval", server_default="interval", nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    missing_intervals: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    errors: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    preview: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    warnings: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportStagingRow(Base, UUIDMixin):
    """Validated but not-yet-committed readings.

    The wizard preview only keeps the first 200 rows, so the full validated set
    lives here until the user confirms. Rows are deleted after a successful commit.
    """

    __tablename__ = "import_staging_rows"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    __table_args__ = (
        Index("ix_staging_job_ts", "import_job_id", "ts"),
        Index("ix_staging_org", "organization_id"),
    )
