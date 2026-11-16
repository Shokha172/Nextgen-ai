"use client";

/**
 * Charts are hand-rolled SVG — no charting dependency, no external assets, so
 * they render identically in the product and in a sandboxed preview.
 *
 * Units are never guessed: every chart receives an explicit `unit` (kWh, kW or a
 * currency) from the caller.
 */
import { useId, useMemo, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { num } from "@/lib/format";
import { cx } from "./ui";

export interface Series {
  name: string;
  color: string;
  values: Array<number | null>;
  dashed?: boolean;
  area?: boolean;
  /** Index in `labels` where this series starts (used for forecast continuation). */
  offset?: number;
}

interface LineChartProps {
  labels: string[];
  series: Series[];
  unit: string;
  height?: number;
  /** Number of x-axis labels to render (thinned automatically). */
  xTicks?: number;
  ariaLabel: string;
  emptyLabel?: string;
}

const PAD = { top: 12, right: 12, bottom: 22, left: 46 };

export function LineChart({
  labels,
  series,
  unit,
  height = 240,
  xTicks = 6,
  ariaLabel,
  emptyLabel,
}: LineChartProps) {
  const { lang, t } = useI18n();
  const gradientId = useId().replace(/:/g, "");
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const width = 720;
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const totals = useMemo(() => {
    let max = 0;
    let hasValue = false;
    for (const s of series) {
      for (const v of s.values) {
        if (v === null || Number.isNaN(v)) continue;
        hasValue = true;
        if (v > max) max = v;
      }
    }
    return { max: max > 0 ? max : 1, hasValue };
  }, [series]);

  const x = (index: number) => PAD.left + (labels.length <= 1 ? plotW / 2 : (index / (labels.length - 1)) * plotW);
  const y = (value: number) => PAD.top + plotH - (value / totals.max) * plotH;

  const ticks = useMemo(() => [0, 0.25, 0.5, 0.75, 1].map((frac) => frac * totals.max), [totals.max]);

  if (!totals.hasValue) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-line/70 text-xs text-muted"
        style={{ height }}
      >
        {emptyLabel ?? t("common.empty")}
      </div>
    );
  }

  const pathFor = (s: Series) => {
    const offset = s.offset ?? 0;
    const commands: string[] = [];
    s.values.forEach((value, i) => {
      if (value === null || Number.isNaN(value)) return;
      const cmd = commands.length === 0 ? "M" : "L";
      commands.push(`${cmd}${x(offset + i).toFixed(2)},${y(value).toFixed(2)}`);
    });
    return commands.join(" ");
  };

  const areaFor = (s: Series) => {
    const offset = s.offset ?? 0;
    const valid = s.values.map((v, i) => ({ v, i })).filter((p) => p.v !== null && !Number.isNaN(p.v));
    if (valid.length === 0) return "";
    const first = valid[0];
    const last = valid[valid.length - 1];
    const line = valid
      .map((p, idx) => `${idx === 0 ? "M" : "L"}${x(offset + p.i).toFixed(2)},${y(p.v as number).toFixed(2)}`)
      .join(" ");
    const base = PAD.top + plotH;
    return `${line} L${x(offset + last.i).toFixed(2)},${base} L${x(offset + first.i).toFixed(2)},${base} Z`;
  };

  const labelStep = Math.max(1, Math.ceil(labels.length / xTicks));

  const onMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const svg = event.currentTarget;
    const rect = svg.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const px = ratio * width;
    const idx = Math.round(((px - PAD.left) / plotW) * (labels.length - 1));
    setHover(Math.max(0, Math.min(labels.length - 1, idx)));
  };

  const hovered = hover !== null ? hover : null;

  return (
    <figure className="w-full" ref={wrapRef}>
      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label={ariaLabel}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
          className="touch-none"
        >
          <defs>
            {series.map((s, i) => (
              <linearGradient key={s.name} id={`${gradientId}-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity="0.32" />
                <stop offset="100%" stopColor={s.color} stopOpacity="0.02" />
              </linearGradient>
            ))}
          </defs>

          {/* grid + y labels */}
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="currentColor"
                className="text-line"
                strokeDasharray={tick === 0 ? undefined : "3 4"}
                strokeWidth="1"
              />
              <text x={PAD.left - 8} y={y(tick) + 3} textAnchor="end" className="fill-muted text-[10px]">
                {num(tick, tick >= 100 ? 0 : 1, lang)}
              </text>
            </g>
          ))}

          {/* x labels */}
          {labels.map((label, i) =>
            i % labelStep === 0 || i === labels.length - 1 ? (
              <text
                key={`${label}-${i}`}
                x={x(i)}
                y={height - 6}
                textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"}
                className="fill-muted text-[10px]"
              >
                {label}
              </text>
            ) : null,
          )}

          {series.map((s, i) =>
            s.area === false ? null : (
              <path key={`area-${s.name}`} d={areaFor(s)} fill={`url(#${gradientId}-${i})`} />
            ),
          )}

          {series.map((s) => (
            <path
              key={`line-${s.name}`}
              d={pathFor(s)}
              fill="none"
              stroke={s.color}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeDasharray={s.dashed ? "5 4" : undefined}
            />
          ))}

          {hovered !== null && (
            <line
              x1={x(hovered)}
              x2={x(hovered)}
              y1={PAD.top}
              y2={PAD.top + plotH}
              stroke="currentColor"
              className="text-muted"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
          )}
          {hovered !== null &&
            series.map((s) => {
              const offset = s.offset ?? 0;
              const value = s.values[hovered - offset];
              if (value === null || value === undefined || Number.isNaN(value)) return null;
              return (
                <circle
                  key={`dot-${s.name}`}
                  cx={x(hovered)}
                  cy={y(value)}
                  r="3.5"
                  fill={s.color}
                  stroke="#080D19"
                  strokeWidth="1.5"
                />
              );
            })}
        </svg>

        {hovered !== null && (
          <div
            className="pointer-events-none absolute top-1 z-10 rounded-lg border border-line bg-surface/95 px-2.5 py-1.5 text-[11px] shadow-lg"
            style={{
              left: `${Math.min(78, Math.max(2, (x(hovered) / width) * 100))}%`,
            }}
          >
            <div className="mb-0.5 font-medium text-ink">{labels[hovered]}</div>
            {series.map((s) => {
              const offset = s.offset ?? 0;
              const value = s.values[hovered - offset];
              if (value === null || value === undefined || Number.isNaN(value)) return null;
              return (
                <div key={s.name} className="flex items-center gap-1.5 whitespace-nowrap text-muted">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
                  {s.name}: <span className="text-ink">{num(value, 1, lang)} {unit}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {series.length > 1 && (
        <figcaption className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted">
          {series.map((s) => (
            <span key={s.name} className="inline-flex items-center gap-1.5">
              <span
                className={cx("h-0.5 w-4 rounded", s.dashed && "opacity-70")}
                style={{ background: s.color }}
              />
              {s.name}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}

export function BarChart({
  bars,
  unit,
  height = 180,
  ariaLabel,
  color = "var(--color-primary)",
}: {
  bars: Array<{ label: string; value: number | null }>;
  unit: string;
  height?: number;
  ariaLabel: string;
  color?: string;
}) {
  const { lang, t } = useI18n();
  const max = Math.max(...bars.map((b) => b.value ?? 0), 0);
  if (max <= 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-line/70 text-xs text-muted"
        style={{ height }}
      >
        {t("common.empty")}
      </div>
    );
  }
  return (
    <div role="img" aria-label={ariaLabel}>
      <div className="flex items-end gap-[3px]" style={{ height }}>
        {bars.map((bar, i) => {
          const ratio = (bar.value ?? 0) / max;
          return (
            <div
              key={`${bar.label}-${i}`}
              className="group relative flex-1"
              title={`${bar.label}: ${bar.value === null ? "—" : num(bar.value, 1, lang)} ${unit}`}
            >
              <div
                className="w-full rounded-t-[3px] transition-opacity group-hover:opacity-80"
                style={{
                  height: `${Math.max(ratio * height, 2)}px`,
                  background: `linear-gradient(180deg, ${color}, color-mix(in srgb, ${color} 45%, transparent))`,
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted">
        <span>{bars[0]?.label}</span>
        {bars.length > 2 && <span>{bars[Math.floor(bars.length / 2)]?.label}</span>}
        <span>{bars[bars.length - 1]?.label}</span>
      </div>
    </div>
  );
}

/** Ranked horizontal bars — used for meter and department shares. */
export function ShareBars({
  items,
  unit,
  lang,
}: {
  items: Array<{ label: string; value: number; share?: number | null }>;
  unit: string;
  lang: "uz" | "ru" | "en";
}) {
  const max = Math.max(...items.map((i) => i.value), 0) || 1;
  return (
    <ul className="flex flex-col gap-2.5">
      {items.map((item) => (
        <li key={item.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[12px]">
            <span className="truncate text-ink/90" title={item.label}>
              {item.label}
            </span>
            <span className="shrink-0 tabular-nums text-muted">
              {num(item.value, 1, lang)} {unit}
              {item.share !== null && item.share !== undefined && (
                <span className="ml-1.5 text-ink/70">· {num(item.share, 1, lang)}%</span>
              )}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface2">
            <div
              className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
              style={{ width: `${Math.max((item.value / max) * 100, 1.5)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
