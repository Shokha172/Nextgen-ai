#!/usr/bin/env python3
"""Interactive Terminal Telegram Bot Simulator for NEXTGEN AI.

Allows testing all Telegram bot commands and viewing live formatted bot responses
directly in the terminal against the local backend server without requiring
a live Telegram BotFather token.

Usage:
    python -m bots.cli_interactive [demo|official]
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.common.api import BackendClient, BotAPIError
from bots.common.config import BotConfig
from bots.common.formatting import dashboard_text, kwh, money, num
from bots.common.i18n import LANGUAGES, t

USER_ID = 998901234567


async def run_simulator(mode: str = "demo") -> None:
    api_url = os.getenv("BOT_API_BASE_URL", "http://127.0.0.1:8000")
    key = "demo-service-key-2026" if mode == "demo" else "official-service-key-2026"
    cfg = BotConfig(mode=mode, token="simulated-token", service_key=key, api_base_url=api_url)
    api = BackendClient(cfg)

    print("=" * 60)
    print(f"🤖 NEXTGEN AI — TELEGRAM BOT SIMULATOR ({mode.upper()} MODE)")
    print(f"📡 Backend URL: {api_url}")
    print("=" * 60)

    try:
        if mode == "demo":
            sess = await api.demo_session(USER_ID, "DemoUser")
            org_name = sess.get("organization_name", "Namuna Sanoat MChJ (DEMO)")
            role = sess.get("role", "viewer")
            lang = sess.get("language", "uz")
        else:
            print("Official bot requires linking to an active organization.")
            code = input("Enter 6-digit linking code from Web /settings: ").strip()
            if not code:
                print("No code provided, defaulting to demo mode.")
                return
            sess = await api.link(code, USER_ID, "OfficialUser")
            org_name = sess.get("organization_name", "Enterprise")
            role = sess.get("role", "analyst")
            lang = sess.get("language", "uz")
    except BotAPIError as e:
        print(f"❌ Connection error: {e.message}")
        await api.close()
        return

    print(f"✅ Connected to: {org_name} (Role: {role}, Lang: {lang})")
    print("\nAvailable commands:")
    print("  /start         — Welcome message & main menu")
    print("  /dashboard     — Executive consumption & cost dashboard")
    print("  /anomalies     — Recent detected anomalies with explanations")
    print("  /forecast      — 30-day demand and expense forecast")
    print("  /analysis      — Ask grounded AI energy question")
    print("  /lang <code>   — Change language (uz, en, ru, kk, tr, ky)")
    print("  /report        — Generate and download report")
    print("  exit / quit    — Exit simulator\n")

    while True:
        try:
            line = input(f"[{org_name} | {lang}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            break

        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "/start":
                welcome = t(lang, "welcome", name="Foydalanuvchi")
                if mode == "demo":
                    welcome += t(lang, "welcome_demo")
                print("\n" + welcome)
                print("\n" + t(lang, "menu"))
                print("1. 📊 " + t(lang, "dashboard"))
                print("2. 🧠 " + t(lang, "analysis"))
                print("3. ⚠️ " + t(lang, "anomalies"))
                print("4. 📈 " + t(lang, "forecast"))
                print("5. 📄 " + t(lang, "report"))
                print("6. ⚙️ " + t(lang, "settings"))
                print()

            elif cmd in ("/dashboard", "1"):
                data = await api.dashboard(USER_ID, "month")
                formatted = dashboard_text(data, lang, label=t(lang, "month"))
                print("\n" + formatted + "\n")

            elif cmd in ("/anomalies", "3"):
                data = await api.anomalies(USER_ID)
                items = data.get("items", [])
                if not items:
                    print("\n" + t(lang, "no_anomalies") + "\n")
                else:
                    print(f"\n⚠️ {t(lang, 'anomalies_title', count=len(items))}")
                    for anom in items[:5]:
                        sev = anom.get("severity", "info").upper()
                        ts = anom.get("ts", "")[:16].replace("T", " ")
                        kwh_val = anom.get("actual_kwh", 0)
                        base_val = anom.get("expected_kwh", 0)
                        method = anom.get("method", "z-score")
                        expl = anom.get("explanation", {}).get("summary", "")
                        print(f"  • [{sev}] {ts} — {kwh_val} kWh (Oddiy: {base_val} kWh) | Usul: {method}")
                        if expl:
                            print(f"    Sabab: {expl}")
                    print()

            elif cmd in ("/forecast", "4"):
                data = await api.forecast(USER_ID)
                f_items = data.get("forecast", [])
                if not f_items:
                    print("\n" + t(lang, "forecast_na") + "\n")
                else:
                    total_kwh = sum(item.get("forecast_kwh", 0) for item in f_items)
                    cost = data.get("cost_uzs")
                    print(f"\n📈 {t(lang, 'forecast_title', days=len(f_items))}")
                    print(f"  Kutilayotgan iste'mol: {num(total_kwh, 1)} kWh")
                    if cost:
                        print(f"  Kutilayotgan xarajat: {money(cost, 'UZS')}")
                    print(f"  Model aniqligi (MAPE): {data.get('mape', '—')}%")
                    print()

            elif cmd in ("/analysis", "2"):
                question = arg or "Ushbu oyda eng katta energiya sarflagan uskunalar va anomaliyalarni tahlil qilib bering."
                print(f"\n🧠 AI savol: \"{question}\"")
                print("AI tahlil qilinmoqda...")
                ans = await api.chat(USER_ID, question)
                print("\n" + ans.get("answer", "Javob yo'q") + "\n")

            elif cmd in ("/lang", "/language"):
                if arg in LANGUAGES:
                    await api.set_language(USER_ID, arg)
                    lang = arg
                    print(f"\n✅ {t(lang, 'lang_set')}\n")
                else:
                    print(f"\nMavjud tillar: {', '.join(LANGUAGES.keys())}\nMisol: /lang ru yoki /lang en\n")

            elif cmd in ("/report", "5"):
                rep = await api.create_report(USER_ID, kind="dashboard", fmt="pdf")
                print(f"\n📄 {t(lang, 'report_done', filename=rep.get('filename', 'report.pdf'))}\n")

            elif cmd == "/help":
                print("\n" + t(lang, "help_text") + "\n")

            else:
                print(f"Noma'lum buyruq: {cmd}. /help deb yozing.")

        except BotAPIError as exc:
            print(f"❌ Xatolik: {exc.message}")
        except Exception as exc:
            print(f"❌ Kutilmagan xatolik: {exc}")

    await api.close()
    print("Simulator tugatildi.")


if __name__ == "__main__":
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "demo"
    asyncio.run(run_simulator(mode_arg))
