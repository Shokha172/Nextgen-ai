"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  Textarea,
  useToast,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, energy, num } from "@/lib/format";
import { useDebounced, useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import type { Meter } from "@/lib/types";

interface MeterPage {
  items: Meter[];
  total: number;
  page: number;
  page_size: number;
}

const EMPTY_FORM = {
  name: "",
  serial_number: "",
  department: "",
  location: "",
  interval_minutes: "60",
  max_power_kw: "",
  notes: "",
};

export default function MetersPage() {
  const { t, lang } = useI18n();
  const { can } = useAuth();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const debouncedSearch = useDebounced(search, 350);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const meters = useResource<MeterPage>(
    (signal) =>
      api.get<MeterPage>(
        "/meters",
        { search: debouncedSearch || undefined, status: status || undefined, page_size: 200 },
        signal,
      ),
    [debouncedSearch, status],
  );

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await api.post("/meters", {
        name: form.name.trim(),
        serial_number: form.serial_number.trim(),
        department: form.department.trim() || null,
        location: form.location.trim() || null,
        interval_minutes: Number(form.interval_minutes) || 60,
        max_power_kw: form.max_power_kw ? Number(form.max_power_kw) : null,
        notes: form.notes.trim() || null,
      });
      toast.success(t("meters.created"));
      setOpen(false);
      setForm(EMPTY_FORM);
      meters.reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err : new ApiError("error", 0));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={t("meters.title")}
        subtitle={t("meters.subtitle")}
        actions={
          can("analyst") ? (
            <Button size="sm" onClick={() => setOpen(true)}>
              {t("meters.add")}
            </Button>
          ) : undefined
        }
      />

      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t("common.search")} className="min-w-[14rem] flex-1">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("meters.search_placeholder")}
            />
          </Field>
          <Field label={t("meters.filter_status")} className="w-40">
            <Select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">{t("common.all")}</option>
              <option value="active">{t("meters.active")}</option>
              <option value="inactive">{t("meters.inactive")}</option>
            </Select>
          </Field>
          <Button variant="ghost" size="sm" onClick={meters.reload} loading={meters.refreshing}>
            {t("common.refresh")}
          </Button>
        </div>
      </Card>

      {meters.error && <ErrorState error={meters.error} onRetry={meters.reload} />}

      {meters.loading && !meters.data && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-12" />
          ))}
        </div>
      )}

      {meters.data && meters.data.items.length === 0 && (
        <Card>
          <EmptyState
            title={t("meters.empty_title")}
            body={t("meters.empty_body")}
            action={
              can("analyst") ? (
                <Button size="sm" onClick={() => setOpen(true)}>
                  {t("meters.add")}
                </Button>
              ) : (
                <Link href="/imports">
                  <Button size="sm" variant="secondary">
                    {t("dashboard.no_data_cta")}
                  </Button>
                </Link>
              )
            }
          />
        </Card>
      )}

      {meters.data && meters.data.items.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                <Th>{t("common.name")}</Th>
                <Th>{t("meters.serial")}</Th>
                <Th>{t("common.department")}</Th>
                <Th align="right">{t("meters.interval")}</Th>
                <Th align="right">{t("meters.readings_count")}</Th>
                <Th align="right">{t("meters.lifetime_energy")}</Th>
                <Th>{t("meters.last_reading")}</Th>
                <Th>{t("common.status")}</Th>
              </tr>
            </thead>
            <tbody>
              {meters.data.items.map((meter) => (
                <tr key={meter.id} className="hover:bg-surface2/40">
                  <Td>
                    <Link
                      href={`/meters/${meter.id}`}
                      className="font-medium text-ink underline-offset-2 hover:text-accent hover:underline"
                    >
                      {meter.name}
                    </Link>
                    {meter.location && (
                      <span className="block text-[11px] text-muted">{meter.location}</span>
                    )}
                  </Td>
                  <Td className="font-mono text-[12px] text-muted">{meter.serial_number}</Td>
                  <Td className="text-muted">{meter.department ?? "—"}</Td>
                  <Td align="right">{meter.interval_minutes}</Td>
                  <Td align="right">{meter.readings ?? 0}</Td>
                  <Td align="right">{energy(meter.total_kwh ?? 0, lang)}</Td>
                  <Td className="whitespace-nowrap text-muted">
                    {meter.last_reading_at ? dateTime(meter.last_reading_at, lang) : "—"}
                  </Td>
                  <Td>
                    <Badge tone={meter.status === "active" ? "success" : "neutral"}>
                      {meter.status === "active" ? t("meters.active") : t("meters.inactive")}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p className="mt-3 text-[11px] text-muted">
            {meters.data.total} {t("common.total").toLowerCase()} · {t("meters.energy_vs_power")}
          </p>
        </Card>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={t("meters.add")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" form="meter-form" loading={saving}>
              {t("common.create")}
            </Button>
          </>
        }
      >
        <form id="meter-form" onSubmit={submit} className="flex flex-col gap-3">
          <Field label={t("common.name")} htmlFor="m-name">
            <Input
              id="m-name"
              required
              minLength={2}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("meters.serial")} htmlFor="m-serial">
              <Input
                id="m-serial"
                required
                value={form.serial_number}
                onChange={(event) => setForm({ ...form, serial_number: event.target.value })}
              />
            </Field>
            <Field label={`${t("common.department")} (${t("common.optional")})`} htmlFor="m-dept">
              <Input
                id="m-dept"
                value={form.department}
                onChange={(event) => setForm({ ...form, department: event.target.value })}
              />
            </Field>
            <Field label={`${t("meters.location")} (${t("common.optional")})`} htmlFor="m-loc">
              <Input
                id="m-loc"
                value={form.location}
                onChange={(event) => setForm({ ...form, location: event.target.value })}
              />
            </Field>
            <Field label={t("meters.interval")} htmlFor="m-interval">
              <Input
                id="m-interval"
                type="number"
                min={1}
                max={1440}
                value={form.interval_minutes}
                onChange={(event) => setForm({ ...form, interval_minutes: event.target.value })}
              />
            </Field>
            <Field
              label={`${t("meters.max_power")} (${t("common.optional")})`}
              htmlFor="m-maxpower"
            >
              <Input
                id="m-maxpower"
                type="number"
                step="0.1"
                min={0}
                value={form.max_power_kw}
                onChange={(event) => setForm({ ...form, max_power_kw: event.target.value })}
              />
            </Field>
          </div>
          <Field label={`${t("meters.notes")} (${t("common.optional")})`} htmlFor="m-notes">
            <Textarea
              id="m-notes"
              rows={2}
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
            />
          </Field>
          {formError && <ErrorState error={formError} compact />}
        </form>
      </Modal>
    </div>
  );
}
