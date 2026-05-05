"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api, clearToken, getToken } from "@/lib/api";
import type { NotificationList, User } from "@/lib/types";

const navigation = [
  { href: "/dashboard", label: "Обзор", short: "OV" },
  { href: "/settings", label: "Кабинет", short: "SC" },
  { href: "/jobs", label: "Парсеры", short: "PR" },
  { href: "/results", label: "Результаты", short: "DB" },
  { href: "/billing", label: "Тарифы", short: "₸" },
  { href: "/notifications", label: "Уведомления", short: "NT" },
  { href: "/admin", label: "Админка", short: "AD", adminOnly: true },
];

export function AppShell({ children, eyebrow, title, actions }: { children: ReactNode; eyebrow: string; title: string; actions?: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [notifications, setNotifications] = useState<NotificationList | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/");
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
        router.replace("/");
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

  const visibleNavigation = navigation.filter((item) => !item.adminOnly || user?.role === "admin");

  return (
    <div className="workspace-shell">
      <aside className="sidebar-panel">
        <Link className="brand-lockup" href="/dashboard">
          <span className="brand-mark">P</span>
          <span>
            <strong>ParserDesk</strong>
            <small>data operations</small>
          </span>
        </Link>

        <nav className="nav-stack">
          {visibleNavigation.map((item) => (
            <Link key={item.href} className={pathname === item.href ? "active" : ""} href={item.href}>
              <span>{item.short}</span>
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="operator-card">
          <span className="operator-label">Аккаунт</span>
          <strong>{user?.full_name || user?.email || "Загрузка"}</strong>
          <small>{user?.role === "admin" ? "Администратор" : "Пользователь"}</small>
          <button
            className="ghost-button wide"
            type="button"
            onClick={() => {
              clearToken();
              router.replace("/");
            }}
          >
            Выйти
          </button>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="topbar">
          <div>
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <Link className="notification-chip" href="/notifications">
              <span>{notifications?.unread_total || 0}</span>
              новых
            </Link>
            {actions}
          </div>
        </header>
        {!ready ? <div className="loading-card">Подключаем кабинет...</div> : children}
      </main>
    </div>
  );
}
