/**
 * Locale-aware formatting.
 *
 * Hard rules:
 *  - energy is always labelled **kWh**, power always **kW** — never mixed;
 *  - timestamps are stored in UTC and shown in Asia/Tashkent;
 *  - a missing value renders as "—" instead of a fake zero.
 */
import type { Lang } from "./types";

export const DISPLAY_TZ = "Asia/Tashkent";

function localeFor(lang: Lang): string {
  return lang === "en" ? "en-US" : "ru-RU";
}

/** Thousands separator is a space (UZ/RU convention), decimals a comma. */
export function num(value: number | string | null | undefined, digits = 1, lang: Lang = "uz"): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat(localeFor(lang), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}

/** Energy — kWh. */
export function energy(value: number | string | null | undefined, lang: Lang = "uz", digits = 1): string {
  return value === null || value === undefined ? "—" : `${num(value, digits, lang)} kWh`;
}

/** Power — kW. A 1000× smaller number than energy; never rendered as kWh. */
export function power(value: number | string | null | undefined, lang: Lang = "uz", digits = 1): string {
  return value === null || value === undefined ? "—" : `${num(value, digits, lang)} kW`;
}

export function money(
  value: number | string | null | undefined,
  currency = "UZS",
  lang: Lang = "uz",
): string {
  if (value === null || value === undefined) return "—";
  return `${num(value, 0, lang)} ${currency}`;
}

/** Compact money for KPI tiles: 208 325 027 UZS -> 208,3 mln UZS. */
export function moneyCompact(
  value: number | string | null | undefined,
  currency = "UZS",
  lang: Lang = "uz",
): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  const [div, suffix] = abs >= 1e9 ? [1e9, lang === "en" ? "bn" : "mlrd"] : abs >= 1e6 ? [1e6, lang === "en" ? "m" : "mln"] : [1, ""];
  const scaled = n / div;
  const digits = div === 1 ? 0 : 1;
  return `${num(scaled, digits, lang)}${suffix ? ` ${suffix}` : ""} ${currency}`;
}

export function pct(value: number | string | null | undefined, lang: Lang = "uz", digits = 1): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${num(n, digits, lang)}%`;
}

export function signedEnergy(value: number | string | null | undefined, lang: Lang = "uz"): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  const prefix = n > 0 ? "+" : "";
  return `${prefix}${num(n, 1, lang)} kWh`;
}

export function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${num(value / 1024, 1)} KB`;
  return `${num(value / 1024 / 1024, 1)} MB`;
}

const dtf = (lang: Lang, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat(localeFor(lang), { timeZone: DISPLAY_TZ, ...opts });

export function dateShort(iso: string | null | undefined, lang: Lang = "uz"): string {
  if (!iso) return "—";
  return dtf(lang, { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(iso));
}

export function dateTime(iso: string | null | undefined, lang: Lang = "uz"): string {
  if (!iso) return "—";
  return dtf(lang, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function timeOnly(iso: string | null | undefined, lang: Lang = "uz"): string {
  if (!iso) return "—";
  return dtf(lang, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

export function relativeTime(iso: string | null | undefined, lang: Lang = "uz"): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  const rtf = new Intl.RelativeTimeFormat(localeFor(lang), { numeric: "auto" });
  if (Math.abs(minutes) < 60) return rtf.format(-minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(-hours, "hour");
  return rtf.format(-Math.round(hours / 24), "day");
}

/** ISO date (yyyy-mm-dd) in the display timezone — used for date inputs. */
export function isoDateInTz(value: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: DISPLAY_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(value);
  return parts;
}

export function daysAgoIso(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return isoDateInTz(d);
}

export function initials(name: string | null | undefined): string {
  if (!name) return "—";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
