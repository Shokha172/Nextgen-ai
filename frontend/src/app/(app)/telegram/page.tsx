"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  PageHeader,
  Table,
  Td,
  Th,
  useToast,
} from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";

interface TelegramAccount {
  id: string;
  telegram_user_id: number;
  telegram_username: string | null;
  language: string;
  is_demo: boolean;
  alerts_enabled: boolean;
  created_at: string;
}

export default function TelegramPage() {
  const { lang } = useI18n();
  const { toast } = useToast();
  const [linkingCode, setLinkingCode] = useState<string | null>(null);
  const [generatingCode, setGeneratingCode] = useState(false);

  const accounts = useResource<{ items: TelegramAccount[] }>(
    (signal) => api.get<{ items: TelegramAccount[] }>("/telegram/accounts", {}, signal),
    [],
  );

  const handleGenerateCode = async () => {
    setGeneratingCode(true);
    try {
      const res = await api.post<{ code: string; expires_at: string }>("/telegram/link");
      setLinkingCode(res.code);
      toast({ title: "Ulanish kodi yaratildi!", body: `Kod: ${res.code}`, tone: "success" });
    } catch {
      toast({ title: "Xatolik", body: "Kod yaratishda xatolik yuz berdi", tone: "danger" });
    } finally {
      setGeneratingCode(false);
    }
  };

  const handleRevoke = async (id: string) => {
    try {
      await api.delete(`/telegram/accounts/${id}`);
      toast({ title: "Hisob uzildi", tone: "neutral" });
      void accounts.reload();
    } catch {
      toast({ title: "Xatolik", body: "Uzishda xatolik yuz berdi", tone: "danger" });
    }
  };

  const items = accounts.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Telegram Bot Integratsiyasi"
        subtitle="Rasmiy va Demo Telegram bot orqali korxona energetika ma'lumotlarini kuzating"
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
            <Button variant="secondary" size="sm" onClick={accounts.reload} loading={accounts.refreshing}>
              Yangilash
            </Button>
          </div>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        {/* Link Instructions */}
        <Card className="flex flex-col gap-4">
          <CardTitle
            title="Hisobni Telegram Botga ulash"
            subtitle="3 bosqichda xavfsiz bir martalik kod orqali ulaning"
          />

          <div className="flex flex-col gap-3 text-[13px] leading-relaxed text-muted">
            <div className="flex items-start gap-2.5">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                1
              </span>
              <span>
                Telegramda rasmiy <strong>@nextgenuzz_bot</strong> botiga kiring yoki quyidagi tugmani bosing:
              </span>
            </div>

            <div className="pl-8">
              <a
                href="https://t.me/nextgenuzz_bot"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-xl bg-[#155EEF] px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-[#124bbf]"
              >
                <span>Telegram Botni ochish (@nextgenuzz_bot)</span>
                <span>↗</span>
              </a>
            </div>

            <div className="flex items-start gap-2.5">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                2
              </span>
              <span>Quyidagi tugma orqali bir martalik 6 xonali ulanish kodini generatsiya qiling:</span>
            </div>

            <div className="pl-8">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleGenerateCode}
                loading={generatingCode}
              >
                🔑 Bir martalik kod yaratish
              </Button>
            </div>

            {linkingCode && (
              <div className="ml-8 mt-1 flex flex-col gap-2 rounded-xl border border-primary/30 bg-primary/5 p-4">
                <span className="text-xs text-muted">Sizning bir martalik ulanish kodingiz (amal qilish muddati: 10 daqiqa):</span>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-2xl font-bold tracking-widest text-primary">
                    {linkingCode}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      navigator.clipboard.writeText(`/start ${linkingCode}`);
                      toast({ title: "Nusxalandi!", tone: "success" });
                    }}
                  >
                    Nusxa olish
                  </Button>
                </div>
                <span className="text-[11px] text-muted">
                  Botga kirib: <code className="bg-surface px-1.5 py-0.5 rounded font-mono text-ink">/start {linkingCode}</code> deb yozing.
                </span>
              </div>
            )}

            <div className="flex items-start gap-2.5">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                3
              </span>
              <span>
                Bot hisobingizni tasdiqlaydi va sizga shaxsiy korxona kabinetingiz, anomaliya ogohlantirishlari va AI hisobotlarini taqdim etadi.
              </span>
            </div>
          </div>
        </Card>

        {/* Bot Features Card */}
        <Card className="flex flex-col gap-3">
          <CardTitle title="Bot imkoniyatlari" subtitle="24/7 operativ nazorat" />
          <ul className="flex flex-col gap-2.5 text-[12px] text-muted">
            <li className="flex items-start gap-2">
              <span className="text-primary font-bold">✓</span>
              <span><strong>Dashboard:</strong> Har soatlik va kunlik elektr iste'moli balansi.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary font-bold">✓</span>
              <span><strong>Operativ xabarlar:</strong> Anomaliya yoki ruxsatsiz quvvat oshganda lahzali ogohlantirish.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary font-bold">✓</span>
              <span><strong>AI savol-javob:</strong> Har qanday tahliliy savolga deterministik aniq javoblar.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary font-bold">✓</span>
              <span><strong>6 ta til:</strong> O'zbek, Rus, Ingliz, Qozoq, Turk va Qirg'iz tillarida.</span>
            </li>
          </ul>
        </Card>
      </div>

      {/* Linked Accounts List */}
      <Card>
        <CardTitle title="Ulangan Telegram hisoblari" subtitle="Tashkilotga bog'langan bot foydalanuvchilari" />
        {items.length === 0 ? (
          <div className="py-10 text-center text-xs text-muted">
            Hozircha ulangan hisoblar yo‘q. Yuqoridagi ko‘rsatma orqali botni ulang.
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Telegram User ID</Th>
                <Th>Foydalanuvchi nomi</Th>
                <Th>Til</Th>
                <Th>Holat</Th>
                <Th>Uzlangan sana</Th>
                <Th align="right">Amal</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((acc) => (
                <tr key={acc.id} className="hover:bg-surface2">
                  <Td className="font-mono text-xs font-semibold text-ink">{acc.telegram_user_id}</Td>
                  <Td className="text-muted">{acc.telegram_username ? `@${acc.telegram_username}` : "—"}</Td>
                  <Td>
                    <Badge tone="neutral">{acc.language.toUpperCase()}</Badge>
                  </Td>
                  <Td>
                    <Badge tone="success">Faol</Badge>
                  </Td>
                  <Td className="whitespace-nowrap text-muted">{dateTime(acc.created_at, lang)}</Td>
                  <Td align="right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-danger hover:bg-danger/10"
                      onClick={() => void handleRevoke(acc.id)}
                    >
                      Uzish
                    </Button>
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
