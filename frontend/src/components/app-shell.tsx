"use client";

import { useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { DataLeadHubFooter, DataLeadHubHeader } from "@/components/parsehub-chrome";
import { api, clearToken, getToken } from "@/lib/api";
import type { NotificationList, User } from "@/lib/types";

export function AppShell({ children, eyebrow, title, actions }: { children: ReactNode; eyebrow: string; title: string; actions?: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [notifications, setNotifications] = useState<NotificationList | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    Promise.all([api.me(), api.notifications().catch(() => null)])
      .then(([me, notice]) => {
        if (!active) return;
        setUser(me);
        setNotifications(notice);
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      })
      .finally(() => active && setReady(true));
    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    function refreshNotifications() {
      api.notifications()
        .then((notice) => setNotifications(notice))
        .catch(() => undefined);
    }
    window.addEventListener("parserdesk:notifications-updated", refreshNotifications);
    return () => window.removeEventListener("parserdesk:notifications-updated", refreshNotifications);
  }, []);

  useEffect(() => {
    function refreshUser() {
      api.me()
        .then((me) => setUser(me))
        .catch(() => undefined);
    }
    window.addEventListener("parserdesk:user-updated", refreshUser);
    return () => window.removeEventListener("parserdesk:user-updated", refreshUser);
  }, []);

  return (
    <div className="parsehub-shell">
      <DataLeadHubHeader
        mode="app"
        notificationsCount={notifications?.unread_total || 0}
        onLogout={() => {
          clearToken();
          router.replace("/login");
        }}
      />

      <main className="workspace-main parsehub-main">
        <header className="topbar">
          <div>
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">{actions}</div>
        </header>
        {!ready ? <div className="loading-card">Подключаем кабинет...</div> : children}
      </main>

      <DataLeadHubFooter />
    </div>
  );
}
