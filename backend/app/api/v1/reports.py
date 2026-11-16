from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.deps import TenantAnalyst, TenantViewer
from app.services import exports

router = APIRouter(tags=["reports"])

MEDIA = {"pdf": "application/pdf",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "csv": "text/csv"}


class ExportRequest(BaseModel):
    kind: str = Field(default="dashboard",
                      pattern="^(dashboard|consumption|anomalies|savings|forecast)$")
    format: str = Field(default="pdf", pattern="^(pdf|xlsx|csv)$")
    period: str = "month"
    title: str | None = Field(default=None, max_length=200)
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")


@router.get("/reports", summary="Generated reports")
def list_reports(tenant: TenantViewer, limit: int = 50, offset: int = 0):
    return exports.list_reports(tenant, limit=limit, offset=offset)


@router.post("/reports/export", summary="Generate a PDF / XLSX / CSV report")
def export(payload: ExportRequest, tenant: TenantAnalyst):
    row = exports.generate(tenant, kind=payload.kind, fmt=payload.format,
                           period=payload.period, title=payload.title,
                           language=payload.language)
    return {"id": row.id, "kind": row.kind, "format": row.format, "filename": row.filename,
            "size_bytes": row.size_bytes, "created_at": row.created_at,
            "download_url": f"/api/v1/reports/{row.id}/download"}


@router.get("/reports/{report_id}/download", summary="Download a generated report")
def download(report_id: uuid.UUID, tenant: TenantViewer):
    path, row = exports.report_path(tenant, report_id)
    return FileResponse(path, media_type=MEDIA.get(row.format, "application/octet-stream"),
                        filename=row.filename)
