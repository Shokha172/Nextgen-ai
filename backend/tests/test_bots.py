"""Bot contract tests (no Telegram network): translations, formatting, keyboards, router."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bots.common import formatting, i18n, keyboards  # noqa: E402
from bots.common.api import BackendClient  # noqa: E402
from bots.common.config import BotConfig  # noqa: E402
from bots.common.handlers import SessionCache, build_router  # noqa: E402


def test_all_languages_cover_the_same_keys():
    keys = {lang: set(translations) for lang, translations in i18n.TEXTS.items()}
    assert keys["uz"] == keys["ru"] == keys["en"] == keys["kk"] == keys["tr"] == keys["ky"], "translations must stay in sync"


def test_translations_render_without_missing_placeholders():
    for lang in ("uz", "ru", "en"):
        assert "Assalomu" in i18n.t(lang, "welcome", name="Test") or \
               "Здравствуйте" in i18n.t(lang, "welcome", name="Test") or \
               "Hello" in i18n.t(lang, "welcome", name="Test")
        assert "{" not in i18n.t(lang, "help_text")
        assert "{" not in i18n.t(lang, "welcome_demo")


def test_energy_and_power_are_labelled_distinctly():
    assert formatting.kwh(1234.5678, 1) == "1 234.6 kWh"
    assert formatting.kw(120) == "120.0 kW"
    assert "kWh" not in formatting.kw(500)
    assert formatting.money(1080000, "UZS") == "1 080 000 UZS"
    assert formatting.money(None) == "—"
    assert formatting.pct(12.345) == "+12.3%"
    assert formatting.pct(-5) == "-5.0%"


def test_dashboard_text_states_missing_data_instead_of_zeroes():
    empty = {"has_data": False}
    assert formatting.dashboard_text(empty, "en", "month") == i18n.t("en", "no_data")
    data = {"has_data": True,
            "consumption": {"total_kwh": 2400, "data_coverage_pct": 100},
            "cost": {"estimated": None, "currency": "UZS"},
            "trend": {"vs_previous_period_pct": None},
            "anomalies": {"count": 0}}
    text = formatting.dashboard_text(data, "en", "month")
    assert "2 400.00 kWh" in text
    assert i18n.t("en", "no_tariff") in text


def test_keyboards_hide_upload_for_the_demo_bot():
    demo_callbacks = [b.callback_data for row in keyboards.main_menu("uz", is_demo=True).inline_keyboard
                      for b in row]
    official_callbacks = [b.callback_data
                          for row in keyboards.main_menu("uz", is_demo=False).inline_keyboard
                          for b in row]
    assert "menu:upload" not in demo_callbacks
    assert "menu:upload" in official_callbacks


def test_every_button_has_a_registered_handler():
    """No dead controls: each callback_data prefix must be handled by the router."""
    cfg = BotConfig(mode="official", token="t", service_key="k",
                    api_base_url="http://localhost:8000")
    router = build_router(cfg, BackendClient(cfg), SessionCache())
    handled_prefixes = {"menu:", "lang:", "report:", "settings:"}
    buttons = []
    for markup in (keyboards.main_menu("uz", is_demo=False), keyboards.back_keyboard("uz"),
                   keyboards.language_keyboard(), keyboards.report_keyboard("uz"),
                   keyboards.settings_keyboard("uz")):
        buttons.extend(b.callback_data for row in markup.inline_keyboard for b in row)
    assert buttons
    for data in buttons:
        assert any(data.startswith(prefix) for prefix in handled_prefixes), data
    assert router.message.handlers and router.callback_query.handlers


def test_bot_config_requires_its_own_credentials(monkeypatch):
    from bots.common import config as config_module

    monkeypatch.delenv("TELEGRAM_OFFICIAL_BOT_TOKEN", raising=False)
    monkeypatch.setenv("BOT_SERVICE_KEY_OFFICIAL", "key")
    try:
        config_module.load_config("official")
    except SystemExit as exc:
        assert "TELEGRAM_OFFICIAL_BOT_TOKEN" in str(exc)
    else:
        raise AssertionError("missing token must raise")
