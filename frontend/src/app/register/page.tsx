"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/shell";
import { Button, ErrorState, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export default function RegisterPage() {
  const { t, lang } = useI18n();
  const { reload, session, loading } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    organization_name: "",
    invite_token: "",
  });
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && session) router.replace("/dashboard");
  }, [loading, session, router]);

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        locale: lang,
      };
      if (form.organization_name.trim()) body.organization_name = form.organization_name.trim();
      if (form.invite_token.trim()) body.invite_token = form.invite_token.trim();
      // Registration signs the user in: the backend sets the session cookie.
      await api.post("/auth/register", body);
      await reload();
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError("Registration failed", 0));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center px-5 py-10">
      <div className="mb-7 flex items-center justify-between">
        <Logo />
        <Link href="/login" className="text-[12px] text-muted underline underline-offset-2">
          {t("auth.have_account")} {t("auth.login_link")}
        </Link>
      </div>

      <h1 className="text-xl font-semibold text-ink">{t("auth.register_title")}</h1>
      <p className="mt-1 text-[13px] text-muted">{t("auth.register_subtitle")}</p>

      <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
        <Field label={t("auth.full_name")} htmlFor="full_name">
          <Input id="full_name" required minLength={2} value={form.full_name} onChange={set("full_name")} />
        </Field>
        <Field label={t("auth.email")} htmlFor="email">
          <Input id="email" type="email" required value={form.email} onChange={set("email")} />
        </Field>
        <Field label={t("auth.password")} htmlFor="password" hint="≥ 10">
          <Input
            id="password"
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            value={form.password}
            onChange={set("password")}
          />
        </Field>
        <Field
          label={`${t("auth.organization_name")} (${t("common.optional")})`}
          htmlFor="organization_name"
          hint={t("auth.organization_hint")}
        >
          <Input id="organization_name" value={form.organization_name} onChange={set("organization_name")} />
        </Field>
        <Field
          label={`${t("auth.invite_token")} (${t("common.optional")})`}
          htmlFor="invite_token"
        >
          <Input id="invite_token" value={form.invite_token} onChange={set("invite_token")} />
        </Field>

        {error && <ErrorState error={error} compact />}

        <Button type="submit" loading={submitting}>
          {submitting ? t("auth.registering") : t("auth.register")}
        </Button>
      </form>
    </div>
  );
}
