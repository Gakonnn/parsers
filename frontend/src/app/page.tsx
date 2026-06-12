"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

type AuthState = "checking" | "guest" | "user";

export default function HomePage() {
  const router = useRouter();
  const [authState, setAuthState] = useState<AuthState>("checking");

  useEffect(() => {
    if (getToken()) {
      setAuthState("user");
      router.replace("/dashboard");
      return;
    }
    setAuthState("guest");
  }, [router]);

  return (
    <div className="parsehub-shell parsehub-public-shell">
      <header className="parsehub-header">
        <div className="parsehub-header-inner">
          <Link className="parsehub-brand" href="/">
            <span className="parsehub-logo-wrap"><img src="/logo/logo.png" alt="" /></span>
            <strong>ParseHub</strong>
          </Link>
          <nav className="parsehub-nav" aria-label="Публичная навигация">
            <Link href="/">Обзор</Link>
            <Link href="/marketing">Парсеры</Link>
            <Link href="/structure">Результаты</Link>
            <Link href="/finance">Тарифы</Link>
            <Link href="/profile">Кабинет</Link>
          </nav>
          <div className="parsehub-userbar">
            <Link className="parsehub-login-link" href="/login">Вход</Link>
            <Link className="parsehub-register-link" href="/register">Регистрация</Link>
          </div>
        </div>
      </header>

      <main className="parsehub-main">
        {authState === "checking" || authState === "user" ? (
          <section className="panel-card parsehub-guest-hero">
            <span className="eyebrow">ParseHub Platform</span>
            <h1>Открываем рабочий кабинет</h1>
            <p>Если вы уже вошли в систему, мы перенаправим вас на страницу запуска парсеров.</p>
          </section>
        ) : (
          <>
            <section className="panel-card parsehub-guest-hero">
              <span className="eyebrow">ParseHub Platform</span>
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
