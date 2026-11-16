"use client";

import Link from "next/link";
import { useState } from "react";
import { LANGS, useI18n } from "@/lib/i18n";
import { Logo } from "@/components/shell";
import { Button, Card, Badge, cx } from "@/components/ui";

export default function LandingPage() {
  const { lang, setLang, t } = useI18n();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#F5F8FC] text-[#172B4D] selection:bg-[#155EEF]/20">
      {/* Official State / Enterprise Top Ribbon */}
      <div className="border-b border-[#E4EAF2] bg-[#123B72] px-4 py-1.5 text-xs text-white/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-[#12A66A]" />
            <span className="font-medium tracking-wide">
              O‘zbekiston Respublikasi Sanoat va Energetika Korxonalari Uchun Rasmiy Platforma
            </span>
          </div>
          <div className="hidden items-center gap-4 text-white/80 sm:flex">
            <span>Standart: O‘zDst / ISO 50001</span>
            <span className="text-white/40">|</span>
            <span>Toshkent vaqti: UTC+5</span>
          </div>
        </div>
      </div>

      {/* Main Navigation Header */}
      <header className="sticky top-0 z-40 border-b border-[#E4EAF2] bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#155EEF] text-base font-bold text-white shadow-sm">
                N
              </span>
              <div className="flex flex-col">
                <span className="text-base font-bold tracking-tight text-[#123B72]">NEXTGEN AI</span>
                <span className="text-[10px] font-semibold tracking-wider text-[#667085] uppercase">
                  Energy Intelligence
                </span>
              </div>
            </Link>

            <nav className="hidden items-center gap-6 text-sm font-medium text-[#667085] lg:flex">
              <a href="#features" className="transition-colors hover:text-[#155EEF]">
                Imkoniyatlar
              </a>
              <a href="#how-it-works" className="transition-colors hover:text-[#155EEF]">
                Qanday ishlaydi
              </a>
              <a href="#industries" className="transition-colors hover:text-[#155EEF]">
                Sohalar
              </a>
              <a href="#ai-safety" className="transition-colors hover:text-[#155EEF]">
                AI va Xavfsizlik
              </a>
              <a href="#contact" className="transition-colors hover:text-[#155EEF]">
                Aloqa
              </a>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {/* 6-Language Selector Pill */}
            <div className="hidden items-center gap-0.5 rounded-lg border border-[#E4EAF2] bg-[#F5F8FC] p-1 sm:flex">
              {LANGS.map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => setLang(item.code)}
                  className={cx(
                    "rounded px-2 py-0.5 text-xs font-semibold transition-all",
                    lang === item.code
                      ? "bg-[#155EEF] text-white shadow-xs"
                      : "text-[#667085] hover:text-[#172B4D]",
                  )}
                  title={item.label}
                >
                  {item.short}
                </button>
              ))}
            </div>

            <Link href="/login">
              <Button variant="secondary" size="sm" className="hidden font-medium sm:inline-flex">
                Kirish
              </Button>
            </Link>

            <Link href="/dashboard">
              <Button variant="primary" size="sm" className="bg-[#155EEF] shadow-sm hover:bg-[#124bbf]">
                DEMO Sinov
              </Button>
            </Link>

            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="grid h-9 w-9 place-items-center rounded-lg border border-[#E4EAF2] lg:hidden"
              aria-label="Menyu"
            >
              <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 6h12M4 12h12M4 18h12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile dropdown */}
        {mobileMenuOpen && (
          <div className="border-t border-[#E4EAF2] bg-white px-4 py-4 lg:hidden">
            <nav className="flex flex-col gap-3 text-sm font-medium">
              <a href="#features" onClick={() => setMobileMenuOpen(false)}>
                Imkoniyatlar
              </a>
              <a href="#how-it-works" onClick={() => setMobileMenuOpen(false)}>
                Qanday ishlaydi
              </a>
              <a href="#industries" onClick={() => setMobileMenuOpen(false)}>
                Sohalar
              </a>
              <a href="#ai-safety" onClick={() => setMobileMenuOpen(false)}>
                AI va Xavfsizlik
              </a>
              <a href="#contact" onClick={() => setMobileMenuOpen(false)}>
                Aloqa
              </a>
            </nav>
            <div className="mt-4 flex flex-wrap gap-1 border-t border-[#E4EAF2] pt-3">
              {LANGS.map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => setLang(item.code)}
                  className={cx(
                    "rounded px-2.5 py-1 text-xs font-semibold",
                    lang === item.code ? "bg-[#155EEF] text-white" : "bg-[#F5F8FC] text-[#667085]",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden border-b border-[#E4EAF2] bg-gradient-to-b from-white via-white to-[#F5F8FC] px-4 py-16 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12">
            <div className="flex flex-col items-start lg:col-span-7">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-[#155EEF]/20 bg-[#155EEF]/5 px-3 py-1 text-xs font-semibold text-[#155EEF]">
                <span className="h-1.5 w-1.5 rounded-full bg-[#155EEF]" />
                O‘ZBEKISTON KORXONALARI UCHUN ENERGETIKA INTELEKTI
              </div>

              <h1 className="text-3xl font-extrabold tracking-tight text-[#123B72] sm:text-4xl lg:text-5xl">
                Intelligent Energy Management for a Smarter Future
              </h1>

              <p className="mt-4 text-base leading-relaxed text-[#667085] sm:text-lg">
                NEXTGEN AI elektr energiyasi iste’mol ma’lumotlarini tushunarli biznes-tahlilga aylantiradi.
                Noodatiy ortiqcha yuklamalarni aniqlang, O‘zbekiston sanoat tariflari bo‘yicha xarajatlarni prognozlang
                va dalillarga asoslangan energiya samaradorligiga erishing.
              </p>

              {/* Action Buttons */}
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link href="/dashboard">
                  <Button
                    variant="primary"
                    size="md"
                    className="h-11 bg-[#155EEF] px-6 text-sm font-semibold shadow-md hover:bg-[#124bbf]"
                  >
                    ⚡ Interaktiv DEMO-ni Ochish
                  </Button>
                </Link>
                <Link href="/login">
                  <Button
                    variant="secondary"
                    size="md"
                    className="h-11 border-[#E4EAF2] bg-white px-6 text-sm font-semibold text-[#172B4D] hover:bg-[#F5F8FC]"
                  >
                    Tizimga Kirish
                  </Button>
                </Link>
              </div>

              {/* Ethical Transparency Note */}
              <div className="mt-8 rounded-lg border border-[#E4EAF2] bg-[#F5F8FC] p-3.5 text-xs text-[#667085]">
                <div className="flex items-center gap-2 font-semibold text-[#123B72]">
                  <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="8" cy="8" r="7" />
                    <path d="M8 5v4m0 3v.01" />
                  </svg>
                  <span>Qat’iy Ishonchlilik va Ochiqlik Tamoyili:</span>
                </div>
                <p className="mt-1 leading-normal">
                  Kafolatlangan tejamkorlik va’da qilinmaydi. Sun’iy ko‘rsatkichlar real korxona natijasi sifatida
                  taqdim etilmaydi. Har bir xulosa 100% deterministik hisob-kitoblar va o‘lchangan dalillarga tayanadi.
                </p>
              </div>
            </div>

            {/* Interactive Preview Mockup */}
            <div className="lg:col-span-5">
              <div className="rounded-xl border border-[#E4EAF2] bg-white p-5 shadow-lg">
                <div className="mb-4 flex items-center justify-between border-b border-[#E4EAF2] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full bg-[#12A66A]" />
                    <span className="text-xs font-bold uppercase tracking-wider text-[#123B72]">
                      Jonli Tahlil Paneli
                    </span>
                  </div>
                  <Badge tone="warning">Sintetik DEMO</Badge>
                </div>

                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg border border-[#E4EAF2] bg-[#F5F8FC] p-3">
                      <span className="text-[11px] font-semibold text-[#667085]">Jami Iste’mol (Oylik)</span>
                      <p className="mt-1 text-lg font-bold text-[#123B72]">1 248 500 kWh</p>
                      <span className="text-[10px] text-[#12A66A] font-medium">↑ 2.4% o‘tgan oyga nisbatan</span>
                    </div>
                    <div className="rounded-lg border border-[#E4EAF2] bg-[#F5F8FC] p-3">
                      <span className="text-[11px] font-semibold text-[#667085]">Hisoblangan Xarajat</span>
                      <p className="mt-1 text-lg font-bold text-[#123B72]">561 825 000 UZS</p>
                      <span className="text-[10px] text-[#667085]">Tarif: 450 UZS/kWh</span>
                    </div>
                  </div>

                  <div className="rounded-lg border border-[#E4EAF2] bg-white p-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-[#172B4D]">Pik Yuklama Soati (18:00 - 22:00)</span>
                      <span className="font-bold text-[#D92D20]">420.5 kW</span>
                    </div>
                    <div className="mt-2 h-2 w-full rounded-full bg-[#E4EAF2]">
                      <div className="h-2 rounded-full bg-[#155EEF]" style={{ width: "78%" }} />
                    </div>
                  </div>

                  <div className="rounded-lg border border-[#E9A23B]/30 bg-[#E9A23B]/5 p-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-[#E9A23B]">
                      <span>⚠️ Anomaliya Aniqlangan:</span>
                      <span className="font-medium text-[#172B4D]">Gip-3 kompressor stansiyasi</span>
                    </div>
                    <p className="mt-1 text-[11px] text-[#667085]">
                      Tungi smenada kutilmagan 42% oshish aniqlandi (Rolling Z-score: 3.42).
                    </p>
                  </div>
                </div>

                <div className="mt-4 border-t border-[#E4EAF2] pt-3 text-center">
                  <Link href="/dashboard" className="text-xs font-semibold text-[#155EEF] hover:underline">
                    To‘liq platformani ko‘rish →
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trust & Architecture Metrics */}
      <section className="border-b border-[#E4EAF2] bg-white py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
            <div className="flex flex-col border-l-2 border-[#155EEF] pl-4">
              <span className="text-2xl font-bold text-[#123B72]">100%</span>
              <span className="mt-1 text-xs font-semibold text-[#172B4D]">Deterministik Matematika</span>
              <span className="mt-0.5 text-xs text-[#667085]">kWh va kW aniq hisoblash, uydirmalarsiz</span>
            </div>
            <div className="flex flex-col border-l-2 border-[#12A66A] pl-4">
              <span className="text-2xl font-bold text-[#123B72]">10 Bosqich</span>
              <span className="mt-1 text-xs font-semibold text-[#172B4D]">Ma’lumot Tekshiruvi</span>
              <span className="mt-0.5 text-xs text-[#667085]">CSV va Excel importi dublikatsiz</span>
            </div>
            <div className="flex flex-col border-l-2 border-[#155EEF] pl-4">
              <span className="text-2xl font-bold text-[#123B72]">6 Til</span>
              <span className="mt-1 text-xs font-semibold text-[#172B4D]">To‘liq Lokalizatsiya</span>
              <span className="mt-0.5 text-xs text-[#667085]">UZ, EN, RU, KK, TR, KY</span>
            </div>
            <div className="flex flex-col border-l-2 border-[#123B72] pl-4">
              <span className="text-2xl font-bold text-[#123B72]">2 Telegram Bot</span>
              <span className="mt-1 text-xs font-semibold text-[#172B4D]">Xavfsiz Integratsiya</span>
              <span className="mt-0.5 text-xs text-[#667085]">Rasmiy korxona va Sintetik demo</span>
            </div>
          </div>
        </div>
      </section>

      {/* Product Features Section */}
      <section id="features" className="border-b border-[#E4EAF2] bg-[#F5F8FC] py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="text-center">
            <Badge tone="info">PLATFORMA IMKONIYATLARI</Badge>
            <h2 className="mt-3 text-2xl font-bold text-[#123B72] sm:text-3xl">
              Korxona Energetika Tahlilining To‘liq Sikli
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm text-[#667085]">
              Hisoblagichlar ko‘rsatkichlarini qabul qilishdan tortib, davlat va xalqaro auditga mos hisobotlar tuzishgacha.
            </p>
          </div>

          <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {/* Feature 1 */}
            <Card className="flex flex-col bg-white p-6 shadow-xs">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#155EEF]/10 text-[#155EEF]">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="10" cy="10" r="7" />
                  <path d="M10 6v4l2.5 2.5" />
                </svg>
              </div>
              <h3 className="mt-4 text-base font-bold text-[#172B4D]">Hisoblagichlar Boshqaruvi</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#667085]">
                Intervalli (kWh) va kumulyativ (registr) hisoblagichlar. 15, 30 va 60 daqiqalik kadanslar, bo‘limlar va
                transformator multiplikatorlari hisobi.
              </p>
            </Card>

            {/* Feature 2 */}
            <Card className="flex flex-col bg-white p-6 shadow-xs">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#12A66A]/10 text-[#12A66A]">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 16V4m0 0L8 8m4-4 4 4M4 20h16" />
                </svg>
              </div>
              <h3 className="mt-4 text-base font-bold text-[#172B4D]">10 Bosqichli Ma’lumot Importi</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#667085]">
                CSV va XLSX fayllar uchun ko‘p tilli sarlavhalarni aniqlash, dublikatlarni tekshirish, intervallardagi uzilishlar
                va registr nolga tushishini xavfsiz qayta ishlash.
              </p>
            </Card>

            {/* Feature 3 */}
            <Card className="flex flex-col bg-white p-6 shadow-xs">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#D92D20]/10 text-[#D92D20]">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 4.5 3.5 19h17L12 4.5Zm0 5v4m0 3v.01" />
                </svg>
              </div>
              <h3 className="mt-4 text-base font-bold text-[#172B4D]">Tushuntiriluvchi Anomaliyalar</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#667085]">
                Rolling Z-score, Robust MAD va Quvvat Cheklovi algoritmlari orqali noodatiy sarfni aniqlash. Har bir anomaliya
                sababi matematik formulalar bilan tushuntiriladi.
              </p>
            </Card>

            {/* Feature 4 */}
            <Card className="flex flex-col bg-white p-6 shadow-xs">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#155EEF]/10 text-[#155EEF]">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 17l6-6 4 4 6-6" />
                </svg>
              </div>
              <h3 className="mt-4 text-base font-bold text-[#172B4D]">Xarajatlar va 30 Kunlik Prognoz</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#667085]">
                O‘zbekiston korxona tariflari (UZS) bo‘yicha xarajatlar tahlili. Tarixiy ma’lumotlarga asoslangan ilmiy prognoz
                va ishonchlilik oralig‘i.
              </p>
            </Card>

            {/* Feature 5 */}
            <Card className="flex flex-col bg-white p-6 shadow-xs">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#123B72]/10 text-[#123B72]">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 3h8l4 4v14H6V3Z" />
                  <path d="M9 12h6M9 16h4" />
                </svg>
              </div>
              <h3 className="mt-4 text-base font-bold text-[#172B4D]">Dalillangan Tejamkorlik Hisoboti</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#667085]">
                Bazaviy davr bilan faktik taqqoslash. Hech qanday uydirma ko‘rsatkichsiz, PDF, Excel va CSV formatlarida rasmiy
                eksport.
              </p>
            </Card>

            {/* Feature 6 */}
            <Card className="flex flex-col bg-white p-6 shadow-xs">
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#155EEF]/10 text-[#155EEF]">
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 4 3 11l7 3 3 6 8-16Zm-8 10 3-7" />
                </svg>
              </div>
              <h3 className="mt-4 text-base font-bold text-[#172B4D]">Ikki Tomonlama Telegram Bot</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#667085]">
                6 xonali bir martalik kod orqali bog‘lanish. Energetiklar va rahbarlar uchun tezkor xabardorlik va tahlil.
              </p>
            </Card>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="how-it-works" className="border-b border-[#E4EAF2] bg-white py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="text-center">
            <Badge tone="success">ISHLASH METODOLOGIYASI</Badge>
            <h2 className="mt-3 text-2xl font-bold text-[#123B72] sm:text-3xl">
              Xom Ma’lumotlardan Amaliy Boshqaruvgacha
            </h2>
          </div>

          <div className="mt-12 grid grid-cols-1 gap-8 md:grid-cols-4">
            <div className="flex flex-col items-center text-center">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-[#155EEF] text-lg font-bold text-white shadow-sm">
                1
              </span>
              <h3 className="mt-4 text-sm font-bold text-[#172B4D]">Ma’lumotlarni Yuklash</h3>
              <p className="mt-2 text-xs text-[#667085]">
                CSV yoki XLSX fayllarini yuklang yoki hisoblagichlarni to‘g‘ridan-to‘g‘ri ulang.
              </p>
            </div>
            <div className="flex flex-col items-center text-center">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-[#123B72] text-lg font-bold text-white shadow-sm">
                2
              </span>
              <h3 className="mt-4 text-sm font-bold text-[#172B4D]">Tekshiruv va Tozalash</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Tizim vaqt uzilishlari, takroriy qatorlar va noto‘g‘ri o‘qishlarni avtomatik aniqlaydi.
              </p>
            </div>
            <div className="flex flex-col items-center text-center">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-[#155EEF] text-lg font-bold text-white shadow-sm">
                3
              </span>
              <h3 className="mt-4 text-sm font-bold text-[#172B4D]">AI va Deterministik Tahlil</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Iste’mol profili, eng yuqori soatlar va xarajatlar aniq formulalar bilan hisoblanadi.
              </p>
            </div>
            <div className="flex flex-col items-center text-center">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-[#12A66A] text-lg font-bold text-white shadow-sm">
                4
              </span>
              <h3 className="mt-4 text-sm font-bold text-[#172B4D]">Amaliy Hisobot va Natija</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Rahbariyat va bosh energetik uchun tasdiqlangan hisobotlar va tavsiyalar taqdim etiladi.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Target Industries */}
      <section id="industries" className="border-b border-[#E4EAF2] bg-[#F5F8FC] py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="text-center">
            <Badge tone="info">O‘ZBEKISTON SANOATI</Badge>
            <h2 className="mt-3 text-2xl font-bold text-[#123B72] sm:text-3xl">
              Asosiy Tarmoqlar Uchun Maxsus Yechimlar
            </h2>
          </div>

          <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-xl border border-[#E4EAF2] bg-white p-6 shadow-xs">
              <span className="text-2xl">🧵</span>
              <h3 className="mt-3 text-base font-bold text-[#172B4D]">To‘qimachilik va Ip-kalava</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Uzluksiz 24/7 ishlab chiqarishda yigiruv va to‘quv dastgohlarining energetik balansi va pik soatlarini optimallashtirish.
              </p>
            </div>
            <div className="rounded-xl border border-[#E4EAF2] bg-white p-6 shadow-xs">
              <span className="text-2xl">⚙️</span>
              <h3 className="mt-3 text-base font-bold text-[#172B4D]">Og‘ir va Yengil Sanoat</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Metallurgiya, kimyo va mashinasozlik korxonalarida quvvat cheklovlariga (Power Ceiling) rioya etilishini nazorat qilish.
              </p>
            </div>
            <div className="rounded-xl border border-[#E4EAF2] bg-white p-6 shadow-xs">
              <span className="text-2xl">🍞</span>
              <h3 className="mt-3 text-base font-bold text-[#172B4D]">Oziq-ovqat va Qayta Ishlash</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Muzlatkich va pishirish pechlarining smenalar bo‘yicha o‘zgaruvchan elektr yuklamalarini kuzatish.
              </p>
            </div>
            <div className="rounded-xl border border-[#E4EAF2] bg-white p-6 shadow-xs">
              <span className="text-2xl">📦</span>
              <h3 className="mt-3 text-base font-bold text-[#172B4D]">Logistika va Sovuq Omborlar</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Sovutish kompressorlarining tungi arzon tarif vaqtlarida ishlash rejimlarini muvofiqlashtirish.
              </p>
            </div>
            <div className="rounded-xl border border-[#E4EAF2] bg-white p-6 shadow-xs">
              <span className="text-2xl">🏢</span>
              <h3 className="mt-3 text-base font-bold text-[#172B4D]">Tijorat va Biznes Markazlar</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Konditsionerlash, shamollatish va yoritish tizimlarining ish vaqtidan tashqari behuda sarfini aniqlash.
              </p>
            </div>
            <div className="rounded-xl border border-[#E4EAF2] bg-white p-6 shadow-xs">
              <span className="text-2xl">⚡</span>
              <h3 className="mt-3 text-base font-bold text-[#172B4D]">Ijtimoiy va Davlat Obyektlari</h3>
              <p className="mt-2 text-xs text-[#667085]">
                Davlat budjeti mablag‘larining energiya xarajatlari bo‘yicha shaffof monitoringi va auditga tayyorligi.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* AI Safety and Hallucination Guard */}
      <section id="ai-safety" className="border-b border-[#E4EAF2] bg-white py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="rounded-2xl border border-[#155EEF]/20 bg-gradient-to-br from-[#123B72] to-[#155EEF] p-8 text-white sm:p-12">
            <div className="max-w-3xl">
              <Badge tone="info" className="bg-white/20 text-white">
                AI ARXITEKTURASI VA XAVFSIZLIK
              </Badge>
              <h2 className="mt-4 text-2xl font-bold tracking-tight text-white sm:text-3xl">
                Raqamli Gallyutsinatsiyalardan Himoyalangan Sun’iy Intellekt
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-white/90">
                NEXTGEN AI generativ model (Gemini 2.5) xulosalarini qat’iy raqamli himoyalovchi{" "}
                <span className="font-semibold text-white">"Numeric Hallucination Guard"</span> orqali tekshiradi.
                Agar AI taklif qilgan matnda korxona bazasida mavjud bo‘lmagan bitta raqam paydo bo‘lsa, u darhol
                bloklanadi va deterministik qoidaga asoslangan hisob-kitobga almashtiriladi.
              </p>

              <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="rounded-lg bg-white/10 p-4 backdrop-blur-xs">
                  <span className="text-xs font-bold uppercase tracking-wider text-white/80">01. Dalillilik</span>
                  <p className="mt-1 text-xs text-white/90">Har bir xulosa faqat o‘lchangan hisoblagich ko‘rsatkichlariga tayanadi.</p>
                </div>
                <div className="rounded-lg bg-white/10 p-4 backdrop-blur-xs">
                  <span className="text-xs font-bold uppercase tracking-wider text-white/80">02. Mustaqillik</span>
                  <p className="mt-1 text-xs text-white/90">Har bir korxona ma’lumotlari alohida tenant darajasida qat’iy izolyatsiya qilingan.</p>
                </div>
                <div className="rounded-lg bg-white/10 p-4 backdrop-blur-xs">
                  <span className="text-xs font-bold uppercase tracking-wider text-white/80">03. Auditga Tayyorlik</span>
                  <p className="mt-1 text-xs text-white/90">Barcha hisob-kitoblar va o‘zgarishlar audit loglarida saqlanadi.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Contact & Demo CTA */}
      <section id="contact" className="bg-[#F5F8FC] py-20">
        <div className="mx-auto max-w-7xl px-4 text-center sm:px-6">
          <h2 className="text-2xl font-bold text-[#123B72] sm:text-3xl">
            Energiya Tahlilini Bugunoq Boshlang
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-[#667085]">
            Interaktiv sintetik DEMO orqali barcha imkoniyatlarni bevosita o‘rganing yoki korxonangiz uchun hisob oching.
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-4">
            <Link href="/dashboard">
              <Button variant="primary" size="md" className="h-11 bg-[#155EEF] px-8 text-sm font-semibold shadow-md hover:bg-[#124bbf]">
                Interaktiv DEMO-ni Sinab Ko‘rish
              </Button>
            </Link>
            <Link href="/register">
              <Button variant="secondary" size="md" className="h-11 border-[#E4EAF2] bg-white px-8 text-sm font-semibold text-[#172B4D]">
                Korxona Uchun Ro‘yxatdan O‘tish
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Official Footer */}
      <footer className="border-t border-[#E4EAF2] bg-white py-12 text-xs text-[#667085]">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 px-4 sm:flex-row sm:px-6">
          <div className="flex flex-col items-center gap-2 sm:items-start">
            <div className="flex items-center gap-2">
              <span className="grid h-6 w-6 place-items-center rounded bg-[#155EEF] text-xs font-bold text-white">
                N
              </span>
              <span className="font-bold text-[#123B72]">NEXTGEN AI</span>
            </div>
            <span>© 2026 NEXTGEN AI. O‘zbekiston Respublikasi. Barcha huquqlar himoyalangan.</span>
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <Link href="/login" className="hover:text-[#155EEF]">
              Tizimga kirish
            </Link>
            <Link href="/register" className="hover:text-[#155EEF]">
              Ro‘yxatdan o‘tish
            </Link>
            <Link href="/dashboard" className="hover:text-[#155EEF]">
              DEMO Platforma
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
