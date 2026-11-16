"use client";

import {
  Badge,
  Button,
  Card,
  CardTitle,
  PageHeader,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, moneyCompact } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import type { Member, Organization, Tariff } from "@/lib/types";

export default function SettingsPage() {
  const { t, lang } = useI18n();

  const org = useResource<Organization>((signal) => api.get<Organization>("/organization", {}, signal), []);
  const members = useResource<{ items: Member[] }>((signal) => api.get<{ items: Member[] }>("/members", {}, signal), []);
  const tariffs = useResource<{ items: Tariff[] }>((signal) => api.get<{ items: Tariff[] }>("/tariffs", {}, signal), []);

  const orgData = org.data;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("nav.settings")}
        subtitle="Korxona rekvizitlari, elektr tariflari va a'zolar boshqaruvi"
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                void org.reload();
                void members.reload();
                void tariffs.reload();
              }}
            >
              {t("common.refresh")}
            </Button>
          </div>
        }
      />

      {/* Organization Profile */}
      <Card className="flex flex-col gap-4">
        <CardTitle title="Korxona ma'lumotlari" subtitle="Yuridik va geografik sozlamalar" />
        {orgData ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-line bg-surface p-3">
              <span className="text-xs text-muted">Korxona nomi:</span>
              <p className="mt-1 font-semibold text-ink">{orgData.name}</p>
            </div>
            <div className="rounded-xl border border-line bg-surface p-3">
              <span className="text-xs text-muted">Sanoat sohasi:</span>
              <p className="mt-1 font-semibold text-ink">{orgData.industry || "To'qimachilik / Sanoat"}</p>
            </div>
            <div className="rounded-xl border border-line bg-surface p-3">
              <span className="text-xs text-muted">Vaqt mintaqasi:</span>
              <p className="mt-1 font-semibold text-ink">{orgData.timezone || "Asia/Tashkent (UTC+5)"}</p>
            </div>
            <div className="rounded-xl border border-line bg-surface p-3">
              <span className="text-xs text-muted">Valyuta:</span>
              <p className="mt-1 font-semibold text-primary">{orgData.currency || "UZS"}</p>
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted">Yuklanmoqda…</p>
        )}
      </Card>

      {/* Tariffs Section */}
      <Card>
        <CardTitle title="Elektr energiyasi tariflari" subtitle="Xarajatlarni hisoblash uchun faol tariflar" />
        <Table>
          <thead>
            <tr>
              <Th>Tarif nomi</Th>
              <Th align="right">1 kWh narxi</Th>
              <Th align="right">Cho'qqi koeffitsiyenti</Th>
              <Th align="right">Tungi koeffitsiyent</Th>
              <Th align="right">Holat</Th>
            </tr>
          </thead>
          <tbody>
            {(tariffs.data?.items ?? []).map((tf) => (
              <tr key={tf.id} className="hover:bg-surface2">
                <Td className="font-semibold text-ink">{tf.name}</Td>
                <Td align="right" className="font-bold text-primary">
                  {moneyCompact(Number(tf.price_per_kwh), tf.currency, lang)}/kWh
                </Td>
                <Td align="right" className="text-muted">x{tf.peak_multiplier || "1.0"}</Td>
                <Td align="right" className="text-muted">x{tf.offpeak_multiplier || "1.0"}</Td>
                <Td align="right">
                  <Badge tone={tf.is_default ? "success" : "neutral"}>
                    {tf.is_default ? "Standart tarif" : "Qo'shimcha"}
                  </Badge>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {/* Members Section */}
      <Card>
        <CardTitle title="Tashkilot xodimlari" subtitle="Tizimga kirish huquqiga ega mutaxassislar" />
        <Table>
          <thead>
            <tr>
              <Th>F.I.SH</Th>
              <Th>Email</Th>
              <Th>Rol</Th>
              <Th>Lavozim</Th>
              <Th>Qo'shilgan sana</Th>
            </tr>
          </thead>
          <tbody>
            {(members.data?.items ?? []).map((m) => (
              <tr key={m.id} className="hover:bg-surface2">
                <Td className="font-semibold text-ink">{m.full_name || "Demo Owner"}</Td>
                <Td className="text-muted">{m.email || m.invited_email || "demo@nextgen.uz"}</Td>
                <Td>
                  <Badge tone={m.role === "owner" ? "primary" : m.role === "admin" ? "accent" : "neutral"}>
                    {m.role.toUpperCase()}
                  </Badge>
                </Td>
                <Td className="text-muted">{m.title || "Energiya menejeri"}</Td>
                <Td className="whitespace-nowrap text-muted">{dateTime(m.created_at, lang)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
