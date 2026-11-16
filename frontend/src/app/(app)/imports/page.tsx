"use client";

import { useRef, useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  ProgressBar,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  Toggle,
  useToast,
} from "@/components/ui";
import { ApiError, api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { bytes, dateTime, num } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import type { ImportJob, ImportResult, Meter } from "@/lib/types";

interface ImportHistory {
  items: ImportJob[];
  total: number;
  page: number;
  page_size: number;
}

export default function ImportsPage() {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);

  const [meterId, setMeterId] = useState("");
  const [readingType, setReadingType] = useState("interval");
  const [intervalMinutes, setIntervalMinutes] = useState("");
  const [decimalComma, setDecimalComma] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"upload" | "validate" | "confirm" | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});

  const meters = useResource<{ items: Meter[] }>(
    (signal) => api.get<{ items: Meter[] }>("/meters", { page_size: 200 }, signal),
    [],
  );
  const history = useResource<ImportHistory>(
    (signal) => api.get<ImportHistory>("/imports", { page: 1, page_size: 20 }, signal),
    [result],
  );

  const buildForm = () => {
    const form = new FormData();
    if (file) form.append("file", file);
    if (meterId) form.append("meter_id", meterId);
    form.append("reading_type", readingType);
    if (intervalMinutes) form.append("interval_minutes", intervalMinutes);
    form.append("decimal_comma", String(decimalComma));
    return form;
  };

  const upload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file || !meterId) {
      setError(new ApiError(t("imports.meter_required"), 422, "validation_failed"));
      return;
    }
    setBusy("upload");
    setError(null);
    setResult(null);
    try {
      const created = await api.postForm<ImportJob>("/imports", buildForm());
      setJob(created);
      setMapping({
        timestamp: String(created.column_mapping.timestamp ?? ""),
        consumption_kwh: String(created.column_mapping.consumption_kwh ?? ""),
        register_kwh: String(created.column_mapping.register_kwh ?? ""),
        interval_minutes: String(created.column_mapping.interval_minutes ?? ""),
      });
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError("error", 0));
    } finally {
      setBusy(null);
    }
  };

  const revalidate = async () => {
    if (!job || !file) return;
    setBusy("validate");
    setError(null);
    try {
      const form = buildForm();
      for (const [key, value] of Object.entries(mapping)) {
        if (value.trim()) form.append(`mapping_${key}`, value.trim());
      }
      const updated = await api.postForm<ImportJob>(`/imports/${job.id}/validate`, form);
      setJob(updated);
      toast.success(t("imports.summary"));
      history.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError("error", 0));
    } finally {
      setBusy(null);
    }
  };

  const confirm = async () => {
    if (!job) return;
    setBusy("confirm");
    setError(null);
    try {
      const res = await api.post<ImportResult>(`/imports/${job.id}/confirm`, { skip_duplicates: true });
      setResult(res);
      toast.success(t("imports.confirmed"));
      history.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError("error", 0));
    } finally {
      setBusy(null);
    }
  };

  const download = async (fmt: "csv" | "xlsx") => {
    try {
      await downloadFile(`/imports/templates/${fmt}`, `nextgen-import-template.${fmt}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t("error.generic"));
    }
  };

  const canWrite = can("analyst");

  return (
    <div>
      <PageHeader
        title={t("imports.title")}
        subtitle={t("imports.subtitle")}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => download("csv")}>
              {t("imports.template_csv")}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => download("xlsx")}>
              {t("imports.template_xlsx")}
            </Button>
          </>
        }
      />

      {error && <div className="mb-3"><ErrorState error={error} compact /></div>}

      <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr]">
        <Card>
          <CardTitle title={t("imports.step_upload")} subtitle={t("imports.file_hint")} />
          <form onSubmit={upload} className="flex flex-col gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("imports.meter")}>
                <Select
                  value={meterId}
                  onChange={(event) => setMeterId(event.target.value)}
                  required
                  disabled={!canWrite}
                >
                  <option value="">—</option>
                  {(meters.data?.items ?? []).map((meter) => (
                    <option key={meter.id} value={meter.id}>
                      {meter.name} · {meter.serial_number}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={t("imports.reading_type")}>
                <Select
                  value={readingType}
                  onChange={(event) => setReadingType(event.target.value)}
                  disabled={!canWrite}
                >
                  <option value="interval">{t("imports.type_interval")}</option>
                  <option value="cumulative">{t("imports.type_cumulative")}</option>
                </Select>
              </Field>
              <Field
                label={`${t("imports.interval_minutes")} (${t("common.optional")})`}
                htmlFor="i-interval"
              >
                <Input
                  id="i-interval"
                  type="number"
                  min={1}
                  max={1440}
                  placeholder="60"
                  value={intervalMinutes}
                  onChange={(event) => setIntervalMinutes(event.target.value)}
                  disabled={!canWrite}
                />
              </Field>
              <div className="flex items-end pb-2">
                <Toggle
                  checked={decimalComma}
                  onChange={setDecimalComma}
                  label={t("imports.decimal_comma")}
                  disabled={!canWrite}
                />
              </div>
            </div>

            <Field label={t("imports.choose_file")}>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.txt,.tsv,.xlsx"
                disabled={!canWrite}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setJob(null);
                  setResult(null);
                }}
                className="w-full cursor-pointer rounded-lg border border-line bg-bg/60 px-3 py-2 text-[13px] text-muted file:mr-3 file:rounded-md file:border-0 file:bg-surface2 file:px-3 file:py-1.5 file:text-[12px] file:text-ink"
              />
            </Field>

            {file && (
              <p className="text-[11px] text-muted">
                {file.name} · {bytes(file.size)}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" loading={busy === "upload"} disabled={!canWrite || !file || !meterId}>
                {busy === "upload" ? t("imports.uploading") : t("imports.upload")}
              </Button>
              {job && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={revalidate}
                  loading={busy === "validate"}
                  disabled={!file}
                >
                  {t("imports.mapping")} · {t("common.apply")}
                </Button>
              )}
            </div>
            <p className="text-[11px] leading-relaxed text-muted">{t("imports.cumulative_note")}</p>
          </form>
        </Card>

        <Card>
          <CardTitle
            title={t("imports.summary")}
            subtitle={job ? job.filename : t("imports.no_job")}
            action={
              job && (
                <Badge
                  tone={
                    job.status === "confirmed" ? "success" : job.status === "failed" ? "danger" : "primary"
                  }
                >
                  {job.status === "confirmed"
                    ? t("imports.status_confirmed")
                    : job.status === "failed"
                      ? t("imports.status_failed")
                      : t("imports.status_validated")}
                </Badge>
              )
            }
          />
          {!job && <EmptyState title={t("imports.no_job")} body={t("imports.file_hint")} />}

          {job && (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-3">
                <Metric label={t("imports.total_rows")} value={num(job.total_rows, 0, lang)} />
                <Metric label={t("imports.valid_rows")} value={num(job.valid_rows, 0, lang)} tone="success" />
                <Metric label={t("imports.invalid_rows")} value={num(job.invalid_rows, 0, lang)} tone="danger" />
                <Metric label={t("imports.duplicates")} value={num(job.duplicate_rows, 0, lang)} tone="warning" />
                <Metric
                  label={t("imports.missing_intervals")}
                  value={num(job.missing_intervals, 0, lang)}
                  tone="warning"
                />
                <Metric
                  label={t("common.coverage")}
                  value={`${num(
                    job.total_rows ? (job.valid_rows / Math.max(job.total_rows, 1)) * 100 : 0,
                    0,
                    lang,
                  )}%`}
                />
              </div>
              <ProgressBar
                value={job.total_rows ? (job.valid_rows / job.total_rows) * 100 : 0}
                tone={job.invalid_rows > 0 ? "warning" : "success"}
              />

              <div className="rounded-lg border border-line bg-bg/40 p-2.5">
                <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted">
                  {t("imports.mapping")}
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {(
                    [
                      ["timestamp", t("imports.column.timestamp")],
                      ["consumption_kwh", t("imports.column.consumption")],
                      ["register_kwh", t("imports.column.register")],
                      ["interval_minutes", t("imports.column.interval")],
                    ] as const
                  ).map(([key, label]) => (
                    <Field key={key} label={label} htmlFor={`map-${key}`}>
                      <Input
                        id={`map-${key}`}
                        value={mapping[key] ?? ""}
                        onChange={(event) => setMapping({ ...mapping, [key]: event.target.value })}
                        placeholder="—"
                        disabled={job.status === "confirmed"}
                      />
                    </Field>
                  ))}
                </div>
              </div>

              {job.errors.length > 0 && (
                <div className="max-h-32 overflow-y-auto rounded-lg border border-danger/30 bg-danger/5 p-2 text-[11px] text-danger">
                  {job.errors.slice(0, 20).map((raw, index) => {
                    const item = raw as { row: number; message: string };
                    return (
                      <p key={index}>
                        #{item.row}: {item.message}
                      </p>
                    );
                  })}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  onClick={confirm}
                  loading={busy === "confirm"}
                  disabled={job.status === "confirmed" || job.valid_rows === 0 || !canWrite}
                >
                  {t("imports.confirm")}
                </Button>
                {result && (
                  <span className="text-[12px] text-success">
                    {t("imports.inserted")}: {result.inserted} · {t("imports.skipped")}:{" "}
                    {result.skipped_duplicates}
                  </span>
                )}
              </div>
              {result?.message && <p className="text-[11px] text-muted">{result.message}</p>}
            </div>
          )}
        </Card>
      </div>

      {job && job.preview.length > 0 && (
        <Card className="mt-4">
          <CardTitle title={t("imports.preview")} subtitle={`${job.preview.length} ${t("common.rows")}`} />
          <div className="max-h-80 overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <Th>#</Th>
                  <Th>{t("imports.column.timestamp")}</Th>
                  <Th align="right">{t("imports.column.consumption")}</Th>
                  <Th align="right">kW</Th>
                  <Th>{t("common.status")}</Th>
                </tr>
              </thead>
              <tbody>
                {job.preview.map((row) => (
                  <tr key={row.row}>
                    <Td className="text-muted">{row.row}</Td>
                    <Td className="whitespace-nowrap">{row.ts ? dateTime(row.ts, lang) : "—"}</Td>
                    <Td align="right">{row.consumption_kwh === null ? "—" : num(row.consumption_kwh, 2, lang)}</Td>
                    <Td align="right">{row.power_kw === null ? "—" : num(row.power_kw, 1, lang)}</Td>
                    <Td>
                      <Badge
                        tone={
                          row.status === "valid"
                            ? "success"
                            : row.status === "duplicate"
                              ? "warning"
                              : "danger"
                        }
                      >
                        {t(`imports.row_status.${row.status}`)}
                      </Badge>
                      {row.message && <span className="ml-2 text-[11px] text-muted">{row.message}</span>}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>
      )}

      <Card className="mt-4">
        <CardTitle title={t("imports.history")} />
        {history.data && history.data.items.length === 0 && (
          <EmptyState title={t("imports.history_empty")} body={t("imports.file_hint")} />
        )}
        {history.loading && !history.data && <Skeleton className="h-24" />}
        {history.data && history.data.items.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th>{t("reports.filename")}</Th>
                <Th>{t("common.status")}</Th>
                <Th align="right">{t("imports.valid_rows")}</Th>
                <Th align="right">{t("imports.invalid_rows")}</Th>
                <Th>{t("reports.created")}</Th>
              </tr>
            </thead>
            <tbody>
              {history.data.items.map((row) => (
                <tr key={row.id}>
                  <Td className="max-w-[16rem] truncate">{row.filename}</Td>
                  <Td>
                    <Badge
                      tone={row.status === "confirmed" ? "success" : row.status === "failed" ? "danger" : "primary"}
                    >
                      {row.status}
                    </Badge>
                  </Td>
                  <Td align="right">{row.valid_rows}</Td>
                  <Td align="right">{row.invalid_rows}</Td>
                  <Td className="whitespace-nowrap text-muted">{dateTime(row.created_at, lang)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "danger" | "warning";
}) {
  const color =
    tone === "success"
      ? "text-success"
      : tone === "danger"
        ? "text-danger"
        : tone === "warning"
          ? "text-warning"
          : "text-ink";
  return (
    <div className="rounded-lg border border-line/70 bg-bg/40 px-2.5 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-muted">{label}</p>
      <p className={`text-[15px] font-semibold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}
