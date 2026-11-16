"use client";

import Link from "next/link";
import { useState } from "react";
import { BarChart, LineChart, ShareBars } from "@/components/charts";
import {
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Segmented,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api } from "@/lib/api";
import { dateShort, dateTime, energy, money, num, pct, power } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import type { Comparison, ConsumptionAnalytics, Meter } from "@/lib/types";

const PERIODS = ["today", "week", "month", "year", "last_30_days", "last_90_days"] as const;
type Period = (typeof PERIODS)[number];
const GRANULARITIES = ["hour", "day", "week", "month"] as const;
type Granularity = (typeof GRANULARITIES)[number];

export default function AnalyticsPage() {
  const { t, lang } = useI18n();
  const [period, setPeriod] = useState<Period>("month");
  const [granularity, setGranularity] = useState<Granularity>("day");
  const [meterId, setMeterId] = useState("");
  const [department, setDepartment] = useState("");
  const [mode, setMode] = useState<"previous" | "year">("previous");

  const meters = useResource<{ items: Meter[] }>(
    (signal) => api.get<{ items: Meter[] }>("/meters", { page_size: 200 }, signal),
    [],
  );
  const departments = Array.from(
    new Set((meters.data?.items ?? []).map((meter) => meter.department).filter(Boolean) as string[]),
  );

  const analytics = useResource<ConsumptionAnalytics>(
    (signal) =>
      api.get<ConsumptionAnalytics>(
        "/analytics/consumption",
        { period, granularity, meter_id: meterId || undefined, department: department || undefined },
        signal,
      ),
    [period, granularity, meterId, department],
  );
  const comparison = useResource<Comparison>(
    (signal) =>
      api.get<Comparison>(
        "/analytics/comparison",
        { period, mode, meter_id: meterId || undefined, department: department || undefined },
        signal,
      ),
    [period, mode, meterId, department],
  );

  const data = analytics.data;

  return (
    <div>
      <PageHeader
        title={t("analytics.title")}
        subtitle={t("analytics.subtitle")}
        actions={
          <Link href="/reports">
            <Button variant="secondary" size="sm">
              {t("reports.export")}
            </Button>
          </Link>
        }
      />

      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("common.period")} className="min-w-[10rem]">
            <Select value={period} onChange={(event) => setPeriod(event.target.value as Period)}>
              {PERIODS.map((value) => (
                <option key={value} value={value}>
                  {t(`period.${value}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("analytics.granularity")}>
            <Segmented
              ariaLabel={t("analytics.granularity")}
              value={granularity}
              onChange={(next) => setGranularity(next)}
              options={GRANULARITIES.map((value) => ({
                value,
                label: t(`analytics.granularity.${value}`),
              }))}
            />
          </Field>
          <Field label={t("common.meter")} className="min-w-[12rem]">
            <Select value={meterId} onChange={(event) => setMeterId(event.target.value)}>
              <option value="">{t("common.all")}</option>
              {(meters.data?.items ?? []).map((meter) => (
                <option key={meter.id} value={meter.id}>
                  {meter.name} · {meter.serial_number}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("common.department")} className="min-w-[10rem]">
            <Select value={department} onChange={(event) => setDepartment(event.target.value)}>
              <option value="">{t("common.all")}</option>
              {departments.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
          <Button variant="ghost" size="sm" onClick={analytics.reload} loading={analytics.refreshing}>
            {t("common.refresh")}
          </Button>
        </div>
      </Card>

      {analytics.error && <ErrorState error={analytics.error} onRetry={analytics.reload} />}

      {analytics.loading && !data && <Skeleton className="h-72" />}

      {data && data.totals.readings === 0 && (
        <Card>
          <EmptyState
            title={t("analytics.empty_title")}
            body={t("analytics.empty_body")}
            action={
              <Link href="/imports">
                <Button size="sm">{t("dashboard.no_data_cta")}</Button>
              </Link>
            }
          />
        </Card>
      )}

      {data && data.totals.readings > 0 && (
        <div className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MiniStat label={t("analytics.total_energy")} value={energy(data.totals.consumption_kwh, lang)} />
            <MiniStat
              label={t("dashboard.kpi.cost")}
              value={money(data.totals.estimated_cost, data.totals.currency, lang)}
              hint={data.totals.tariff?.name ?? t("dashboard.tariff_missing")}
            />
            <MiniStat
              label={t("common.peak")}
              value={power(data.totals.peak_power_kw, lang)}
              hint={`${t("common.average")}: ${power(data.totals.average_power_kw, lang)}`}
            />
            <MiniStat
              label={t("common.coverage")}
              value={`${num(data.totals.data_coverage_pct, 1, lang)}%`}
              hint={`${data.totals.readings} / ${data.totals.expected_intervals}`}
            />
          </div>

          <Card>
            <CardTitle
              title={t("analytics.title")}
              subtitle={`${dateShort(data.window.start, lang)} — ${dateShort(data.window.end, lang)} · ${data.series.length} ${t("common.rows")}`}
            />
            <LineChart
              ariaLabel={t("analytics.title")}
              unit="kWh"
              labels={data.series.map((point) => point.label)}
              series={[
                {
                  name: t("analytics.total_energy"),
                  color: "var(--color-primary)",
                  values: data.series.map((point) => point.consumption_kwh),
                },
              ]}
              height={280}
            />
            <p className="mt-2 text-[11px] text-muted">
              {t("meters.energy_vs_power")} · kWh
            </p>
          </Card>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardTitle title={t("analytics.comparison")} />
              <div className="mb-3 flex items-center gap-2">
                <Segmented
                  ariaLabel={t("analytics.mode")}
                  value={mode}
                  onChange={setMode}
                  options={[
                    { value: "previous", label: t("analytics.mode.previous") },
                    { value: "year", label: t("analytics.mode.year") },
                  ]}
                />
              </div>
              {comparison.data ? (
                <div className="flex flex-col gap-2 text-[13px]">
                  <Row
                    label={t("analytics.current")}
                    value={`${energy(comparison.data.current.consumption_kwh, lang)} · ${money(comparison.data.current.estimated_cost, data.totals.currency, lang)}`}
                    hint={`${dateShort(comparison.data.current.start, lang)} — ${dateShort(comparison.data.current.end, lang)}`}
                  />
                  <Row
                    label={t("analytics.baseline")}
                    value={`${energy(comparison.data.baseline.consumption_kwh, lang)} · ${money(comparison.data.baseline.estimated_cost, data.totals.currency, lang)}`}
                    hint={`${dateShort(comparison.data.baseline.start, lang)} — ${dateShort(comparison.data.baseline.end, lang)}`}
                  />
                  <Row
                    label={t("analytics.difference")}
                    value={
                      comparison.data.difference_pct === null
                        ? (comparison.data.why_null_pct ?? t("analytics.why_null"))
                        : `${pct(comparison.data.difference_pct, lang)} (${energy(comparison.data.difference_kwh, lang)})`
                    }
                    tone={
                      comparison.data.difference_pct === null
                        ? "neutral"
                        : comparison.data.difference_pct > 0
                          ? "danger"
                          : "success"
                    }
                  />
                </div>
              ) : (
                <Skeleton className="h-24" />
              )}
            </Card>

            <Card>
              <CardTitle title={t("analytics.by_department")} />
              {data.by_department.length === 0 ? (
                <p className="py-6 text-center text-[12px] text-muted">{t("common.empty")}</p>
              ) : (
                <ShareBars
                  lang={lang}
                  unit="kWh"
                  items={data.by_department.map((row) => ({
                    label: row.department,
                    value: row.consumption_kwh,
                    share: row.share_pct,
                  }))}
                />
              )}
            </Card>
          </div>

          <Card>
            <CardTitle title={t("analytics.hourly_profile")} subtitle="kWh" />
            <BarChart
              ariaLabel={t("analytics.hourly_profile")}
              unit="kWh"
              bars={data.hourly_profile.map((row) => ({
                label: `${String(row.hour).padStart(2, "0")}:00`,
                value: row.average_kwh,
              }))}
              height={170}
            />
          </Card>

          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardTitle title={t("analytics.by_meter")} />
              <Table>
                <thead>
                  <tr>
                    <Th>{t("common.meter")}</Th>
                    <Th>{t("common.department")}</Th>
                    <Th align="right">{t("common.total")} (kWh)</Th>
                    <Th align="right">{t("common.share")}</Th>
                    <Th align="right">{t("common.peak")} (kW)</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_meter.map((row) => (
                    <tr key={row.meter_id}>
                      <Td>
                        <Link
                          href={`/meters/${row.meter_id}`}
                          className="text-ink underline-offset-2 hover:text-accent hover:underline"
                        >
                          {row.name}
                        </Link>
                        <span className="ml-1.5 text-[11px] text-muted">{row.serial_number}</span>
                      </Td>
                      <Td className="text-muted">{row.department ?? "—"}</Td>
                      <Td align="right">{num(row.consumption_kwh, 1, lang)}</Td>
                      <Td align="right">{num(row.share_pct, 1, lang)}%</Td>
                      <Td align="right">{num(row.peak_power_kw, 1, lang)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>

            <Card>
              <CardTitle title={t("analytics.peaks")} />
              <Table>
                <thead>
                  <tr>
                    <Th>{t("common.date")}</Th>
                    <Th>{t("common.meter")}</Th>
                    <Th align="right">kWh</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.peaks.slice(0, 10).map((peak, index) => (
                    <tr key={`${peak.ts}-${index}`}>
                      <Td className="whitespace-nowrap text-muted">{dateTime(peak.ts, lang)}</Td>
                      <Td className="max-w-[10rem] truncate">{peak.meter}</Td>
                      <Td align="right">{num(peak.consumption_kwh, 1, lang)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <p className="mt-2 text-[11px] text-muted">{t("analytics.export_hint")}</p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-ink">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted">{hint}</p>}
    </Card>
  );
}

function Row({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "danger" | "success";
}) {
  const color = tone === "danger" ? "text-danger" : tone === "success" ? "text-success" : "text-ink";
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/50 pb-2 last:border-0">
      <div>
        <p className="text-[12px] text-muted">{label}</p>
        {hint && <p className="text-[10px] text-muted/70">{hint}</p>}
      </div>
      <p className={`text-right text-[13px] font-medium ${color}`}>{value}</p>
    </div>
  );
}
