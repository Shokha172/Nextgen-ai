#!/usr/bin/env python3
"""Seed the DEMO organization with synthetic industrial data.

    python scripts/seed_demo.py            # create if missing
    python scripts/seed_demo.py --reset    # delete and recreate

Everything created here is labelled DEMO in the database (`organizations.is_demo`)
and in the UI. It is never mixed with a production tenant.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import AdminSessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (Meter, MeterReading, Organization, OrganizationMember, Tariff,  # noqa: E402
                        User)
from app.models.enums import Industry, MeterType, ReadingSource, Role  # noqa: E402
from app.services import forecast  # noqa: E402
from app.services.synthetic import DEFAULT_METERS, generate_readings  # noqa: E402

DEMO_SLUG = "demo-namuna-sanoat"
DEMO_EMAIL = "demo@nextgen.uz"
DEMO_PASSWORD = os.getenv("DEMO_SEED_PASSWORD", "NextGen-Demo-2026!")
EXAMPLE_TARIFF_UZS_PER_KWH = Decimal("450.0000")   # example configuration, not a market fact


def reset_demo_org() -> None:
    with AdminSessionLocal() as db:
        org = db.scalar(select(Organization).where(Organization.slug == DEMO_SLUG))
        if org:
            db.delete(org)          # cascades to meters, readings, members, etc.
            db.commit()
            print(f"[seed] removed existing demo organization {org.id}")
        demo_user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if demo_user:
            db.delete(demo_user)
            db.commit()


def seed(days: int = 120) -> dict:
    from app.core.db import admin_engine, Base
    Base.metadata.create_all(admin_engine)
    with AdminSessionLocal() as db:
        existing = db.scalar(select(Organization).where(Organization.slug == DEMO_SLUG))
        if existing:
            print(f"[seed] demo organization already exists: {existing.id} "
                  f"(use --reset to rebuild)")
            return {"organization_id": str(existing.id), "created": False}

        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD),
                    full_name="Demo Owner", locale="uz", is_demo=True, email_verified=True)
        db.add(user)
        db.flush()

        org = Organization(
            name="Namuna Sanoat MChJ (DEMO)", slug=DEMO_SLUG, industry=Industry.MANUFACTURING.value,
            region="Toshkent viloyati", city="Chirchiq", address="Sanoat zonasi, 12-uy",
            timezone=settings.DISPLAY_TZ, currency="UZS", is_demo=True, created_by=user.id,
            settings={"demo": True,
                      "disclaimer": "Barcha ma'lumotlar sintetik (DEMO). Haqiqiy korxona "
                                    "ko'rsatkichlari emas."})
        db.add(org)
        db.flush()

        db.add(OrganizationMember(organization_id=org.id, user_id=user.id,
                                  role=Role.OWNER.value, status="active",
                                  accepted_at=datetime.now(UTC), invited_email=user.email,
                                  title="Energiya menejeri"))

        meter_ids = {}
        for spec in DEFAULT_METERS:
            m = Meter(organization_id=org.id, name=spec.name, serial_number=spec.serial,
                      department=spec.department, meter_type=MeterType.INTERVAL.value,
                      interval_minutes=60,
                      max_power_kw=Decimal(str(spec.max_power_kw)) if spec.max_power_kw else None,
                      location=f"{spec.department} bo'limi", created_by=user.id,
                      notes="DEMO hisoblagich")
            db.add(m)
            db.flush()
            meter_ids[spec.serial] = m.id

        db.add(Tariff(organization_id=org.id, name="DEMO tarif (namuna)", currency="UZS",
                      price_per_kwh=EXAMPLE_TARIFF_UZS_PER_KWH,
                      valid_from=(datetime.now(UTC).date().replace(month=1, day=1)),
                      is_default=True,
                      notes="Namuna uchun kiritilgan tarif. Haqiqiy bozor narxi emas."))

        print(f"[seed] generating {days} days x {len(DEFAULT_METERS)} meters of synthetic readings…")
        rows = generate_readings(DEFAULT_METERS, meter_ids=meter_ids, org_id=org.id, days=days)
        cleaned = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
        for i in range(0, len(cleaned), 5000):
            db.add_all([MeterReading(**r) for r in cleaned[i:i + 5000]])
            db.flush()
        db.commit()
        print(f"[seed] inserted {len(cleaned)} readings")

        org_id, user_id = org.id, user.id

    # anomaly detection + forecast use the tenant-bound path, like the real product
    from app.core.tenant import Tenant, bind
    from app.core.timeutil import period_bounds
    from app.services import anomalies
    with AdminSessionLocal() as db:
        org = db.get(Organization, org_id)
        member = db.scalar(select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id))
        db.info["tenant"] = {"org_id": str(org_id), "user_id": str(user_id)}
        bind(db, org_id=org_id, user_id=user_id)
        tenant = Tenant(db=db, user=db.get(User, user_id), org=org, membership=member,
                        role=Role.OWNER, identity=None)  # type: ignore[arg-type]
        start, end = period_bounds("last_30_days")
        result = anomalies.run_detection(tenant, start=start, end=end, persist=True)
        print(f"[seed] anomaly detection: {result['count']} anomalies "
              f"({result['severity_counts']})")
        try:
            fc = forecast.generate(tenant, horizon_days=30)
            print(f"[seed] forecast: {fc['method']} / confidence={fc['confidence']} / "
                  f"MAPE={fc['accuracy_mape']} / total={fc['total_kwh']} kWh")
        except Exception as exc:
            print(f"[seed] forecast skipped: {exc}")

    print("\n[seed] DEMO credentials")
    print(f"   email:    {DEMO_EMAIL}")
    print(f"   password: {DEMO_PASSWORD}")
    print("   NOTE: all data is synthetic and labelled DEMO.")
    return {"organization_id": str(org_id), "created": True, "readings": len(cleaned)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--days", type=int, default=120)
    args = ap.parse_args()
    if args.reset:
        reset_demo_org()
    seed(days=args.days)
