"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DataLeadHubFooter, DataLeadHubHeader } from "@/components/parsehub-chrome";
import { getToken } from "@/lib/api";

type AuthState = "checking" | "guest" | "user";

export default function HomePage() {
  const router = useRouter();
  const [authState, setAuthState] = useState<AuthState>("checking");

  useEffect(() => {
    if (getToken()) {
      setAuthState("user");
      router.replace("/jobs");
      return;
    }
    setAuthState("guest");
  }, [router]);

  return (
    <div className="parsehub-shell parsehub-public-shell">
      <DataLeadHubHeader mode="public" />

      <main className="parsehub-main">
        {authState === "checking" || authState === "user" ? (
          <section className="panel-card parsehub-guest-hero">
            <span className="eyebrow">DataLeadHub Platform</span>
            <h1>Открываем рабочий кабинет</h1>
            <p>Если вы уже вошли в систему, мы перенаправим вас на страницу запуска парсеров.</p>
          </section>
        ) : (
          <>
            <section className="panel-card parsehub-guest-hero">
              <span className="eyebrow">DataLeadHub Platform</span>
              <h1>Парсеры запускаются только из личного кабинета</h1>
              <p>
                Персональные задачи, лимиты, результаты и выгрузки доступны после входа.
                На публичной странице мы показываем только возможности платформы.
              </p>
              <div className="parsehub-guest-actions">
                <Link className="parsehub-register-link" href="/register">Создать аккаунт</Link>
                <Link className="parsehub-login-link" href="/login">Войти в кабинет</Link>
              </div>
            </section>

            <section className="parsehub-guest-grid">
              <article className="metric-card metric-neutral">
                <span>Источники</span>
                <strong>2GIS</strong>
                <small>Krisha.kz и OLX подключаются из кабинета.</small>
              </article>
              <article className="metric-card metric-neutral">
                <span>Результаты</span>
                <strong>CSV</strong>
                <small>Выгрузка в CSV и Excel доступна после авторизации.</small>
              </article>
              <article className="metric-card metric-neutral">
                <span>Хранение</span>
                <strong>DB</strong>
                <small>Данные сохраняются в PostgreSQL и привязаны к пользователю.</small>
              </article>
            </section>
          </>
        )}
      </main>

      <DataLeadHubFooter />
    </div>
  );
}
