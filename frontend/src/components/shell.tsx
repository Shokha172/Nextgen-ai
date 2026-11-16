"use client";

/** Application shell: sidebar navigation, organization switcher, user menu. */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { initials } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import { LANGS, useI18n, type TKey } from "@/lib/i18n";
import type { NotificationPage } from "@/lib/types";
import { Badge, Button, Spinner, cx, useToast } from "./ui";

interface NavItem {
  href: string;
  label: TKey;
  icon: keyof typeof ICONS;
}

const NAV: Array<{ group: TKey; items: NavItem[] }> = [
  {
    group: "nav.group.overview",
    items: [{ href: "/dashboard", label: "nav.dashboard", icon: "dashboard" }],
  },
  {
    group: "nav.group.data",
    items: [
      { href: "/analytics", label: "nav.analytics", icon: "chart" },
      { href: "/meters", label: "nav.meters", icon: "meter" },
      { href: "/imports", label: "nav.imports", icon: "upload" },
    ],
  },
  {
    group: "nav.group.intelligence",
    items: [
      { href: "/anomalies", label: "nav.anomalies", icon: "alert" },
      { href: "/forecast", label: "nav.forecast", icon: "trend" },
      { href: "/advisor", label: "nav.advisor", icon: "spark" },
      { href: "/savings", label: "nav.savings", icon: "piggy" },
    ],
  },
  {
    group: "nav.group.admin",
    items: [
      { href: "/reports", label: "nav.reports", icon: "file" },
      { href: "/notifications", label: "nav.notifications", icon: "bell" },
      { href: "/telegram", label: "nav.telegram", icon: "send" },
      { href: "/settings", label: "nav.settings", icon: "settings" },
    ],
  },
];

const ICONS = {
  dashboard: (
    <>
      <path d="M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm9 0h7v-9h-7v9Zm0-16v5h7V4h-7Z" />
    </>
  ),
  chart: <path d="M4 19h16M7 16V9m5 7V5m5 11v-5" />,
  meter: (
    <>
      <circle cx="12" cy="12" r="7.5" />
      <path d="M12 12l3.5-3.5M9 19.5V21m6-1.5V21" />
    </>
  ),
  upload: <path d="M12 16V5m0 0L8 9m4-4 4 4M5 19h14" />,
  alert: <path d="M12 4.5 3.5 19h17L12 4.5Zm0 5v4m0 3v.01" />,
  trend: <path d="M4 16.5 9 11l3.5 3L20 6m0 0h-4m4 0v4" />,
  spark: <path d="M12 3v3.5M12 17.5V21M4.5 12H8m8 0h3.5M6.7 6.7l2.5 2.5m5.6 5.6 2.5 2.5m0-10.6-2.5 2.5m-5.6 5.6-2.5 2.5" />,
  piggy: <path d="M4 12.5A6 6 0 0 1 10 6h5a6 6 0 0 1 5.6 3.9L21 12v3l-2 .6V18h-3v-1.5H9V18H6v-2.2A6 6 0 0 1 4 12.5Zm12-3.5v.01" />,
  file: (
    <>
      <path d="M6 3h8l4 4v14H6V3Z" />
      <path d="M9 12h6M9 16h4" />
    </>
  ),
  bell: <path d="M6.5 17V11a5.5 5.5 0 0 1 11 0v6l1.5 2H5l1.5-2Zm3.7 4a2 2 0 0 0 3.6 0" />,
  send: <path d="M21 4 3 11l7 3 3 6 8-16Zm-8 10 3-7" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2m0 14v2M4.9 7.4l1.7 1m10.8 7.2 1.7 1M3 12h2m14 0h2M4.9 16.6l1.7-1m10.8-7.2 1.7-1" />
    </>
  ),
} as const;

function NavIcon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      {ICONS[name]}
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-accent text-[13px] font-bold text-white">
        N
      </span>
      {!compact && (
        <span className="flex flex-col leading-none">
          <span className="text-[13px] font-semibold tracking-wide text-ink">NEXTGEN AI</span>
          <span className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-muted">
            Energy Intelligence
          </span>
        </span>
      )}
    </div>
  );
}

function LanguageSwitcher() {
  const { lang, setLang } = useI18n();
  const { session, reload } = useAuth();
  const [saving, setSaving] = useState(false);

  const choose = async (code: (typeof LANGS)[number]["code"]) => {
    setLang(code);
    // Persist the preference on the profile when signed in (best effort).
    if (session) {
      setSaving(true);
      try {
        await api.patch("/auth/me", { locale: code });
        await reload();
      } catch {
        /* non-blocking: the UI language is already switched locally */
      } finally {
        setSaving(false);
      }
    }
  };

  return (
    <div className="flex items-center gap-1 rounded-lg border border-line bg-bg/40 p-0.5">
      {LANGS.map((item) => (
        <button
          key={item.code}
          type="button"
          onClick={() => void choose(item.code)}
          aria-pressed={lang === item.code}
          title={item.label}
          disabled={saving}
          className={cx(
            "rounded-md px-2 py-1 text-[11px] font-semibold transition-colors",
            lang === item.code ? "bg-primary/20 text-ink" : "text-muted hover:text-ink",
          )}
        >
          {item.short}
        </button>
      ))}
    </div>
  );
}

function OrgSwitcher() {
  const { switchOrg, activeOrg } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const orgs = useResource<{ items: Array<{ id: string; name: string; is_demo: boolean; role: string }> }>(
    (signal) => api.get("/organizations", undefined, signal),
    [],
  );
  const items = orgs.data?.items ?? [];

  if (items.length <= 1 || !activeOrg) {
    return (
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-[13px] font-medium text-ink">{activeOrg?.name ?? "—"}</span>
        {activeOrg?.is_demo && <Badge tone="warning">{t("app.demo_badge")}</Badge>}
      </div>
    );
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      <select
        value={activeOrg.id}
        disabled={busy}
        aria-label={t("settings.org_title")}
        onChange={async (event) => {
          setBusy(true);
          try {
            await switchOrg(event.target.value);
          } catch {
            toast.error(t("error.generic"));
          } finally {
            setBusy(false);
          }
        }}
        className="max-w-[16rem] truncate rounded-lg border border-line bg-bg/60 px-2 py-1.5 text-[13px] text-ink focus:border-primary/70 focus:outline-none"
      >
        {items.map((org) => (
          <option key={org.id} value={org.id}>
            {org.name}
          </option>
        ))}
      </select>
      {busy && <Spinner className="h-3.5 w-3.5 text-muted" />}
      {activeOrg.is_demo && <Badge tone="warning">{t("app.demo_badge")}</Badge>}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const { session, logout, activeOrg, isDemo } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenu, setUserMenu] = useState(false);

  const notifications = useResource<NotificationPage>(
    (signal) => api.get<NotificationPage>("/notifications", { limit: 1 }, signal),
    [pathname],
  );

  useEffect(() => setMobileOpen(false), [pathname]);

  const nav = useMemo(
    () =>
      NAV.map((group) => ({
        ...group,
        items: group.items,
      })),
    [],
  );

  const sidebar = (
    <nav className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-4" aria-label="Asosiy menyu">
      <div className="px-1.5">
        <Logo />
      </div>
      {nav.map((group) => (
        <div key={group.group}>
          <p className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted/70">
            {t(group.group)}
          </p>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cx(
                      "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors",
                      active
                        ? "bg-primary/15 text-ink"
                        : "text-muted hover:bg-surface2 hover:text-ink",
                    )}
                  >
                    <span className={active ? "text-primary" : "text-muted"}>
                      <NavIcon name={item.icon} />
                    </span>
                    <span className="truncate">{t(item.label)}</span>
                    {item.href === "/notifications" &&
                      (notifications.data?.unread ?? 0) > 0 && (
                        <span className="ml-auto rounded-full bg-danger px-1.5 text-[10px] font-semibold text-white">
                          {notifications.data?.unread}
                        </span>
                      )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      <div className="mt-auto rounded-lg border border-line/70 bg-surface2/40 p-2.5 text-[11px] leading-relaxed text-muted">
        {t("dashboard.cost_note")}
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15.5rem_1fr]">
      <aside className="sticky top-0 hidden h-screen border-r border-line bg-surface/60 lg:block">
        {sidebar}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="animate-in absolute inset-y-0 left-0 w-[16.5rem] border-r border-line bg-surface">
            {sidebar}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/85 px-3 backdrop-blur sm:px-5">
          <button
            type="button"
            className="rounded-lg p-2 text-muted hover:bg-surface2 hover:text-ink lg:hidden"
            aria-label={mobileOpen ? t("nav.close_menu") : t("nav.open_menu")}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((open) => !open)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
            </svg>
          </button>

          <div className="hidden min-w-0 items-center gap-2 sm:flex">
            <OrgSwitcher />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <LanguageSwitcher />
            <Link
              href="/notifications"
              className="relative rounded-lg p-2 text-muted hover:bg-surface2 hover:text-ink"
              aria-label={t("nav.notifications")}
            >
              <NavIcon name="bell" />
              {(notifications.data?.unread ?? 0) > 0 && (
                <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-danger" />
              )}
            </Link>

            <div className="relative">
              <button
                type="button"
                onClick={() => setUserMenu((open) => !open)}
                aria-expanded={userMenu}
                aria-haspopup="menu"
                className="flex items-center gap-2 rounded-lg border border-line px-2 py-1.5 text-[12px] text-ink hover:bg-surface2"
              >
                <span className="grid h-6 w-6 place-items-center rounded-full bg-primary/20 text-[10px] font-semibold text-primary">
                  {initials(session?.user.full_name)}
                </span>
                <span className="hidden max-w-[9rem] truncate sm:block">
                  {session?.user.full_name ?? "—"}
                </span>
              </button>
              {userMenu && (
                <div
                  role="menu"
                  className="animate-in absolute right-0 top-11 z-40 w-56 rounded-xl border border-line bg-surface p-1.5 shadow-xl"
                >
                  <div className="px-2 py-1.5">
                    <p className="truncate text-[13px] font-medium text-ink">{session?.user.full_name}</p>
                    <p className="truncate text-[11px] text-muted">{session?.user.email}</p>
                    <p className="mt-1 text-[11px] text-muted">
                      {t("common.role")}: {session?.role ? t(`settings.role.${session.role}` as TKey) : "—"}
                    </p>
                  </div>
                  <div className="my-1 h-px bg-line" />
                  <Link
                    href="/settings"
                    role="menuitem"
                    className="block rounded-lg px-2 py-1.5 text-[13px] text-muted hover:bg-surface2 hover:text-ink"
                  >
                    {t("nav.settings")}
                  </Link>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={async () => {
                      await logout();
                      router.replace("/login");
                    }}
                    className="block w-full rounded-lg px-2 py-1.5 text-left text-[13px] text-danger hover:bg-danger/10"
                  >
                    {t("nav.logout")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {isDemo && (
          <div className="border-b border-warning/25 bg-warning/10 px-3 py-1.5 text-[11px] text-warning sm:px-5">
            {t("app.demo_notice")}
          </div>
        )}

        <main className="min-w-0 flex-1 px-3 py-4 sm:px-5 sm:py-6">{children}</main>

        <footer className="border-t border-line px-3 py-3 text-[11px] text-muted sm:px-5">
          NEXTGEN AI · {t("app.tagline")} · kWh / kW · Asia/Tashkent
        </footer>
      </div>
    </div>
  );
}

/** Placeholder used while the session is being resolved. */
export function ShellSkeleton() {
  return (
    <div className="grid min-h-screen place-items-center">
      <div className="flex items-center gap-3 text-sm text-muted">
        <Spinner />
        <span>…</span>
      </div>
    </div>
  );
}

export function UnauthorizedNotice() {
  const { t } = useI18n();
  return (
    <div className="grid min-h-screen place-items-center px-6 text-center">
      <div className="max-w-sm">
        <p className="text-sm text-muted">{t("error.unauthorized")}</p>
        <Link href="/login" className="mt-3 inline-block">
          <Button>{t("auth.login")}</Button>
        </Link>
      </div>
    </div>
  );
}
