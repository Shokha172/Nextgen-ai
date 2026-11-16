# NEXTGEN AI — Enterprise Energy Intelligence Platform

> **"Intelligent Energy Management for a Smarter Future"**  
> *O‘zbekiston Sanoat va Energetika Korxonalari Uchun Rasmiy Raqamli Tahlil Platformasi*

---

## 1. Product Overview

**NEXTGEN AI** is an institutional-grade Energy Intelligence Platform developed for industrial, manufacturing, and commercial enterprises in Uzbekistan and Central Asia. The platform converts raw electricity consumption readings into deterministic business intelligence, detects unusual equipment behavior, forecasts electricity expenditure according to national enterprise tariffs, and identifies evidence-based efficiency opportunities.

### Key Target Sectors
- **Textile & Spinning Mills** (Toshkent, Farg‘ona, Andijon)
- **Heavy & Light Manufacturing Plants** (Chirchiq, Navoiy, Samarqand)
- **Food Processing & Cold Storage Facilities**
- **Commercial Complexes & Business Centers**
- **Distribution Warehouses & Logistics Hubs**

### Non-Negotiable Core Principles
1. **Never promise guaranteed energy savings**.
2. **Never fabricate customer metrics or financial results**.
3. **Never present simulated or synthetic data as real enterprise performance** (all demo environments are explicitly labeled `DEMO`).
4. **100% deterministic calculations**: kWh and kW are strictly segregated; costs are calculated directly against verified enterprise tariffs.
5. **Zero numeric hallucination in AI**: Outputs from generative models (Gemini) are strictly validated by an automated **Numeric Guard** against verified database metrics.

---

## 2. Architecture & Design System

```
                         ┌────────────────────────────────────────┐
                         │   NEXTGEN WEB (Next.js 15, React 19)   │
                         │   - Institutional Blue & White UI      │
                         │   - 6-Language Dynamic Localization    │
                         └───────────────────┬────────────────────┘
                                             │ HTTP / JSON
                                             ▼
                         ┌────────────────────────────────────────┐
                         │       NEXTGEN API (FastAPI, Python)    │
                         │   - Tenant Boundary & RLS Context      │
                         │   - Numeric Hallucination Guard        │
                         └───────┬────────────────────────┬───────┘
                                 │                        │
                 ┌───────────────▼────────┐      ┌────────▼───────────────┐
                 │    ANALYTICS ENGINE    │      │       AI ADVISOR       │
                 │  - Rolling Z-Score     │      │  - Gemini 2.5 Grounded │
                 │  - Robust MAD Baseline │      │  - Rule-Based Fallback │
                 │  - 30-Day Cost Forecast│      │  - Numeric Audit Guard │
                 └───────────────┬────────┘      └────────┬───────────────┘
                                 │                        │
                                 └───────────┬────────────┘
                                             │ SQLAlchemy ORM
                                             ▼
                         ┌────────────────────────────────────────┐
                         │      DATABASE (PostgreSQL / SQLite)    │
                         │   - Multi-tenant Row Level Security    │
                         │   - Asia/Tashkent (UTC+5) Local Day    │
                         └───────────────────┬────────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
         ┌───────────────────────────┐               ┌───────────────────────────┐
         │     NEXTGEN DEMO BOT      │               │   NEXTGEN OFFICIAL BOT    │
         │ - Isolated Synthetic Data │               │ - 6-Digit One-Time Link   │
         │ - Read-Only Safe Sandbox  │               │ - Role-Based Permissions  │
         └───────────────────────────┘               └───────────────────────────┘
```

### Official Institutional Palette
- **Primary Blue**: `#155EEF`
- **Deep Blue**: `#123B72`
- **Background**: `#F5F8FC`
- **Surface Card**: `#FFFFFF`
- **Main Text (Ink)**: `#172B4D`
- **Secondary Text (Muted)**: `#667085`
- **Border Line**: `#E4EAF2`
- **Success**: `#12A66A` | **Warning**: `#E9A23B` | **Danger**: `#D92D20`

### Complete 6-Language Support
1. **O‘zbekcha (`uz`)** — Default
2. **English (`en`)** — International Fallback
3. **Русский (`ru`)**
4. **Қазақша (`kk`)**
5. **Türkçe (`tr`)**
6. **Кыргызча (`ky`)**

---

## 3. Quick Start & Local Setup

### Prerequisites
- **Node.js** 20+ (with npm)
- **Python** 3.11+ (Python 3.14 compatible)
- **Git**

### Step 1: Clone and Set Up Python Virtual Environment
```bash
# In the project root (d:\Nextgen)
uv venv .venv
# Activate on Windows:
.\.venv\Scripts\activate
# Activate on Linux/macOS:
source .venv/bin/activate

# Install backend dependencies
uv pip install -r backend/requirements.txt
# Install bot dependencies
uv pip install -r bots/requirements.txt
```

### Step 2: Seed Synthetic Demo Data
```bash
# Seed 120 days of realistic industrial data for 6 meters into nextgen.db
python backend/scripts/seed_demo.py --reset
```
*Demo Credentials:*
- **Email**: `demo@nextgen.uz`
- **Password**: `NextGen-Demo-2026!`

### Step 3: Run the FastAPI Backend Server
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation will be available at:
- **Interactive Swagger UI**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/health`

### Step 4: Run the Next.js Frontend
```bash
cd frontend
# Build for production:
npm run build
# Start production server:
npm run start
# Or start in development mode:
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 4. Test Suite Execution

The repository contains 106 automated tests covering authentication, deterministic analytics, explainable anomaly algorithms, multi-tenant isolation, 10-stage data import, Gemini AI grounding, verified savings reports, and dual Telegram bots.

To execute the test suite:
```bash
python -m pytest backend/tests/ -v
```
**Results: 105 passed, 1 skipped (PostgreSQL RLS on SQLite) in ~75 seconds.**

---

## 5. Dual Telegram Bots

NEXTGEN AI operates two distinct bot runtimes to ensure strict isolation:

| Bot Mode | Target Audience | Data Access | File Uploads |
| :--- | :--- | :--- | :--- |
| **Demo Bot** | Prospective clients, public demos | Confined strictly to synthetic `is_demo=True` data | Disabled |
| **Official Bot** | Authenticated enterprise clients | Authorized tenant accounts via 6-digit one-time code | Enabled (CSV/XLSX) |

### Running the Bots
```bash
# To run the Demo Bot:
TELEGRAM_DEMO_BOT_TOKEN="your_token" BOT_SERVICE_KEY_DEMO="demo-key" python -m bots.run demo

# To run the Official Enterprise Bot:
TELEGRAM_OFFICIAL_BOT_TOKEN="your_token" BOT_SERVICE_KEY_OFFICIAL="official-key" python -m bots.run official
```

---

## 6. Deployment Guide

### A. Frontend Deployment (Vercel)
The `frontend/` directory is an independent Next.js application designed for zero-configuration deployment to Vercel:
1. Link the repository to your Vercel project with **Root Directory** set to `frontend`.
2. Configure Environment Variables in Vercel:
   - `NEXT_PUBLIC_API_URL`: URL of your deployed FastAPI backend (e.g., `https://api.nextgen.uz`).
3. Deploy. Vercel automatically runs `next build` and serves static assets via edge CDN.

### B. Backend Deployment (Docker / Linux VPS)
1. Set up a PostgreSQL 17 instance with Row Level Security enabled.
2. Run database migrations:
   ```bash
   alembic -c backend/alembic.ini upgrade head
   ```
3. Set production environment variables:
   ```env
   ENVIRONMENT=production
   DATABASE_URL=postgresql+psycopg://nextgen_app:secret@db:5432/nextgen
   DATABASE_ADMIN_URL=postgresql+psycopg://postgres:secret@db:5432/nextgen
   JWT_SECRET=your-minimum-64-char-secure-random-secret
   GEMINI_API_KEY=your-google-gemini-api-key
   BOT_SERVICE_KEY_OFFICIAL=your-secure-internal-key
   ```
4. Run via Gunicorn / Uvicorn worker:
   ```bash
   gunicorn -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000 backend.app.main:app
   ```

---

## 7. 180-Person Demonstration Walkthrough Script

This script provides an exact step-by-step walkthrough for presenting NEXTGEN AI to enterprise executives, institutional delegates, and engineers.

### Scene 1: The Core Problem in Uzbekistan Industry (2 mins)
- **Speaker**: "O‘zbekiston sanoat korxonalari har oy yuzlab million so‘mlik elektr energiyasini iste’mol qiladi. Ko‘p korxonalarda ASKUE yoki zamonaviy hisoblagichlar o‘rnatilgan, lekin ma’lumotlar Excel jadvallarida qolib ketadi. Bosh energetik va rahbarlar ortiqcha yuklama qachon va qaysi uskunada yuz berganini bilishmaydi."
- **Visual**: Open `http://localhost:3000` (Public Enterprise Landing Page). Highlight the official institutional design, standard compliance badge, and transparent ethical principles.

### Scene 2: Interactive DEMO Platform (3 mins)
- **Speaker**: "Biz darhol tizimning sintetik DEMO muhitini ochamiz. Bu yerda Chirchiqdagi to‘qimachilik va mexanika korxonasining 120 kunlik 6 ta hisoblagich ma’lumotlari yuklangan."
- **Action**: Click **"DEMO Sinov"** or sign in with `demo@nextgen.uz` / `NextGen-Demo-2026!`.
- **Key Highlights**:
  - Show the prominent yellow **DEMO** badge explaining that this is an isolated sandbox.
  - Review Executive KPIs: Total Consumption ($\text{kWh}$), Peak Load ($\text{kW}$), Estimated Cost ($\text{UZS}$ at 450 UZS/kWh).
  - Demonstrate the 6-language switcher (`UZ` -> `EN` -> `RU` -> `KK` -> `TR` -> `KY`) in the top navigation bar.

### Scene 3: Explainable Anomaly Detection (2 mins)
- **Speaker**: "NEXTGEN AI shunchaki chiroyli grafik emas. Bizning algoritmik tahlil dvigatelimiz Rolling Z-score va Robust MAD usuli orqali 14 ta anomaliyani aniqladi."
- **Action**: Navigate to `/anomalies`.
- **Key Highlights**:
  - Show a specific spike on "Kompressor stansiyasi".
  - Explain the mathematical rationale: *Normal baseline: 110 kWh; Detected surge: 285 kWh; Z-score: 3.42*.
  - Click **"Acknowledge"** to demonstrate operational workflow for plant engineers.

### Scene 4: 10-Stage Data Import Wizard (2 mins)
- **Speaker**: "Korxonalarning eng katta muammosi — har xil formatdagi Excel fayllar. Biz 10 bosqichli import dvigatelini yaratdik."
- **Action**: Navigate to `/imports`.
- **Key Highlights**:
  - Download the official template (`CSV` / `XLSX`).
  - Demonstrate column mapping in Uzbek, Russian, and English.
  - Explain how the engine automatically isolates duplicates and calculates differential kWh for cumulative registers without silent data corruption.

### Scene 5: Grounded AI Advisor with Numeric Guard (2 mins)
- **Speaker**: "Bosh energetik tizimdan savol so‘raydi: 'Kecha nima uchun iste’mol 15% ga oshdi?'"
- **Action**: Open the AI Advisor tab.
- **Key Highlights**:
  - Show how Gemini generates an insightful executive summary.
  - Emphasize the **Numeric Hallucination Guard**: *Every number cited in the text is mathematically verified against the database before display*.

### Scene 6: Telegram Bot & Mobile Management (1 min)
- **Speaker**: "Energetik va direktor doim kompyuter oldida bo‘lmaydi. Biz Telegram orqali 6 xonali xavfsiz bir martalik kod bilan bog‘lanadigan 2 ta botni taqdim etamiz."
- **Action**: Show `/settings` Telegram linking panel and mobile responsive layout.
- **Closing**: "NEXTGEN AI — bu O‘zbekiston sanoati uchun amaliy, ishonchli va xavfsiz energetika intellekti."
