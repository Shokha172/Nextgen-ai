"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  ErrorState,
  PageHeader,
  Segmented,
  Skeleton,
  Table,
  Td,
  Th,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";

interface ReportItem {
  id: string;
  filename: string;
  kind: string;
  format: "pdf" | "xlsx" | "csv";
  period: string;
  size_bytes: number;
  created_at: string;
}

export default function ReportsPage() {
  const { t, lang } = useI18n();
  const { toast } = useToast();
  const [kind, setKind] = useState("dashboard");
  const [format, setFormat] = useState<"pdf" | "xlsx" | "csv">("pdf");
  const [generating, setGenerating] = useState(false);

  const reports = useResource<{ items: ReportItem[]; total: number }>(
    (signal) => api.get<{ items: ReportItem[]; total: number }>("/reports", { limit: 50 }, signal),
    [],
  );

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await api.post<ReportItem>("/reports", {
        kind,
        format,
        period: "month",
      });
      toast({ title: "Hisobot tayyor!", body: res.filename, tone: "success" });
      void reports.reload();
      // Auto download
      window.open(`/api/v1/reports/${res.id}/download`, "_blank");
    } catch {
      toast({ title: "Xatolik", body: "Hisobotni shakllantirishda xatolik yuz berdi", tone: "danger" });
    } finally {
      setGenerating(false);
    }
  };

  const items = reports.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("nav.reports")}
        subtitle="Rasmiy energetika balansi, hisoblagichlar tafsiloti va anomaliyalar bo‘yicha eksport"
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
            <Button variant="secondary" size="sm" onClick={reports.reload} loading={reports.refreshing}>
              {t("common.refresh")}
            </Button>
          </div>
        }
      />

      {/* Generator Card */}
      <Card className="flex flex-col gap-4">
        <CardTitle
          title="Yangi hisobot generatsiya qilish"
          subtitle="Format va hisobot turini tanlang"
        />
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted">Hisobot turi:</label>
            <Segmented
              value={kind}
              onChange={setKind}
              options={[
                { value: "dashboard", label: "📊 Oylik umumiy balans" },
                { value: "consumption", label: "📈 Iste'mol tahlili" },
                { value: "anomalies", label: "⚠️ Anomaliyalar jurnali" },
                { value: "forecast", label: "🔮 30 kunlik prognoz" },
              ]}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted">Format:</label>
            <Segmented
              value={format}
              onChange={(f) => setFormat(f as "pdf" | "xlsx" | "csv")}
              options={[
                { value: "pdf", label: "PDF Hujjat" },
                { value: "xlsx", label: "Excel (.xlsx)" },
                { value: "csv", label: "CSV Jadval" },
              ]}
            />
          </div>

          <div className="flex items-end pt-5">
            <Button
              variant="primary"
              className="bg-[#155EEF] hover:bg-[#124bbf]"
              onClick={handleGenerate}
              loading={generating}
            >
              📥 Hisobotni shakllantirish va yuklab olish
            </Button>
          </div>
        </div>
      </Card>

      {reports.error && <ErrorState error={reports.error} onRetry={reports.reload} />}

      {/* Reports History */}
      <Card>
        <CardTitle title="Tayyorlangan hisobotlar arxivi" subtitle="Barcha arxivlangan rasmiy hisobotlar" />
        {reports.loading && !reports.data ? (
          <div className="flex flex-col gap-3 p-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 text-center text-xs text-muted">
            Hozircha hisobotlar mavjud emas. Yuqoridagi tugma orqali birinchi hisobotni generatsiya qiling.
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Fayl nomi</Th>
                <Th>Turi</Th>
                <Th>Format</Th>
                <Th>Hajmi</Th>
                <Th>Yaratilgan vaqt</Th>
                <Th align="right">Amal</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="hover:bg-surface2">
                  <Td className="font-medium text-ink">{r.filename}</Td>
                  <Td>
                    <Badge tone="neutral">{r.kind}</Badge>
                  </Td>
                  <Td>
                    <Badge tone={r.format === "pdf" ? "danger" : "success"}>
                      {r.format.toUpperCase()}
                    </Badge>
                  </Td>
                  <Td className="text-muted">{(r.size_bytes / 1024).toFixed(1)} KB</Td>
                  <Td className="whitespace-nowrap text-muted">{dateTime(r.created_at, lang)}</Td>
                  <Td align="right">
                    <a
                      href={`/api/v1/reports/${r.id}/download`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-lg border border-line bg-surface px-3 py-1 text-xs font-semibold text-primary transition-colors hover:bg-primary/5"
                    >
                      Yuklab olish ⬇️
                    </a>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
