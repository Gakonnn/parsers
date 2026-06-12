"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import { api, clearToken, getToken } from "@/lib/api";
import { formatDate, percent } from "@/lib/format";
import type { ParserJob, UsageSummary } from "@/lib/types";

type HomeTask = {
  id: string;
  source: string;
  status: string;
  progress: number;
  count: string;
  date: string;
};

type AuthState = "checking" | "guest" | "user";

function toTask(job: ParserJob): HomeTask {
  const value = percent(job.progress_current, job.progress_total);
  return {
    id: job.id,
    source: job.source.toUpperCase(),
    status: job.status === "completed" ? "Готово" : job.status === "running" ? "В работе" : job.status,
    progress: value,
    count: `${job.progress_current}/${job.progress_total || "?"}`,
    date: formatDate(job.created_at),
  };
}

export default function HomePage() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [jobs, setJobs] = useState<ParserJob[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => {
    if (!getToken()) {
      setAuthState("guest");
      return;
    }
    setAuthState("user");
    Promise.all([api.jobs(false), api.usage().catch(() => null)])
      .then(([jobsResponse, usageResponse]) => {
        setJobs(jobsResponse.items);
        setUsage(usageResponse);
      })
      .catch(() => {
        clearToken();
        setAuthState("guest");
      });
  }, []);

  const tasks = useMemo(() => jobs.slice(0, 6).map(toTask), [jobs]);
  const activeJobs = jobs.filter((job) => ["pending", "running"].includes(job.status)).length;
  const completed = jobs.filter((job) => job.status === "completed").length;
  const recordsUsed = usage?.records_used ?? 0;
  const recordsLimit = usage?.subscription.plan.max_records_per_month ?? 0;
  const recordsPercent = percent(recordsUsed, recordsLimit);
  const planName = usage?.subscription.plan.name || "Тариф";
  const jobsRemaining = usage?.jobs_remaining ?? 0;

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
        {authState === "user" ? (
          <>
            <section className="dashboard-grid">
              <article className="metric-card metric-neutral">
                <span>Активные задачи</span>
                <strong>{activeJobs}</strong>
                <small>очередь и выполнение</small>
              </article>
              <article className="metric-card metric-neutral">
                <span>Успешные запуски</span>
                <strong>{completed}</strong>
                <small>последние задачи</small>
              </article>
              <article className="metric-card metric-neutral">
                <span>Тариф</span>
                <strong className="parsehub-plan-name">{planName}</strong>
                <small>{jobsRemaining} запусков осталось</small>
              </article>
              <article className="usage-card">
                <div className="progress-ring" style={{ "--progress": `${recordsPercent * 3.6}deg` } as CSSProperties}>
                  <div>
                    <strong>{recordsPercent}%</strong>
                    <span>records</span>
                  </div>
                </div>
                <div>
                  <span className="eyebrow">Лимит записей</span>
                  <strong>{recordsUsed} / {recordsLimit}</strong>
                  <p>Месячное использование по текущему тарифу.</p>
                </div>
              </article>
            </section>

            <section className="panel-card parsehub-home-table">
              <div className="section-heading">
                <span className="eyebrow">Последняя активность</span>
                <h2>Последние задачи</h2>
              </div>
              <div className="table-card">
                <div className="data-table home-table">
                  <div className="table-row table-head">
                    <span>Источник</span>
                    <span>Статус</span>
                    <span>Прогресс</span>
                    <span>Запуск</span>
                  </div>
                  {tasks.length ? (
                    tasks.map((task) => (
                      <div className="table-row" key={task.id}>
                        <span className="source-cell">{task.source}</span>
                        <span><span className="status-pill status-completed">{task.status}</span></span>
                        <span>
                          <div className="inline-progress"><i style={{ width: `${task.progress}%` }} /></div>
                          <small>{task.count}</small>
                        </span>
                        <span>{task.date}</span>
                      </div>
                    ))
                  ) : (
                    <div className="table-row parsehub-empty-row">
                      <span>Пока нет запусков</span>
                      <span>После первого парсинга здесь появится история задач.</span>
                    </div>
                  )}
                </div>
              </div>
            </section>
          </>
        ) : (
          <>
            <section className="panel-card parsehub-guest-hero">
              <span className="eyebrow">ParseHub Platform</span>
              <h1>Парсеры запускаются только из личного кабинета</h1>
              <p>
                Персональные задачи, лимиты, результаты и выгрузки доступны после входа.
                На публичной странице мы показываем только возможности платформы, без чужих или демо-данных.
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
                <small>Krisha.kz, OLX и другие парсеры подключаются из кабинета.</small>
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
