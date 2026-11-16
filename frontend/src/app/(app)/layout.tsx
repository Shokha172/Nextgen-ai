"use client";

import { AppShell, ShellSkeleton } from "@/components/shell";
import { useRequireAuth } from "@/lib/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { session, loading } = useRequireAuth();

  if (loading) return <ShellSkeleton />;
  if (!session) return <div className="min-h-screen bg-bg" aria-busy="true" />;
  return <AppShell>{children}</AppShell>;
}
