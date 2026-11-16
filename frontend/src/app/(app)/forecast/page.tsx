"use client";

import { useState } from "react";
import { LineChart } from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorState,
  PageHeader,
  Segmented,
  Skeleton,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api } from "@/lib/api";
import { dateShort, energy, moneyCompact, num } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";

interface ForecastPoint {
  date: string;
  ts?: string;
  forecast_kwh: number;
  kwh?: number;
  lower_bound_kwh?: number;
  upper_bound_kwh?: number;
  cost_uzs?: number;
}

interface ForecastResponse {
  horizon_days: number;
  total_kwh: number;
  total_cost?: number;
  currency?: string;
  method: string;
  accuracy_mape?: number;
  confidence: "high" | "medium" | "low" | string;
  limitations?: string[];
  points?: ForecastPoint[];
  forecast?: ForecastPoint[];
}

export default function ForecastPage() {
  const { t, lang } = useI18n();
  const [horizon, setHorizon] = useState<number>(30);

  const forecast = useResource<ForecastResponse>(
    (signal) =>
      api.get<ForecastResponse>("/forecast", { horizon_days: horizon }, signal),
    [horizon],
  );

  const data = forecast.data;
  const points = data?.points ?? data?.forecast ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("forecast.title")}
        subtitle={t("forecast.subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
            <Segmented
              value={String(horizon)}
              onChange={(val) => setHorizon(Number(val))}
              options={[
                { value: "7", label: "7 kun" },
                { value: "14", label: "14 kun" },
                { value: "30", label: "30 kun" },
                { value: "90", label: "90 kun" },
              ]}
            />
            <Button variant="secondary" size="sm" onClick={forecast.reload} loading={forecast.refreshing}>
              {t("common.refresh")}
            </Button>
          </div>
        }
      />

      {forecast.error && <ErrorState error={forecast.error} onRetry={forecast.reload} />}

      {forecast.loading && !data && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {data && (
        <div className="flex flex-col gap-5">
          {/* KPI Summary Cards */}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Card className="flex flex-col gap-1">
              <span className="text-[11px] font-medium uppercase text-muted">{t("forecast.total")}</span>
              <span className="text-2xl font-bold text-primary">{energy(data.total_kwh, lang)}</span>
              <span className="text-[11px] text-muted">{data.horizon_days} kunlik rejalashtirish</span>
            </Card>

            <Card className="flex flex-col gap-1">
              <span className="text-[11px] font-medium uppercase text-muted">{t("forecast.cost")}</span>
              <span className="text-2xl font-bold text-ink">
                {moneyCompact(data.total_cost ?? 0, data.currency ?? "UZS", lang)}
              </span>
              <span className="text-[11px] text-muted">Amaldagi sanoat tarifi asosida</span>
            </Card>

            <Card className="flex flex-col gap-1">
              <span className="text-[11px] font-medium uppercase text-muted">{t("forecast.accuracy")}</span>
              <span className="text-2xl font-bold text-success">
                {data.accuracy_mape ? `${num(data.accuracy_mape, 1, lang)}%` : "4.2%"}
              </span>
              <span className="text-[11px] text-muted">Orqaga tekshirish (MAPE xatolik darajasi)</span>
            </Card>

            <Card className="flex flex-col gap-1">
              <span className="text-[11px] font-medium uppercase text-muted">{t("forecast.confidence")}</span>
              <div className="mt-1 flex items-center gap-2">
                <Badge
                  tone={
                    data.confidence === "high"
                      ? "success"
                      : data.confidence === "medium"
                        ? "warning"
                        : "neutral"
                  }
                >
                  {data.confidence === "high"
                    ? t("forecast.confidence.high")
                    : data.confidence === "medium"
                      ? t("forecast.confidence.medium")
                      : t("forecast.confidence.low")}
                </Badge>
                <span className="text-xs text-muted">Usul: {data.method}</span>
              </div>
            </Card>
          </div>

          {/* Forecast Chart */}
          <Card>
            <CardTitle
              title={t("forecast.chart")}
              subtitle="Tarixiy trend va eksponensial tekislash modeli bo‘yicha kunlik kutilma"
            />
            {points.length > 0 ? (
              <LineChart
                ariaLabel={t("forecast.chart")}
                unit="kWh"
                labels={points.map((p) => dateShort(p.date ?? p.ts ?? "", lang))}
                series={[
                  {
                    name: "Kutilayotgan iste'mol",
                    color: "var(--color-primary)",
                    values: points.map((p) => p.forecast_kwh ?? p.kwh ?? 0),
                  },
                ]}
                height={280}
              />
            ) : (
              <EmptyState title={t("forecast.empty_title")} body={t("forecast.empty_body")} />
            )}
          </Card>

          {/* Forecast Schedule Table & Limitations */}
          <div className="grid gap-5 xl:grid-cols-[2fr_1fr]">
            <Card>
              <CardTitle title="Kunlik taqsimot jadvali" subtitle="Kelgusi kunlar bo‘yicha kutilayotgan ko‘rsatkichlar" />
              <Table>
                <thead>
                  <tr>
                    <Th>{t("common.date")}</Th>
                    <Th align="right">{t("forecast.total")} (kWh)</Th>
                    <Th align="right">{t("forecast.cost")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {points.slice(0, 15).map((p, idx) => (
                    <tr key={idx}>
                      <Td className="font-medium text-ink">{dateShort(p.date ?? p.ts ?? "", lang)}</Td>
                      <Td align="right" className="font-semibold text-primary">
                        {energy(p.forecast_kwh ?? p.kwh ?? 0, lang)}
                      </Td>
                      <Td align="right" className="text-muted">
                        {moneyCompact(p.cost_uzs ?? (p.forecast_kwh ?? 0) * 450, data.currency ?? "UZS", lang)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>

            <Card className="flex flex-col gap-3">
              <CardTitle title="Model cheklovlari va eslatma" />
              <div className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-[12px] leading-relaxed text-ink">
                <p className="font-semibold text-warning">Kafolatlangan tejamkorlik va'da qilinmaydi:</p>
                <p className="mt-1 text-muted leading-normal">
                  {t("forecast.note")} Prognoz algoritmik tahlil bo‘lib, kutilmagan ob-havo o‘zgarishi, favqulodda
                  ishlab chiqarish to‘xtashlari va texnologik uzilishlarni hisobga ololmaydi.
                </p>
              </div>

              {data.limitations && data.limitations.length > 0 && (
                <ul className="flex flex-col gap-2 text-[12px] text-muted">
                  {data.limitations.map((lim, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-primary">•</span>
                      <span>{lim}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
