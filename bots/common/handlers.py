"""Shared aiogram handlers for both bots.

The behaviour difference between demo and official lives in *policy* (the demo bot
opens a session on the DEMO organization automatically and cannot upload files),
not in duplicated handler code.
"""
from __future__ import annotations

import io

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bots.common.api import BackendClient, BotAPIError
from bots.common.config import BotConfig
from bots.common.formatting import dashboard_text, kwh, money, num, pct
from bots.common.i18n import t
from bots.common.keyboards import (back_keyboard, language_keyboard, main_menu,
                                   report_keyboard, settings_keyboard)

PERIODS = {"today": "today", "week": "week", "month": "month", "year": "year"}


class UploadStates(StatesGroup):
    waiting_file = State()


class AskStates(StatesGroup):
    waiting_question = State()


def _lang(ctx_lang: str | None) -> str:
    return ctx_lang if ctx_lang in ("uz", "ru", "en") else "uz"


class SessionCache:
    """Per-process cache of linked-account context (language, org, role)."""

    def __init__(self) -> None:
        self._data: dict[int, dict] = {}

    def get(self, uid: int) -> dict | None:
        return self._data.get(uid)

    def set(self, uid: int, value: dict) -> None:
        self._data[uid] = value

    def language(self, uid: int) -> str:
        return _lang((self._data.get(uid) or {}).get("language"))

    def drop(self, uid: int) -> None:
        self._data.pop(uid, None)


def build_router(cfg: BotConfig, api: BackendClient, cache: SessionCache) -> Router:
    router = Router(name=f"nextgen-{cfg.mode}")

    async def _ensure_session(message_or_cb) -> dict | None:
        uid = message_or_cb.from_user.id
        cached = cache.get(uid)
        if cached:
            return cached
        try:
            me = await api.me(uid)
            me["language"] = _lang(me.get("language"))
            cache.set(uid, me)
            return me
        except BotAPIError:
            return None

    async def _send(message: Message, text: str, **kwargs) -> None:
        await message.answer(text, **kwargs)

    # ---------------------------------------------------------------- /start
    @router.message(Command("start"))
    async def start(message: Message, command: CommandObject, bot: Bot) -> None:
        uid = message.from_user.id
        username = message.from_user.username
        name = message.from_user.first_name or "do'stim"
        code = (command.args or "").strip()

        if cfg.is_demo:
            try:
                session = await api.demo_session(uid, username)
            except BotAPIError as exc:
                await _send(message, t("uz", "error") + f"\n\n<i>{exc.message}</i>")
                return
            cache.set(uid, {**session, "language": _lang(session.get("language"))})
            lang = cache.language(uid)
            await _send(message, t(lang, "welcome", name=name) + t(lang, "welcome_demo")
                        + f"\n\n<b>{session['organization_name']}</b>",
                        reply_markup=main_menu(lang, is_demo=True))
            return

        # official bot
        if code:
            try:
                session = await api.link(uid, username, code)
            except BotAPIError as exc:
                if exc.code == "link_code_invalid":
                    await _send(message, t("uz", "invalid_code"))
                elif exc.code == "telegram_already_linked":
                    await _send(message, t("uz", "already"))
                else:
                    await _send(message, t("uz", "error") + f"\n<i>{exc.message}</i>")
                return
            cache.set(uid, {**session, "language": _lang(session.get("language"))})
            lang = cache.language(uid)
            await _send(message, t(lang, "linked", org=session["organization_name"],
                                   role=session.get("role") or "—"),
                        reply_markup=main_menu(lang, is_demo=False))
            return

        me = await _ensure_session(message)
        if me:
            lang = _lang(me.get("language"))
            await _send(message, t(lang, "welcome", name=name) + t(lang, "menu"),
                        reply_markup=main_menu(lang, is_demo=False))
        else:
            await _send(message, t("uz", "welcome", name=name) + t("uz", "welcome_official"))

    # ------------------------------------------------------------- /dashboard
    @router.message(Command("dashboard"))
    async def dashboard_cmd(message: Message) -> None:
        await _dashboard(message, message.from_user.id)

    async def _dashboard(target: Message, uid: int, period: str = "month") -> None:
        me = cache.get(uid)
        if me is None:
            try:
                me = await api.me(uid)
                me["language"] = _lang(me.get("language"))
                cache.set(uid, me)
            except BotAPIError:
                await target.answer(t("uz", "not_linked"))
                return
        lang = cache.language(uid)
        try:
            data = await api.dashboard(uid, period)
        except BotAPIError as exc:
            await target.answer(f"{t(lang, 'error')}\n<i>{exc.message}</i>")
            return
        text = dashboard_text(data, lang, period)
        header = t(lang, "dashboard_title", org=me.get("organization", "—"), period=period)
        await target.answer(f"{header}\n\n{text}",
                            reply_markup=back_keyboard(lang))

    # -------------------------------------------------------------- /analysis
    @router.message(Command("analysis"))
    async def analysis_cmd(message: Message) -> None:
        await _analysis(message, message.from_user.id)

    async def _analysis(target: Message, uid: int) -> None:
        lang = cache.language(uid)
        waiting = await target.answer(t(lang, "analysis_running"))
        try:
            result = await api.chat(uid, "Give a structured energy analysis of the current period.",
                                    lang)
        except BotAPIError as exc:
            await waiting.edit_text(f"{t(lang, 'error')}\n<i>{exc.message}</i>")
            return
        body = [t(lang, "analysis_title"), "", result["answer"]]
        if result.get("suggestions"):
            body.append("")
            for s in result["suggestions"][:3]:
                body.append("• " + s["text"])
        if result["grounding"]["passed"] is False:
            body.append("")
            body.append("⚠️ <i>AI javobi raqamlar bilan mos kelmadi va bekor qilindi; "
                        "deterministik javob ko'rsatildi.</i>")
        await waiting.edit_text("\n".join(body)[:4000], reply_markup=back_keyboard(lang))

    # ------------------------------------------------------------- /anomalies
    @router.message(Command("alerts", "anomalies"))
    async def anomalies_cmd(message: Message) -> None:
        await _anomalies(message, message.from_user.id)

    async def _anomalies(target: Message, uid: int) -> None:
        lang = cache.language(uid)
        try:
            data = await api.anomalies(uid, limit=5)
        except BotAPIError as exc:
            await target.answer(f"{t(lang, 'error')}\n<i>{exc.message}</i>")
            return
        if not data["items"]:
            await target.answer(t(lang, "no_anomalies"), reply_markup=back_keyboard(lang))
            return
        lines = [t(lang, "anomalies_title", count=data["total"]), ""]
        for item in data["items"]:
            explanation = (item.get("explanations") or {}).get(lang) or item.get("explanation", "")
            lines.append(f"• <b>{item['severity'].upper()}</b> — {kwh(item['observed_kwh'], 1)} "
                         f"(kutilgan {kwh(item['expected_kwh'], 1)}, {pct(item['deviation_pct'])})")
            lines.append(f"  <i>{explanation[:220]}</i>")
        await target.answer("\n".join(lines)[:4000], reply_markup=back_keyboard(lang))

    # -------------------------------------------------------------- /forecast
    @router.message(Command("forecast"))
    async def forecast_cmd(message: Message) -> None:
        await _forecast(message, message.from_user.id)

    async def _forecast(target: Message, uid: int) -> None:
        lang = cache.language(uid)
        try:
            data = await api.forecast(uid, 30)
        except BotAPIError as exc:
            if exc.code == "insufficient_history":
                await target.answer(t(lang, "forecast_na"), reply_markup=back_keyboard(lang))
                return
            await target.answer(f"{t(lang, 'error')}\n<i>{exc.message}</i>")
            return
        lines = [t(lang, "forecast_title", days=data["horizon_days"]), "",
                 f"{t(lang, 'kwh')}: <b>{kwh(data['total_kwh'], 0)}</b>",
                 f"{t(lang, 'cost')}: "
                 + (money(data["total_cost"], data["currency"])
                    if data.get("total_cost") is not None else t(lang, "no_tariff")),
                 f"Ishonch: {data['confidence']}"
                 + (f" · MAPE {num(data['accuracy_mape'], 1)}%" if data.get("accuracy_mape") else ""),
                 f"Usul: {data['method']}"]
        if data.get("limitations"):
            lines.append("")
            lines.append("<i>Cheklovlar: " + data["limitations"][0][:200] + "</i>")
        await target.answer("\n".join(lines)[:4000], reply_markup=back_keyboard(lang))

    # ---------------------------------------------------------------- /report
    @router.message(Command("report"))
    async def report_cmd(message: Message) -> None:
        lang = cache.language(message.from_user.id)
        await message.answer(t(lang, "report_choose"), reply_markup=report_keyboard(lang))

    # ---------------------------------------------------------------- /upload
    @router.message(Command("upload"))
    async def upload_cmd(message: Message, state: FSMContext) -> None:
        lang = cache.language(message.from_user.id)
        if cfg.is_demo:
            await message.answer(t(lang, "upload_demo"), reply_markup=back_keyboard(lang))
            return
        await state.set_state(UploadStates.waiting_file)
        await message.answer(t(lang, "upload_prompt"), reply_markup=back_keyboard(lang))

    @router.message(UploadStates.waiting_file, F.document)
    async def upload_document(message: Message, bot: Bot, state: FSMContext) -> None:
        uid = message.from_user.id
        lang = cache.language(uid)
        document = message.document
        filename = document.file_name or "upload.csv"
        if not filename.lower().endswith((".csv", ".xlsx", ".txt", ".tsv")):
            await message.answer(t(lang, "upload_failed", error="faqat CSV/XLSX"))
            return
        if document.file_size and document.file_size > 10 * 1024 * 1024:
            await message.answer(t(lang, "upload_failed", error="fayl 10 MB dan katta"))
            return
        buffer = io.BytesIO()
        await bot.download(document, destination=buffer)
        try:
            result = await api.upload(uid, filename, buffer.getvalue())
        except BotAPIError as exc:
            await message.answer(t(lang, "upload_failed", error=exc.message))
            return
        await state.clear()
        await message.answer(t(lang, "upload_done", inserted=result["inserted"],
                                skipped=result["skipped_duplicates"]),
                             reply_markup=back_keyboard(lang))

    # -------------------------------------------------------------- /settings
    @router.message(Command("settings"))
    async def settings_cmd(message: Message) -> None:
        await _settings(message, message.from_user.id)

    async def _settings(target: Message, uid: int) -> None:
        me = cache.get(uid)
        if me is None:
            await target.answer(t("uz", "not_linked"))
            return
        lang = cache.language(uid)
        await target.answer(t(lang, "settings_title", org=me.get("organization", "—"),
                              role=me.get("role", "—"), lang=lang),
                            reply_markup=settings_keyboard(lang))

    # ------------------------------------------------------------------ /help
    @router.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        lang = cache.language(message.from_user.id)
        await message.answer(t(lang, "help_text"), reply_markup=back_keyboard(lang))

    # ------------------------------------------------- free-text AI questions
    @router.message(F.text & ~F.text.startswith("/"))
    async def free_text(message: Message, state: FSMContext) -> None:
        uid = message.from_user.id
        lang = cache.language(uid)
        question = (message.text or "").strip()
        if not question:
            return
        waiting = await message.answer(t(lang, "analysis_running"))
        try:
            result = await api.chat(uid, question[:900], lang)
        except BotAPIError as exc:
            await waiting.edit_text(f"{t(lang, 'error')}\n<i>{exc.message}</i>")
            return
        text = result["answer"][:3600]
        if result.get("suggestions"):
            text += "\n\n" + "\n".join("• " + s["text"] for s in result["suggestions"][:3])
        await waiting.edit_text(text, reply_markup=back_keyboard(lang))

    # -------------------------------------------------------------- callbacks
    @router.callback_query(F.data == "menu:main")
    async def cb_main(cb: CallbackQuery) -> None:
        lang = cache.language(cb.from_user.id)
        await cb.message.edit_text(t(lang, "menu"),
                                   reply_markup=main_menu(lang, is_demo=cfg.is_demo))
        await cb.answer()

    @router.callback_query(F.data == "menu:dashboard")
    async def cb_dashboard(cb: CallbackQuery) -> None:
        await cb.answer()
        await _dashboard(cb.message, cb.from_user.id)

    @router.callback_query(F.data == "menu:analysis")
    async def cb_analysis(cb: CallbackQuery) -> None:
        await cb.answer()
        await _analysis(cb.message, cb.from_user.id)

    @router.callback_query(F.data == "menu:anomalies")
    async def cb_anomalies(cb: CallbackQuery) -> None:
        await cb.answer()
        await _anomalies(cb.message, cb.from_user.id)

    @router.callback_query(F.data == "menu:forecast")
    async def cb_forecast(cb: CallbackQuery) -> None:
        await cb.answer()
        await _forecast(cb.message, cb.from_user.id)

    @router.callback_query(F.data == "menu:report")
    async def cb_report(cb: CallbackQuery) -> None:
        lang = cache.language(cb.from_user.id)
        await cb.message.edit_text(t(lang, "report_choose"), reply_markup=report_keyboard(lang))
        await cb.answer()

    @router.callback_query(F.data == "menu:settings")
    async def cb_settings(cb: CallbackQuery) -> None:
        await cb.answer()
        await _settings(cb.message, cb.from_user.id)

    @router.callback_query(F.data == "menu:help")
    async def cb_help(cb: CallbackQuery) -> None:
        lang = cache.language(cb.from_user.id)
        await cb.message.edit_text(t(lang, "help_text"), reply_markup=back_keyboard(lang))
        await cb.answer()

    @router.callback_query(F.data == "menu:upload")
    async def cb_upload(cb: CallbackQuery, state: FSMContext) -> None:
        lang = cache.language(cb.from_user.id)
        await cb.answer()
        if cfg.is_demo:
            await cb.message.answer(t(lang, "upload_demo"), reply_markup=back_keyboard(lang))
            return
        await state.set_state(UploadStates.waiting_file)
        await cb.message.answer(t(lang, "upload_prompt"), reply_markup=back_keyboard(lang))

    @router.callback_query(F.data.startswith("report:"))
    async def cb_report_generate(cb: CallbackQuery) -> None:
        _, kind, fmt = cb.data.split(":")
        uid = cb.from_user.id
        lang = cache.language(uid)
        await cb.answer(t(lang, "analysis_running"))
        try:
            meta = await api.report(uid, kind=kind, fmt=fmt, period="month")
            content = await api.download_report(uid, meta["id"])
        except BotAPIError as exc:
            await cb.message.answer(f"{t(lang, 'error')}\n<i>{exc.message}</i>")
            return
        await cb.message.answer_document(
            BufferedInputFile(content, filename=meta["filename"]),
            caption=t(lang, "report_done", filename=meta["filename"]))

    @router.callback_query(F.data == "settings:lang")
    async def cb_lang(cb: CallbackQuery) -> None:
        await cb.message.edit_text(t(cache.language(cb.from_user.id), "choose_lang"),
                                   reply_markup=language_keyboard())
        await cb.answer()

    @router.callback_query(F.data.startswith("lang:"))
    async def cb_set_lang(cb: CallbackQuery) -> None:
        code = cb.data.split(":", 1)[1]
        uid = cb.from_user.id
        try:
            await api.set_language(uid, code)
        except BotAPIError:
            await cb.answer(t("uz", "error"), show_alert=True)
            return
        cached = cache.get(uid) or {}
        cached["language"] = code
        cache.set(uid, cached)
        await cb.message.edit_text(t(code, "lang_set"),
                                   reply_markup=main_menu(code, is_demo=cfg.is_demo))
        await cb.answer()

    @router.callback_query(F.data == "settings:alerts")
    async def cb_alerts(cb: CallbackQuery) -> None:
        uid = cb.from_user.id
        lang = cache.language(uid)
        try:
            result = await api.toggle_alerts(uid)
        except BotAPIError:
            await cb.answer(t(lang, "error"), show_alert=True)
            return
        await cb.answer(t(lang, "alerts_on" if result["alerts_enabled"] else "alerts_off"),
                        show_alert=True)

    @router.callback_query(F.data == "settings:unlink")
    async def cb_unlink(cb: CallbackQuery) -> None:
        uid = cb.from_user.id
        lang = cache.language(uid)
        try:
            await api.unlink(uid)
        except BotAPIError:
            await cb.answer(t(lang, "error"), show_alert=True)
            return
        cache.drop(uid)
        await cb.message.edit_text(t(lang, "unlinked"))
        await cb.answer()

    @router.errors()
    async def on_error(event) -> bool:  # pragma: no cover - defensive path
        return True

    return router
