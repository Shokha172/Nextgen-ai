import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import os
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_ADMIN_URL"] = "sqlite:///./test_diagnostic.db"
os.environ["DATABASE_URL"] = "sqlite:///./test_diagnostic.db"
os.environ["JWT_SECRET"] = "test-secret-key-that-is-long-enough-1234567890"

from app.core.db import Base, admin_engine, app_engine, SessionLocal
import app.models
from app.models.meter import MeterReading, Meter
from app.models.organization import Organization, OrganizationMember
from app.models.identity import User
from app.core.tenant import Tenant, Identity, Role
import uuid
from datetime import datetime, UTC, timedelta
from app.services.forecast import generate, _daily_series

Base.metadata.create_all(admin_engine)

# Create org and meter
org_id = uuid.uuid4()
user_id = uuid.uuid4()
meter_id = uuid.uuid4()

with admin_engine.begin() as conn:
    conn.execute(User.__table__.insert().values(
        id=user_id, email="test@test.uz", password_hash="x", full_name="Test", locale="uz", is_active=True
    ))
    conn.execute(Organization.__table__.insert().values(
        id=org_id, name="Test Org", slug="test-org", is_demo=False
    ))
    conn.execute(OrganizationMember.__table__.insert().values(
        id=uuid.uuid4(), organization_id=org_id, user_id=user_id, role="owner", status="active"
    ))
    conn.execute(Meter.__table__.insert().values(
        id=meter_id, organization_id=org_id, name="Meter 1", serial_number="M-1", status="active"
    ))

# Insert 60 days of readings
start = (datetime.now(UTC) - timedelta(days=60)).replace(minute=0, second=0, microsecond=0)
rows = []
for i in range(60 * 24):
    ts = start + timedelta(hours=i)
    rows.append({
        "id": uuid.uuid4(),
        "organization_id": org_id,
        "meter_id": meter_id,
        "ts": ts,
        "interval_minutes": 60,
        "consumption_kwh": 10.0,
        "power_kw": 10.0,
        "source": "seed",
        "quality": "ok",
        "created_at": datetime.now(UTC)
    })

with admin_engine.begin() as conn:
    conn.execute(MeterReading.__table__.insert(), rows)

with SessionLocal() as db:
    user = db.get(User, user_id)
    org = db.get(Organization, org_id)
    mem = db.get(OrganizationMember, org.members[0].id)
    ident = Identity(user=user, memberships=[mem])
    t = Tenant(db=db, user=user, org=org, membership=mem, role=Role.OWNER, identity=ident)
    
    # Check count in DB
    cnt = db.execute(MeterReading.__table__.select().where(MeterReading.organization_id == org_id)).fetchall()
    print("Total readings in DB:", len(cnt))
    
    # Test _daily_series
    end_utc = datetime.now(UTC)
    start_utc = end_utc - timedelta(days=90)
    series = _daily_series(t, start=start_utc, end=end_utc)
    print("Series length:", len(series))
    if series:
        print("Sample series items:", list(series.items())[:3])
    
    # Test forecast
    fc = generate(t, horizon_days=30, history_days=90)
    print("Forecast generated successfully! Points:", len(fc["points"]), "Method:", fc["method"])
