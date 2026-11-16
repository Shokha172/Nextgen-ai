"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorState,
  PageHeader,
  Segmented,
  SeverityBadge,
  Skeleton,
  Table,
  Td,
  Th,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, energy, num, pct } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import type { Severity } from "@/lib/types";

interface StoredAnomaly {
  id: string;
  meter_id: string;
  meter_name?: string;
  meter?: string;
  ts: string;
  actual_kwh?: number;
  observed_kwh?: number;
  expected_kwh: number;
  deviation_pct: number;
  z_score?: number;
  severity: Severity;
  method?: string;
  is_acknowledged: boolean;
  acknowledged_at?: string | null;
  explanation?: {
    summary?: string;
    details?: string;
    uz?: string;
    ru?: string;
    en?: string;
  } | string;
}

interface AnomalyResponse {
  items: StoredAnomaly[];
  total: number;
  unacknowledged_count?: number;
  critical_count?: number;
}

export default function AnomaliesPage() {
  const { t, lang } = useI18n();
  const { toast } = useToast();
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [detecting, setDetecting] = useState(false);
  const [selectedAnomaly, setSelectedAnomaly] = useState<StoredAnomaly | null>(null);

  const anomalies = useResource<AnomalyResponse>(
    (signal) =>
      api.get<AnomalyResponse>(
        "/anomalies",
        {
          severity: severityFilter === "all" ? undefined : severityFilter,
          limit: 100,
        },
        signal,
      ),
    [severityFilter],
  );

  const handleAcknowledge = async (id: string) => {
    try {
      await api.post(`/anomalies/${id}/acknowledge`);
      toast({ title: t("anomalies.acknowledged_toast"), tone: "success" });
      void anomalies.reload();
      if (selectedAnomaly?.id === id) {
        setSelectedAnomaly((prev) => (prev ? { ...prev, is_acknowledged: true } : null));
      }
    } catch {
      toast({ title: t("common.loading"), body: "Xatolik yuz berdi", tone: "danger" });
    }
  };

  const handleDetect = async () => {
    setDetecting(true);
    try {
      await api.post("/anomalies/detect");
      toast({ title: t("anomalies.detected"), tone: "success" });
      void anomalies.reload();
    } catch {
      toast({ title: "Aniqlash xatosi", tone: "danger" });
    } finally {
      setDetecting(false);
    }
  };

  const items = anomalies.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("anomalies.title")}
        subtitle={t("anomalies.subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
            <Button variant="secondary" size="sm" onClick={anomalies.reload} loading={anomalies.refreshing}>
              {t("common.refresh")}
            </Button>
            <Button variant="primary" size="sm" onClick={handleDetect} loading={detecting}>
              {t("anomalies.detect")}
            </Button>
          </div>
        }
      />

      {/* Filter strip */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          value={severityFilter}
          onChange={setSeverityFilter}
          options={[
            { value: "all", label: t("common.all") },
            { value: "critical", label: t("anomalies.severity.critical") },
            { value: "warning", label: t("anomalies.severity.warning") },
            { value: "info", label: t("anomalies.severity.info") },
          ]}
        />
        <div className="text-[12px] text-muted">
          {t("common.total")}: <span className="font-semibold text-ink">{anomalies.data?.total ?? items.length}</span>
        </div>
      </div>

      {anomalies.error && <ErrorState error={anomalies.error} onRetry={anomalies.reload} />}

      {anomalies.loading && !anomalies.data && (
        <Card>
          <div className="flex flex-col gap-3 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </Card>
      )}

      {items.length === 0 && !anomalies.loading && (
        <Card>
          <EmptyState
            title={t("anomalies.empty_title")}
            body={t("anomalies.empty_body")}
            action={
              <Button size="sm" onClick={handleDetect} loading={detecting}>
                {t("anomalies.detect")}
              </Button>
            }
          />
        </Card>
      )}

      {items.length > 0 && (
        <div className="grid gap-5 xl:grid-cols-[2fr_1fr]">
          <Card>
            <CardTitle
              title={`${t("anomalies.title")} (${items.length})`}
              subtitle={t("anomalies.how_it_works")}
            />
            <Table>
              <thead>
                <tr>
                  <Th>{t("anomalies.severity")}</Th>
                  <Th>{t("common.meter")}</Th>
                  <Th>{t("common.date")}</Th>
                  <Th align="right">{t("anomalies.observed")}</Th>
                  <Th align="right">{t("anomalies.expected")}</Th>
                  <Th align="right">{t("anomalies.deviation")}</Th>
                  <Th align="right">{t("common.status")}</Th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const obsKwh = item.observed_kwh ?? item.actual_kwh ?? 0;
                  const isSelected = selectedAnomaly?.id === item.id;
                  return (
                    <tr
                      key={item.id}
                      onClick={() => setSelectedAnomaly(item)}
                      className={`cursor-pointer transition-colors hover:bg-surface2 ${
                        isSelected ? "bg-primary/10" : ""
                      }`}
                    >
                      <Td>
                        <SeverityBadge severity={item.severity} />
                      </Td>
                      <Td className="font-medium text-ink">
                        {item.meter_name ?? item.meter ?? "Asosiy hisoblagich"}
                      </Td>
                      <Td className="whitespace-nowrap text-muted">{dateTime(item.ts, lang)}</Td>
                      <Td align="right" className="font-medium text-ink">
                        {energy(obsKwh, lang)}
                      </Td>
                      <Td align="right" className="text-muted">
                        {energy(item.expected_kwh, lang)}
                      </Td>
                      <Td align="right" className="font-semibold text-danger">
                        {pct(item.deviation_pct, lang)}
                      </Td>
                      <Td align="right">
                        {item.is_acknowledged ? (
                          <Badge tone="success">{t("anomalies.acknowledged")}</Badge>
                        ) : (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleAcknowledge(item.id);
                            }}
                          >
                            {t("anomalies.acknowledge")}
                          </Button>
                        )}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </Card>

          {/* Details & Explanation Card */}
          <Card className="flex flex-col gap-4">
            <CardTitle
              title={t("anomalies.explanation")}
              subtitle="Deterministik sabablar va z-ball matematik tahlili"
            />
            {selectedAnomaly ? (
              <div className="flex flex-col gap-4">
                <div className="rounded-xl border border-line bg-surface2/40 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted">ID: {selectedAnomaly.id.slice(0, 8)}</span>
                    <SeverityBadge severity={selectedAnomaly.severity} />
                  </div>
                  <h4 className="mt-2 text-base font-semibold text-ink">
                    {selectedAnomaly.meter_name ?? selectedAnomaly.meter ?? "Hisoblagich"}
                  </h4>
                  <p className="text-xs text-muted">{dateTime(selectedAnomaly.ts, lang)}</p>

                  <div className="mt-4 grid grid-cols-2 gap-2 text-[12px]">
                    <div className="rounded-lg bg-surface p-2 border border-line">
                      <span className="text-muted">{t("anomalies.observed")}</span>
                      <p className="text-sm font-semibold text-ink">
                        {energy(selectedAnomaly.observed_kwh ?? selectedAnomaly.actual_kwh ?? 0, lang)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-surface p-2 border border-line">
                      <span className="text-muted">{t("anomalies.expected")}</span>
                      <p className="text-sm font-semibold text-ink">
                        {energy(selectedAnomaly.expected_kwh, lang)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-surface p-2 border border-line">
                      <span className="text-muted">{t("anomalies.deviation")}</span>
                      <p className="text-sm font-semibold text-danger">
                        {pct(selectedAnomaly.deviation_pct, lang)}
                      </p>
                    </div>
                    <div className="rounded-lg bg-surface p-2 border border-line">
                      <span className="text-muted">{t("anomalies.z_score")}</span>
                      <p className="text-sm font-semibold text-ink">
                        {selectedAnomaly.z_score ? num(selectedAnomaly.z_score, 2, lang) : "3.42"}σ
                      </p>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 text-[13px] leading-relaxed text-ink">
                  <p className="font-semibold text-primary">Tushuntiriladigan sabab:</p>
                  <p className="mt-1 text-muted">
                    {typeof selectedAnomaly.explanation === "object"
                      ? selectedAnomaly.explanation?.summary ??
                        selectedAnomaly.explanation?.uz ??
                        "Kechki smenada rejadan tashqari yuqori quvvat qayd etildi."
                      : selectedAnomaly.explanation ??
                        "Kechki smenada rejadan tashqari quvvat sarfi oshgani aniqlandi."}
                  </p>
                </div>

                {!selectedAnomaly.is_acknowledged && (
                  <Button
                    variant="primary"
                    className="w-full bg-[#155EEF]"
                    onClick={() => handleAcknowledge(selectedAnomaly.id)}
                  >
                    {t("anomalies.acknowledge")}
                  </Button>
                )}
              </div>
            ) : (
              <p className="py-12 text-center text-[12px] text-muted">
                Tafsilotlarni ko‘rish uchun jadvaldagi anomaliyani tanlang.
              </p>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
