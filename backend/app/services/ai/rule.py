"""Deterministic narrator.

The provider of record when no model key is configured — and the fallback when a
model is unavailable or its draft fails the numeric guard. It never *generates*:
`advisor._narrate_rule` renders the answer straight from the validated fact
bundle using the templates below, so every figure is traceable to the database.

`RuleBasedProvider.complete` therefore refuses to prompt: there is no model here
to hallucinate with.
"""
from __future__ import annotations

from app.services.ai.base import AIProviderError

TEMPLATES: dict[str, dict[str, str]] = {
    "uz": {
        "header": "NEXTGEN AI tahlili — {org}",
        "period": "Davr: {period}",
        "consumption": "Jami iste'mol: {kwh} kWh ({readings} o'qish, qamrov {coverage}%).",
        "cost_none": "Tarif sozlanmagan, shuning uchun pul qiymati hisoblanmadi.",
        "cost": "Hisoblangan xarajat: {cost} {currency} (tarif: {tariff}).",
        "compare_up": "O'tgan davrga nisbatan {pct}% o'sish ({prev} kWh edi).",
        "compare_down": "O'tgan davrga nisbatan {pct}% pasayish ({prev} kWh edi).",
        "compare_na": "Taqqoslash uchun oldingi davr ma'lumoti yetarli emas.",
        "top_meter": "Eng ko'p iste'mol: {meter} — {kwh} kWh (ulush {share}%).",
        "anomalies": "Anomaliyalar: {count} ta ({severity}).",
        "anomalies_none": "Tanlangan davrda anomaliya aniqlanmadi.",
        "forecast": ("Prognoz ({days} kun): {kwh} kWh, taxminiy xarajat {cost} {currency}. "
                     "Aniqlik (MAPE) {mape}%, ishonch: {confidence}."),
        "forecast_none": "Prognoz uchun tarixiy ma'lumot yetarli emas.",
        "suggestions_title": "Tavsiyalar (AI takliflari, tasdiqlangan fakt emas):",
    },
    "ru": {
        "header": "Анализ NEXTGEN AI — {org}",
        "period": "Период: {period}",
        "consumption": "Общее потребление: {kwh} кВт·ч ({readings} показаний, покрытие {coverage}%).",
        "cost_none": "Тариф не настроен, поэтому денежная оценка не рассчитана.",
        "cost": "Расчётная стоимость: {cost} {currency} (тариф: {tariff}).",
        "compare_up": "По сравнению с прошлым периодом рост {pct}% (было {prev} кВт·ч).",
        "compare_down": "По сравнению с прошлым периодом снижение {pct}% (было {prev} кВт·ч).",
        "compare_na": "Для сравнения недостаточно данных прошлого периода.",
        "top_meter": "Наибольшее потребление: {meter} — {kwh} кВт·ч (доля {share}%).",
        "anomalies": "Аномалии: {count} ({severity}).",
        "anomalies_none": "За выбранный период аномалии не обнаружены.",
        "forecast": ("Прогноз ({days} дней): {kwh} кВт·ч, расчётная стоимость {cost} {currency}. "
                     "Точность (MAPE) {mape}%, доверие: {confidence}."),
        "forecast_none": "Недостаточно истории для прогноза.",
        "suggestions_title": "Рекомендации (предложения ИИ, не подтверждённый факт):",
    },
    "en": {
        "header": "NEXTGEN AI analysis — {org}",
        "period": "Period: {period}",
        "consumption": "Total consumption: {kwh} kWh ({readings} readings, coverage {coverage}%).",
        "cost_none": "No tariff is configured, so no monetary value was calculated.",
        "cost": "Estimated cost: {cost} {currency} (tariff: {tariff}).",
        "compare_up": "Up {pct}% versus the previous period (was {prev} kWh).",
        "compare_down": "Down {pct}% versus the previous period (was {prev} kWh).",
        "compare_na": "There is not enough previous-period data to compare.",
        "top_meter": "Highest consumption: {meter} — {kwh} kWh ({share}% share).",
        "anomalies": "Anomalies: {count} ({severity}).",
        "anomalies_none": "No anomalies were detected for the selected period.",
        "forecast": ("Forecast ({days} days): {kwh} kWh, estimated cost {cost} {currency}. "
                     "Accuracy (MAPE) {mape}%, confidence: {confidence}."),
        "forecast_none": "Not enough history to produce a forecast.",
        "suggestions_title": "Recommendations (AI suggestions, not verified facts):",
    },
}


class RuleBasedProvider:
    """No-model provider: narration happens in `advisor._narrate_rule`."""

    name = "rule_based"
    model = None

    def __init__(self, language: str = "uz") -> None:
        self.language = language if language in TEMPLATES else "uz"

    def complete(self, *, system: str, user: str) -> str:  # pragma: no cover
        raise AIProviderError(
            "The deterministic provider narrates the fact bundle directly and cannot be prompted")
