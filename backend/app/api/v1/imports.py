"""Import wizard endpoints (upload -> detect -> preview -> validate -> confirm)."""
from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import TenantAdmin, TenantAnalyst
from app.core.errors import ValidationFailed
from app.models import ImportJob
from app.models.enums import MeterType
from app.schemas.imports import ImportConfirmRequest, ImportJobOut, ImportResult
from app.services import importer

router = APIRouter(tags=["imports"])

ALLOWED_EXT = (".csv", ".xlsx", ".txt", ".tsv")


async def _read_upload(file: UploadFile) -> bytes:
    name = (file.filename or "").lower()
    if not name.endswith(ALLOWED_EXT):
        raise ValidationFailed("Only .csv, .tsv, .txt and .xlsx files are accepted",
                               code="unsupported_file_type")
    content = await file.read(settings.UPLOAD_MAX_MB * 1024 * 1024 + 1)
    if len(content) > settings.UPLOAD_MAX_MB * 1024 * 1024:
        raise ValidationFailed(f"File exceeds {settings.UPLOAD_MAX_MB} MB", code="file_too_large")
    # content sniffing: an .xlsx must be a ZIP container, never an executable
    if name.endswith(".xlsx") and not content.startswith(b"PK\x03\x04"):
        raise ValidationFailed("This file is not a valid XLSX workbook", code="invalid_upload")
    if not name.endswith(".xlsx") and b"\x00" in content[:4096]:
        raise ValidationFailed("Binary content is not valid for a CSV upload", code="invalid_upload")
    return content


def _mapping_from_form(mapping_timestamp, mapping_consumption_kwh, mapping_register_kwh,
                       mapping_interval_minutes) -> dict[str, str] | None:
    mapping = {"timestamp": mapping_timestamp, "consumption_kwh": mapping_consumption_kwh,
               "register_kwh": mapping_register_kwh, "interval_minutes": mapping_interval_minutes}
    return {k: v for k, v in mapping.items() if v} or None


@router.get("/imports/templates/{fmt}", summary="Download an import template (csv or xlsx)")
def download_template(fmt: str):
    if fmt == "csv":
        return StreamingResponse(io.BytesIO(importer.csv_template()), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          'attachment; filename="nextgen-import-template.csv"'})
    if fmt == "xlsx":
        return StreamingResponse(
            io.BytesIO(importer.xlsx_template()),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="nextgen-import-template.xlsx"'})
    raise ValidationFailed("Template format must be 'csv' or 'xlsx'", code="unsupported_format")


@router.post("/imports", response_model=ImportJobOut, status_code=201,
             summary="Upload a file; columns are detected and rows validated automatically")
async def create_import(tenant: TenantAnalyst,
                        file: UploadFile = File(...),
                        meter_id: uuid.UUID | None = Form(default=None),
                        reading_type: str | None = Form(default=None, pattern="^(interval|cumulative)$"),
                        assume_timezone: str = Form(default=settings.DISPLAY_TZ),
                        interval_minutes: int | None = Form(default=None, ge=1, le=1440),
                        decimal_comma: bool | None = Form(default=None),
                        mapping_timestamp: str | None = Form(default=None),
                        mapping_consumption_kwh: str | None = Form(default=None),
                        mapping_register_kwh: str | None = Form(default=None),
                        mapping_interval_minutes: str | None = Form(default=None)):
    content = await _read_upload(file)
    if meter_id is None:
        raise ValidationFailed("Select the meter these readings belong to", code="meter_required")
    job = importer.create_job(tenant, filename=file.filename or "upload.csv", content=content,
                              content_type=file.content_type, meter_id=meter_id,
                              reading_type=reading_type)
    mapping = _mapping_from_form(mapping_timestamp, mapping_consumption_kwh,
                                 mapping_register_kwh, mapping_interval_minutes)
    job_out = _job_with_file(tenant, job.id, content, meter_id=meter_id,
                            reading_type=reading_type or job.reading_type, mapping=mapping,
                            assume_timezone=assume_timezone, interval_minutes=interval_minutes,
                            decimal_comma=decimal_comma)
    return job_out


def _job_with_file(tenant, job_id: uuid.UUID, content: bytes, *, meter_id: uuid.UUID,
                   reading_type: str, mapping: dict | None, assume_timezone: str,
                   interval_minutes: int | None, decimal_comma: bool | None) -> ImportJobOut:
    importer.validate_job(tenant, job_id, content=content, meter_id=meter_id,
                          reading_type=reading_type, mapping=mapping, tz_name=assume_timezone,
                          interval_minutes=interval_minutes, decimal_comma=decimal_comma)
    job = tenant.db.scalar(select(ImportJob).where(ImportJob.id == job_id))
    return ImportJobOut.model_validate(job)


@router.post("/imports/{job_id}/validate", response_model=ImportJobOut,
             summary="Re-validate the same file with an explicit column mapping")
async def validate_import(tenant: TenantAnalyst, job_id: uuid.UUID,
                          file: UploadFile = File(...),
                          meter_id: uuid.UUID | None = Form(default=None),
                          reading_type: str | None = Form(default=None, pattern="^(interval|cumulative)$"),
                          assume_timezone: str = Form(default=settings.DISPLAY_TZ),
                          interval_minutes: int | None = Form(default=None, ge=1, le=1440),
                          decimal_comma: bool | None = Form(default=None),
                          mapping_timestamp: str | None = Form(default=None),
                          mapping_consumption_kwh: str | None = Form(default=None),
                          mapping_register_kwh: str | None = Form(default=None),
                          mapping_interval_minutes: str | None = Form(default=None)):
    content = await _read_upload(file)
    existing = tenant.db.scalar(select(ImportJob).where(
        ImportJob.id == job_id, ImportJob.organization_id == tenant.org_id))
    if existing is None:
        from app.core.errors import NotFound
        raise NotFound("Import job not found")
    target_meter = meter_id or existing.meter_id
    if target_meter is None:
        raise ValidationFailed("Select the meter these readings belong to", code="meter_required")
    mapping = _mapping_from_form(mapping_timestamp, mapping_consumption_kwh,
                                 mapping_register_kwh, mapping_interval_minutes)
    return _job_with_file(tenant, job_id, content, meter_id=target_meter,
                          reading_type=reading_type or existing.reading_type, mapping=mapping,
                          assume_timezone=assume_timezone, interval_minutes=interval_minutes,
                          decimal_comma=decimal_comma)


@router.get("/imports", summary="Import history")
def list_imports(tenant: TenantAnalyst, page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100)):
    base = select(ImportJob).where(ImportJob.organization_id == tenant.org_id)
    total = tenant.db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(tenant.db.scalars(base.order_by(ImportJob.created_at.desc())
                                  .limit(page_size).offset((page - 1) * page_size)))
    return {"items": [ImportJobOut.model_validate(r) for r in rows], "total": total,
            "page": page, "page_size": page_size, "has_next": page * page_size < total}


@router.get("/imports/{job_id}", response_model=ImportJobOut, summary="Import job detail")
def get_import(tenant: TenantAnalyst, job_id: uuid.UUID):
    job = tenant.db.scalar(select(ImportJob).where(
        ImportJob.id == job_id, ImportJob.organization_id == tenant.org_id))
    if job is None:
        from app.core.errors import NotFound
        raise NotFound("Import job not found")
    return ImportJobOut.model_validate(job)


@router.post("/imports/{job_id}/confirm", response_model=ImportResult,
             summary="Commit the validated rows into meter_readings")
def confirm_import(tenant: TenantAnalyst, job_id: uuid.UUID,
                   payload: ImportConfirmRequest | None = None):
    result = importer.confirm_job(tenant, job_id,
                                  skip_duplicates=(payload.skip_duplicates if payload else True))
    return ImportResult.model_validate(result)
