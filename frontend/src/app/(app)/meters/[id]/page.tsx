"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { LineChart } from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  DataRow,
  ErrorState,
  Field,
  Input,
  Modal,
  PageHeader,
  ProgressBar,
  Skeleton,
  Table,
  Td,
  Th,
  Toggle,
  useToast,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateShort, dateTime, daysAgoIso, energy, isoDateInTz, num, power } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import type { Coverage, Meter, ReadingPage } from "@/lib/types";

export default function MeterDetailPage() {
  const params = useParams<{ id: string }>();
  const meterId = params?.id ?? "";
  const router = useRouter();
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const toast = useToast();

  const [page, setPage] = useState(1);
  const [openReading, setOpenReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [reading, setReading] = useState({ ts: "", consumption_kwh: "", interval_minutes: "" });

  const meter = useResource<Meter>((signal) => api.get<Meter>(`/meters/${meterId}`, undefined, signal), [meterId]);
  const readings = useResource<ReadingPage>(
    (signal) =>
      api.get<ReadingPage>("/readings", { meter_id: meterId, page, page_size: 50 }, signal),
    [meterId, page],
  );
  const coverage = useResource<Coverage>(
    (signal) =>
      api.get<Coverage>(
        `/meters/${meterId}/coverage`,
        { start: `${daysAgoIso(30)}T00:00:00+05:00`, end: `${isoDateInTz()}T23:59:59+05:00` },
        signal,
      ),
    [meterId],
  );

  const toggleStatus = async (next: boolean) => {
    try {
      await api.patch(`/meters/${meterId}`, { status: next ? "active" : "inactive" });
      toast.success(t("meters.updated"));
      meter.reload();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("error.generic"));
    }
  };

  const remove = async () => {
    if (!window.confirm(`${t("common.confirm_delete")}\n${t("meters.delete_warning")}`)) return;
    try {
      await api.del(`/meters/${meterId}`);
      toast.success(t("meters.deleted"));
      router.push("/meters");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("error.generic"));
    }
  };

  const submitReading = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await api.post(`/meters/${meterId}/readings`, {
        ts: new Date(reading.ts).toISOString(),
        consumption_kwh: Number(reading.consumption_kwh),
        interval_minutes: reading.interval_minutes ? Number(reading.interval_minutes) : null,
      });
      toast.success(t("meters.reading_added"));
      setOpenReading(false);
      setReading({ ts: "", consumption_kwh: "", interval_minutes: "" });
      readings.reload();
      coverage.reload();
      meter.reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err : new ApiError("error", 0));
    } finally {
      setSaving(false);
    }
  };

  if (meter.error) {
    return (
      <div>
        <PageHeader title={t("meters.detail_title")} />
        <ErrorState error={meter.error} onRetry={meter.reload} />
      </div>
    );
  }

  const data = meter.data;

  return (
    <div>
      <PageHeader
        title={data?.name ?? t("common.loading")}
        subtitle={data ? `${data.serial_number} · ${data.department ?? "—"}` : undefined}
        actions={
          <>
            <Link href="/meters">
              <Button variant="secondary" size="sm">
                {t("common.back")}
              </Button>
            </Link>
            {can("analyst") && (
              <Button size="sm" onClick={() => setOpenReading(true)}>
                {t("meters.add_reading")}
              </Button>
            )}
            {can("admin") && data && (
              <Button variant="danger" size="sm" onClick={remove}>
                {t("common.delete")}
              </Button>
            )}
          </>
        }
      />

      {!data && <Skeleton className="h-40" />}

      {data && (
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
            <Card>
              <CardTitle title={t("meters.recent_readings")} subtitle="kWh" />
              {readings.data && readings.data.items.length > 0 ? (
                <LineChart
                  ariaLabel={t("meters.recent_readings")}
                  unit="kWh"
                  labels={[...readings.data.items]
                    .reverse()
                    .map((row) => dateTime(row.ts, lang))}
                  series={[
                    {
                      name: t("common.readings"),
                      color: "var(--color-primary)",
                      values: [...readings.data.items].reverse().map((row) => Number(row.consumption_kwh)),
                    },
                  ]}
                  height={220}
                />
              ) : (
                <p className="py-8 text-center text-[12px] text-muted">{t("common.empty")}</p>
              )}
              <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
                <span>
                  {t("common.page")} {page} / {Math.max(1, Math.ceil((readings.data?.total ?? 0) / 50))}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                  >
                    {t("common.prev")}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!readings.data?.has_next}
                    onClick={() => setPage((prev) => prev + 1)}
                  >
                    {t("common.next")}
                  </Button>
                </div>
              </div>
            </Card>

            <div className="flex flex-col gap-4">
              <Card>
                <CardTitle title={t("common.details")} />
                <dl className="flex flex-col">
                  <DataRow label={t("meters.serial")} value={data.serial_number} />
                  <DataRow label={t("common.department")} value={data.department ?? "—"} />
                  <DataRow label={t("meters.location")} value={data.location ?? "—"} />
                  <DataRow label={t("meters.type")} value={data.meter_type} />
                  <DataRow label={t("meters.interval")} value={`${data.interval_minutes} min`} />
                  <DataRow label={t("meters.multiplier")} value={num(data.multiplier, 3, lang)} />
                  <DataRow
                    label={t("meters.max_power")}
                    value={data.max_power_kw ? power(data.max_power_kw, lang) : "—"}
                  />
                  <DataRow
                    label={t("meters.lifetime_energy")}
                    value={energy(data.total_kwh ?? readings.data?.items.reduce((sum, r) => sum + Number(r.consumption_kwh), 0) ?? 0, lang)}
                  />
                  <DataRow
                    label={t("meters.last_reading")}
                    value={data.last_reading_at ? dateTime(data.last_reading_at, lang) : "—"}
                  />
                </dl>
                {data.notes && <p className="mt-2 text-[11px] text-muted">{data.notes}</p>}
              </Card>

              <Card>
                <CardTitle title={t("meters.coverage_title")} subtitle="oxirgi 30 kun" />
                {coverage.data ? (
                  <>
                    <div className="mb-2 flex items-baseline justify-between">
                      <span className="text-lg font-semibold text-ink">
                        {num(coverage.data.coverage_pct, 1, lang)}%
                      </span>
                      <span className="text-[11px] text-muted">
                        {coverage.data.present_intervals} / {coverage.data.expected_intervals}
                      </span>
                    </div>
                    <ProgressBar
                      value={coverage.data.coverage_pct}
                      tone={
                        coverage.data.coverage_pct >= 90
                          ? "success"
                          : coverage.data.coverage_pct >= 60
                            ? "warning"
                            : "danger"
                      }
                    />
                  </>
                ) : (
                  <Skeleton className="h-10" />
                )}
                {can("analyst") && (
                  <div className="mt-4 border-t border-line/60 pt-3">
                    <Toggle
                      checked={data.status === "active"}
                      onChange={toggleStatus}
                      label={data.status === "active" ? t("meters.active") : t("meters.inactive")}
                    />
                  </div>
                )}
              </Card>
            </div>
          </div>

          <Card>
            <CardTitle
              title={t("meters.recent_readings")}
              subtitle={`${dateShort(readings.data?.items[0]?.ts, lang)} — ${dateShort(
                readings.data?.items[readings.data.items.length - 1]?.ts,
                lang,
              )}`}
            />
            <Table>
              <thead>
                <tr>
                  <Th>{t("common.date")}</Th>
                  <Th align="right">{t("meters.reading_value")}</Th>
                  <Th align="right">{t("meters.interval")}</Th>
                  <Th align="right">kW</Th>
                  <Th>{t("common.status")}</Th>
                </tr>
              </thead>
              <tbody>
                {(readings.data?.items ?? []).map((row) => (
                  <tr key={row.id}>
                    <Td className="whitespace-nowrap">{dateTime(row.ts, lang)}</Td>
                    <Td align="right">{energy(row.consumption_kwh, lang)}</Td>
                    <Td align="right">{row.interval_minutes}</Td>
                    <Td align="right">{row.power_kw ? power(row.power_kw, lang) : "—"}</Td>
                    <Td>
                      <Badge tone={row.quality === "good" ? "success" : "warning"}>{row.quality}</Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}

      <Modal
        open={openReading}
        onClose={() => setOpenReading(false)}
        title={t("meters.add_reading")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpenReading(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" form="reading-form" loading={saving}>
              {t("common.add")}
            </Button>
          </>
        }
      >
        <form id="reading-form" onSubmit={submitReading} className="flex flex-col gap-3">
          <Field label={t("meters.reading_ts")} htmlFor="r-ts">
            <Input
              id="r-ts"
              type="datetime-local"
              required
              value={reading.ts}
              onChange={(event) => setReading({ ...reading, ts: event.target.value })}
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("meters.reading_value")} htmlFor="r-kwh">
              <Input
                id="r-kwh"
                type="number"
                step="0.001"
                min={0}
                required
                value={reading.consumption_kwh}
                onChange={(event) => setReading({ ...reading, consumption_kwh: event.target.value })}
              />
            </Field>
            <Field
              label={`${t("meters.interval")} (${t("common.optional")})`}
              htmlFor="r-interval"
            >
              <Input
                id="r-interval"
                type="number"
                min={1}
                max={1440}
                value={reading.interval_minutes}
                onChange={(event) => setReading({ ...reading, interval_minutes: event.target.value })}
              />
            </Field>
          </div>
          {formError && <ErrorState error={formError} compact />}
        </form>
      </Modal>
    </div>
  );
}
