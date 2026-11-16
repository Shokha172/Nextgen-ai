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
import { energy, moneyCompact } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

interface Measure {
  id: string;
  name: string;
  category: string;
  annual_kwh_saved: number;
  annual_cost_saved_uzs: number;
  est_investment_uzs: number;
  payback_months: number;
  risk: "past" | "o'rta" | "yuqori";
  status: "identifikatsiya" | "amalga_oshirilmoqda" | "yakunlangan";
}

const MEASURES: Measure[] = [
  {
    id: "m-01",
    name: "Tsex va omborxonalarni LED yoritish tizimiga to‘liq modernizatsiya qilish",
    category: "Yoritish",
    annual_kwh_saved: 42000,
    annual_cost_saved_uzs: 18900000,
    est_investment_uzs: 24000000,
    payback_months: 15,
    risk: "past",
    status: "amalga_oshirilmoqda",
  },
  {
    id: "m-02",
    name: "Asosiy nasos va ventilyatsiya dvigatellariga chastota o‘zgartirgichlar (VFD) o‘rnatish",
    category: "Elektromotorlar",
    annual_kwh_saved: 86500,
    annual_cost_saved_uzs: 38925000,
    est_investment_uzs: 55000000,
    payback_months: 17,
    risk: "past",
    status: "identifikatsiya",
  },
  {
    id: "m-03",
    name: "Kechki cho‘qqi (18:00 - 22:00) yuklamasini yarim tunga (23:00 - 06:00) ko‘chirish (Load Shifting)",
    category: "Tarif optimallashuvi",
    annual_kwh_saved: 24000,
    annual_cost_saved_uzs: 21600000,
    est_investment_uzs: 0,
    payback_months: 0,
    risk: "o'rta",
    status: "amalga_oshirilmoqda",
  },
  {
    id: "m-04",
    name: "Transformator podstansiyasida avtomatik reaktiv quvvat kompensatori (UKRM) o‘rnatish",
    category: "Quvvat sifati",
    annual_kwh_saved: 31200,
    annual_cost_saved_uzs: 14040000,
    est_investment_uzs: 18000000,
    payback_months: 15,
    risk: "past",
    status: "identifikatsiya",
  },
];

export default function SavingsPage() {
  const { t, lang } = useI18n();

  const totalSavedKwh = MEASURES.reduce((acc, m) => acc + m.annual_kwh_saved, 0);
  const totalSavedUzs = MEASURES.reduce((acc, m) => acc + m.annual_cost_saved_uzs, 0);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("savings.title")}
        subtitle="Deterministik hisob-kitoblar va investitsiya qoplanish tahlili"
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
          </div>
        }
      />

      {/* KPI Cards */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Card className="flex flex-col gap-1">
          <span className="text-[11px] font-medium uppercase text-muted">Yillik potensial tejamkorlik</span>
          <span className="text-2xl font-bold text-success">{energy(totalSavedKwh, lang)}</span>
          <span className="text-[11px] text-muted">Hisoblangan 4 ta chora-tadbir bo‘yicha</span>
        </Card>

        <Card className="flex flex-col gap-1">
          <span className="text-[11px] font-medium uppercase text-muted">Kutilayotgan moliyaviy samaradorlik</span>
          <span className="text-2xl font-bold text-primary">
            {moneyCompact(totalSavedUzs, "UZS", lang)}
          </span>
          <span className="text-[11px] text-muted">450 UZS/kWh bazaviy tarif bo‘yicha</span>
        </Card>

        <Card className="flex flex-col gap-1">
          <span className="text-[11px] font-medium uppercase text-muted">O‘rtacha qoplanish davri</span>
          <span className="text-2xl font-bold text-ink">11.8 oy</span>
          <span className="text-[11px] text-muted">Kapital xarajatlar amortizatsiyasi</span>
        </Card>
      </div>

      {/* Opportunities Table */}
      <Card>
        <CardTitle
          title="Tavsiya etilgan energiya tejovchi tadbirlar"
          subtitle="Tizim aniqlagan yo‘qotishlar va anomaliyalar asosida shakllantirilgan"
        />
        <Table>
          <thead>
            <tr>
              <Th>Tadbir nomi</Th>
              <Th>Kategoriya</Th>
              <Th align="right">Yillik tejamkorlik</Th>
              <Th align="right">Yillik iqtisod</Th>
              <Th align="right">Qoplanish</Th>
              <Th align="right">Holat</Th>
            </tr>
          </thead>
          <tbody>
            {MEASURES.map((m) => (
              <tr key={m.id} className="hover:bg-surface2">
                <Td className="font-medium text-ink max-w-md">{m.name}</Td>
                <Td>
                  <Badge tone="neutral">{m.category}</Badge>
                </Td>
                <Td align="right" className="font-semibold text-success">
                  {energy(m.annual_kwh_saved, lang)}
                </Td>
                <Td align="right" className="font-medium text-primary">
                  {moneyCompact(m.annual_cost_saved_uzs, "UZS", lang)}
                </Td>
                <Td align="right" className="text-muted">
                  {m.payback_months === 0 ? "Darhol (0 oy)" : `${m.payback_months} oy`}
                </Td>
                <Td align="right">
                  <Badge tone={m.status === "amalga_oshirilmoqda" ? "warning" : "neutral"}>
                    {m.status === "amalga_oshirilmoqda" ? "Jarayonda" : "Rejalashtirilgan"}
                  </Badge>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {/* Verification Notice */}
      <Card className="border border-line/80 bg-surface2/30 p-4 text-[12px] leading-relaxed text-muted">
        <p className="font-semibold text-ink">Xalqaro standart eslatmasi (ISO 50001 / IPMVP):</p>
        <p className="mt-1">
          Haqiqiy tejamkorlikni baholash uchun bazaviy davr (baseline) o‘rnatilishi va ishlab chiqarish hajmi hamda ob-havo o‘zgaruvchilari bo‘yicha normallashtirilishi shart. NEXTGEN AI kafolatlanmagan tejamkorlik da'vo qilmaydi.
        </p>
      </Card>
    </div>
  );
}
