"use client";

import Link from "next/link";
import { useState } from "react";
import { LineChart, ShareBars } from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorState,
  PageHeader,
  ProgressBar,
  Segmented,
  SeverityBadge,
  Skeleton,
  Td,
  Th,
  Table,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateShort, dateTime, energy, money, moneyCompact, num, pct, power } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import type { ConsumptionAnalytics, DashboardSummary } from "@/lib/types";

const PERIODS = ["today", "week", "month", "year"] as const;
type Period = (typeof PERIODS)[number];

export default function DashboardPage() {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const [period, setPeriod] = useState<Period>("month");

  const summary = useResource<DashboardSummary>(
    (signal) => api.get<DashboardSummary>("/dashboard/summary", { period }, signal),
    [period],
  );
  const series = useResource<ConsumptionAnalytics>(
    (signal) =>
      api.get<ConsumptionAnalytics>(
        "/analytics/consumption",
        { period, granularity: period === "today" ? "hour" : "day" },
        signal,
      ),
    [period],
  );

  const data = summary.data;
  const loading = summary.loading;

  const latestAnomalies = data?.anomalies?.top ?? data?.anomalies?.latest ?? [];
  const criticalCount = data?.anomalies?.by_severity?.critical ?? data?.anomalies?.critical ?? 0;
  const seriesPoints = series.data?.series ?? [];
  const meterBreakdowns = series.data?.by_meter ?? [];

  return (
    <div>
      <PageHeader
        title={t("dashboard.title")}
        subtitle={t("dashboard.subtitle")}
        actions={
          <>
            <Segmented
              ariaLabel={t("common.period")}
              value={period}
              onChange={(next) => setPeriod(next)}
              options={PERIODS.map((value) => ({ value, label: t(`period.${value}`) }))}
            />
            <Button variant="secondary" size="sm" onClick={summary.reload} loading={summary.refreshing}>
              {t("common.refresh")}
            </Button>
          </>
        }
      />

      {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}

      {loading && !data && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-24" />
          ))}
        </div>
      )}

      {data && !data.has_data && (
        <Card>
          <EmptyState
            title={t("dashboard.no_data_title")}
            body={t("dashboard.no_data_body")}
            action={
              <Link href="/imports">
                <Button size="sm">{t("dashboard.no_data_cta")}</Button>
              </Link>
            }
          />
        </Card>
      )}

      {data && data.has_data && (
        <div className="flex flex-col gap-4">
          {/* KPI row */}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile
              label={t("dashboard.kpi.consumption")}
              value={energy(data.consumption.total_kwh, lang)}
              hint={
                data.trend.vs_previous_period_pct === null
                  ? t("dashboard.trend.vs_previous")
                  : `${pct(data.trend.vs_previous_period_pct, lang)} ${t("dashboard.trend.vs_previous")}`
              }
              tone={
                data.trend.vs_previous_period_pct === null
                  ? "neutral"
                  : data.trend.vs_previous_period_pct > 0
                    ? "warning"
                    : "success"
              }
            />
            <KpiTile
              label={t("dashboard.kpi.cost")}
              value={moneyCompact(data.cost.estimated, data.cost.currency, lang)}
              hint={
                data.cost.tariff
                  ? `${data.cost.tariff.name} · ${num(data.cost.tariff.price_per_kwh, 0, lang)} ${data.cost.currency}/kWh`
                  : t("dashboard.tariff_missing")
              }
              tone={data.cost.estimated === null ? "neutral" : "primary"}
            />
            <KpiTile
              label={t("dashboard.kpi.peak")}
              value={power(data.consumption.peak_power_kw, lang)}
              hint={`${t("common.average")}: ${power(data.consumption.average_power_kw, lang)}`}
              tone="accent"
            />
            <KpiTile
              label={t("dashboard.kpi.coverage")}
              value={`${num(data.consumption.data_coverage_pct, 1, lang)}%`}
              hint={`${data.consumption.readings} ${t("common.readings").toLowerCase()} · ${data.consumption.meters_contributing} ${t("common.meters").toLowerCase()}`}
              tone={
                data.consumption.data_coverage_pct >= 90
                  ? "success"
                  : data.consumption.data_coverage_pct >= 60
                    ? "warning"
                    : "danger"
              }
              progress={data.consumption.data_coverage_pct}
            />
          </div>

          {/* period + trend strip */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-line bg-surface/50 px-4 py-2.5 text-[12px] text-muted">
            <span>
              {t("dashboard.period_range")}:{" "}
              <span className="text-ink">
                {dateShort(data.period.start_local ?? data.period.start, lang)} —{" "}
                {dateShort(data.period.end_local ?? data.period.end, lang)}
              </span>
            </span>
            <span>
              {t("dashboard.trend.vs_previous")}:{" "}
              <span className="text-ink">
                {data.trend.previous_period_kwh
                  ? `${energy(data.trend.previous_period_kwh, lang)} (${pct(data.trend.vs_previous_period_pct, lang)})`
                  : t("common.empty")}
              </span>
            </span>
            <span className="ml-auto flex items-center gap-2">
              <Badge tone={criticalCount > 0 ? "danger" : (data.anomalies?.count ?? 0) > 0 ? "warning" : "success"}>
                {t("dashboard.kpi.anomalies")}: {data.anomalies?.count ?? 0}
              </Badge>
              <Link href="/anomalies" className="text-accent underline underline-offset-2">
                {t("dashboard.view_all")}
              </Link>
            </span>
          </div>

          {/* chart + top meters */}
          <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
            <Card>
              <CardTitle
                title={t("dashboard.consumption_chart")}
                subtitle={
                  data.cost.tariff
                    ? `${t("dashboard.cost_note")} · ${energy(data.consumption.total_kwh, lang)}`
                    : t("dashboard.tariff_missing")
                }
              />
              {seriesPoints.length > 0 ? (
                <LineChart
                  ariaLabel={t("dashboard.consumption_chart")}
                  unit="kWh"
                  labels={seriesPoints.map((point) => point.label)}
                  series={[
                    {
                      name: t("dashboard.kpi.consumption"),
                      color: "var(--color-primary)",
                      values: seriesPoints.map((point) => point.consumption_kwh),
                    },
                  ]}
                  height={260}
                />
              ) : series.loading ? (
                <Skeleton className="h-64" />
              ) : (
                <div className="flex h-64 items-center justify-center text-xs text-muted">
                  Grafik ma'lumotlari mavjud emas
                </div>
              )}
            </Card>

            <Card>
              <CardTitle
                title={t("dashboard.top_meters")}
                action={
                  <Link href="/analytics" className="text-[11px] text-accent underline underline-offset-2">
                    {t("common.details")}
                  </Link>
                }
              />
              {meterBreakdowns.length > 0 ? (
                <ShareBars
                  lang={lang}
                  unit="kWh"
                  items={meterBreakdowns.slice(0, 6).map((meter) => ({
                    label: `${meter.name}${meter.department ? ` · ${meter.department}` : ""}`,
                    value: meter.consumption_kwh,
                    share: meter.share_pct,
                  }))}
                />
              ) : series.loading ? (
                <div className="flex flex-col gap-3">
                  {Array.from({ length: 5 }).map((_, index) => (
                    <Skeleton key={index} className="h-6" />
                  ))}
                </div>
              ) : (
                <div className="flex h-36 items-center justify-center text-xs text-muted">
                  Hisoblagichlar mavjud emas
                </div>
              )}
            </Card>
          </div>

          {/* efficiency + anomalies + forecast hint */}
          <div className="grid gap-4 xl:grid-cols-3">
            <Card>
              <CardTitle title={t("dashboard.efficiency")} />
              <dl className="flex flex-col">
                <div className="flex items-center justify-between border-b border-line/50 py-2 text-[13px]">
                  <dt className="text-muted">{t("dashboard.kwh_per_meter_day")}</dt>
                  <dd className="font-medium text-ink">
                    {data.efficiency.kwh_per_meter_day === null
                      ? "—"
                      : energy(data.efficiency.kwh_per_meter_day, lang)}
                  </dd>
                </div>
                <div className="flex items-center justify-between border-b border-line/50 py-2 text-[13px]">
                  <dt className="text-muted">{t("dashboard.peak_to_average")}</dt>
                  <dd className="font-medium text-ink">
                    {data.efficiency.peak_to_average_ratio === null
                      ? "—"
                      : num(data.efficiency.peak_to_average_ratio, 2, lang)}
                  </dd>
                </div>
                <div className="flex items-center justify-between py-2 text-[13px]">
                  <dt className="text-muted">{t("dashboard.kpi.meters")}</dt>
                  <dd className="font-medium text-ink">{data.consumption.meters_contributing}</dd>
                </div>
              </dl>
              <p className="mt-2 text-[11px] leading-relaxed text-muted">{t("common.estimate")}</p>
            </Card>

            <Card>
              <CardTitle
                title={t("dashboard.anomalies_latest")}
                action={
                  <Link href="/anomalies" className="text-[11px] text-accent underline underline-offset-2">
                    {t("dashboard.view_all")}
                  </Link>
                }
              />
              {latestAnomalies.length === 0 ? (
                <p className="py-6 text-center text-[12px] text-muted">{t("anomalies.empty_title")}</p>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>{t("common.meter")}</Th>
                      <Th>{t("common.date")}</Th>
                      <Th align="right">{t("anomalies.deviation")}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {latestAnomalies.slice(0, 5).map((item) => (
                      <tr key={item.id}>
                        <Td>
                          <div className="flex flex-col">
                            <span className="truncate">{item.meter}</span>
                            <SeverityBadge severity={item.severity} />
                          </div>
                        </Td>
                        <Td className="whitespace-nowrap text-muted">{dateTime(item.ts, lang)}</Td>
                        <Td align="right" className="text-danger">
                          {pct(item.deviation_pct, lang)}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>

            <Card>
              <CardTitle title={t("dashboard.forecast_hint")} />
              <p className="text-[12px] leading-relaxed text-muted">{t("forecast.note")}</p>
              <div className="mt-3 flex flex-col gap-2">
                <Link href="/forecast">
                  <Button variant="secondary" size="sm" className="w-full">
                    {t("nav.forecast")}
                  </Button>
                </Link>
                {can("analyst") && (
                  <Link href="/advisor">
                    <Button variant="ghost" size="sm" className="w-full">
                      {t("nav.advisor")}
                    </Button>
                  </Link>
                )}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function KpiTile({
  label,
  value,
  hint,
  tone = "neutral",
  progress,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "primary" | "accent" | "success" | "warning" | "danger";
  progress?: number;
}) {
  const accent =
    tone === "success"
      ? "text-success"
      : tone === "warning"
        ? "text-warning"
        : tone === "danger"
          ? "text-danger"
          : tone === "accent"
            ? "text-accent"
            : tone === "primary"
              ? "text-primary"
              : "text-ink";
  return (
    <Card className="flex flex-col gap-1.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${accent}`}>{value}</p>
      {progress !== undefined && <ProgressBar value={progress} tone={tone === "primary" ? "primary" : tone} />}
      {hint && <p className="text-[11px] leading-relaxed text-muted">{hint}</p>}
    </Card>
  );
}
