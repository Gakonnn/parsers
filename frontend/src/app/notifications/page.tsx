"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { NotificationItem } from "@/lib/types";

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);

  async function load() {
    const response = await api.notifications();
    setItems(response.items);
    setUnread(response.unread_total);
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function markAll() {
    await api.markNotificationsRead();
    await load();
    window.dispatchEvent(new Event("parserdesk:notifications-updated"));
  }

  return (
    <AppShell
      eyebrow="Inbox"
      title="Уведомления"
      actions={<button className="ghost-button" type="button" onClick={() => markAll().catch(() => undefined)}>Прочитать все</button>}
    >
      <section className="panel-card">
        <div className="section-heading horizontal">
          <div>
            <span className="eyebrow">Непрочитано {unread}</span>
            <h2>Системные события</h2>
          </div>
        </div>
        {!items.length ? <EmptyState title="Пусто" text="Здесь будут статусы задач, оплат и изменений тарифа." /> : null}
        <div className="notification-list">
          {items.map((item) => (
            <article className={item.is_read ? "notification-card read" : "notification-card"} key={item.id}>
              <div>
                <strong>{item.title}</strong>
                <p>{item.body || item.type}</p>
              </div>
              <span>{formatDate(item.created_at)}</span>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
