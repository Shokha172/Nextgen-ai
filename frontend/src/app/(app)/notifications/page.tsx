"use client";

import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
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
import type { NotificationItem, NotificationPage } from "@/lib/types";

export default function NotificationsPage() {
  const { t, lang } = useI18n();
  const { toast } = useToast();

  const notifications = useResource<NotificationPage>(
    (signal) => api.get<NotificationPage>("/notifications", { limit: 50 }, signal),
    [],
  );

  const handleMarkAllRead = async () => {
    try {
      await api.post("/notifications/read-all");
      toast({ title: "Barcha bildirishnomalar o‘qildi deb belgilandi", tone: "success" });
      void notifications.reload();
    } catch {
      toast({ title: "Xatolik", tone: "danger" });
    }
  };

  const items = notifications.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("nav.notifications")}
        subtitle="Tizim ogohlantirishlari, anomaliyalar va yangilanishlar"
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary sm:flex">
              👨‍💻 Dev: Shohjahon Abdullayev
            </span>
            <Button variant="secondary" size="sm" onClick={notifications.reload} loading={notifications.refreshing}>
              {t("common.refresh")}
            </Button>
            {items.length > 0 && (
              <Button variant="secondary" size="sm" onClick={handleMarkAllRead}>
                Barchasini o'qilgan deb belgilash
              </Button>
            )}
          </div>
        }
      />

      <Card>
        <CardTitle
          title={`Bildirishnomalar (${items.length})`}
          subtitle={
            (notifications.data?.unread ?? 0) > 0
              ? `${notifications.data?.unread} ta o‘qilmagan xabar`
              : "Barcha xabarlar o‘qilgan"
          }
        />
        {items.length === 0 ? (
          <EmptyState title="Yangi bildirishnomalar yo‘q" body="Tizim bir maromda ishlamoqda." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Sarlavha</Th>
                <Th>Xabar matni</Th>
                <Th>Turi</Th>
                <Th>Vaqt</Th>
                <Th align="right">Holat</Th>
              </tr>
            </thead>
            <tbody>
              {items.map((n) => (
                <tr key={n.id} className={`hover:bg-surface2 ${!n.read ? "bg-primary/5" : ""}`}>
                  <Td className="font-semibold text-ink">{n.title}</Td>
                  <Td className="text-muted text-xs max-w-md">{n.body}</Td>
                  <Td>
                    <Badge tone={n.severity === "critical" ? "danger" : n.severity === "warning" ? "warning" : "neutral"}>
                      {n.category || n.kind || "Tizim"}
                    </Badge>
                  </Td>
                  <Td className="whitespace-nowrap text-muted text-xs">{dateTime(n.created_at, lang)}</Td>
                  <Td align="right">
                    <Badge tone={n.read ? "neutral" : "primary"}>
                      {n.read ? "O'qilgan" : "Yangi"}
                    </Badge>
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
