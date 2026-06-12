"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api, clearToken, getToken } from "@/lib/api";
import type { NotificationList, User } from "@/lib/types";

const navigation = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/marketing", label: "Парсеры", aliases: ["/jobs"] },
  { href: "/structure", label: "Результаты", aliases: ["/results"] },
  { href: "/billing", label: "Тарифы", aliases: ["/orders", "/cart"] },
  { href: "/profile", label: "Кабинет", aliases: ["/settings"] },
];

export function AppShell({ children, eyebrow, title, actions }: { children: ReactNode; eyebrow: string; title: string; actions?: ReactNode }) {
  const pathname = usePathname();
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
      <header className="parsehub-header">
        <div className="parsehub-header-inner">
          <Link className="parsehub-brand" href="/dashboard" aria-label="ParseHub dashboard">
            <span className="parsehub-logo-wrap">
              <img src="/logo/logo.png" alt="" />
            </span>
            <strong>ParseHub</strong>
          </Link>

          <nav className="parsehub-nav" aria-label="Основная навигация">
            {navigation.map((item) => (
              <Link key={item.href} className={pathname === item.href || item.aliases?.includes(pathname) ? "active" : ""} href={item.href}>
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="parsehub-userbar">
            <Link className="parsehub-login-link" href="/notifications">
              Уведомления{notifications?.unread_total ? ` (${notifications.unread_total})` : ""}
            </Link>
            <button
              className="parsehub-register-link"
              type="button"
              onClick={() => {
                clearToken();
                router.replace("/login");
              }}
            >
              Выйти
            </button>
          </div>
        </div>
      </header>

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

      <footer className="parsehub-footer">
        <div>
          <h3>Документы и информация</h3>
          <Link href="/about">О нас</Link>
          <Link href="/privacy">Политика конфиденциальности</Link>
          <Link href="/offer">Оферта</Link>
          <Link href="/payment">Оплата</Link>
          <Link href="/guide">Инструкция</Link>
        </div>
        <div>
          <h3>Социальные сети</h3>
          <div className="parsehub-socials">
            <a href="#" aria-label="YouTube">YT</a>
            <a href="#" aria-label="Instagram">IG</a>
            <a href="#" aria-label="Telegram">TG</a>
            <a href="#" aria-label="WhatsApp">WA</a>
          </div>
        </div>
        <div>
          <h3>Служба поддержки ParseHub</h3>
          <p>Поддержка по задачам, выгрузкам, тарифам и настройкам доступа.</p>
        </div>
      </footer>
    </div>
  );
}
