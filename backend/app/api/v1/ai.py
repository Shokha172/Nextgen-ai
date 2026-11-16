from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.deps import TenantAnalyst, TenantViewer
from app.models import AIInsight
from app.services import ai

router = APIRouter(tags=["ai"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000,
                          examples=["Nima uchun kecha iste'mol oshdi?"])
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")
    period: str | None = None


class AnalyzeRequest(BaseModel):
    period: str = "last_30_days"
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")


@router.post("/ai/chat", summary="Ask the grounded AI advisor a question")
def chat(payload: ChatRequest, tenant: TenantViewer):
    """The answer is generated only from numbers the backend computed from the
    organization's own readings; a numeric guard rejects any invented figure."""
    return ai.ask(tenant, question=payload.question, language=payload.language,
                  period=payload.period)


@router.post("/ai/analyze", summary="Structured analysis of the current period")
def analyze(payload: AnalyzeRequest, tenant: TenantViewer):
    return ai.analyze(tenant, period=payload.period, language=payload.language)


@router.get("/ai/insights", summary="Previous advisor exchanges (audit trail)")
def insights(tenant: TenantViewer, limit: int = Query(20, ge=1, le=200)):
    rows = tenant.db.scalars(select(AIInsight).where(AIInsight.organization_id == tenant.org_id)
                             .order_by(AIInsight.created_at.desc()).limit(limit))
    items = [{"id": r.id, "kind": r.kind, "question": r.question, "answer": r.answer,
              "provider": r.provider, "model": r.model, "guard_flags": r.guard_flags,
              "suggestions": r.suggestions, "limitations": r.limitations,
              "latency_ms": r.latency_ms, "created_at": r.created_at} for r in rows]
    total = tenant.db.scalar(select(func.count()).select_from(AIInsight).where(
        AIInsight.organization_id == tenant.org_id)) or 0
    return {"items": items, "total": total}
