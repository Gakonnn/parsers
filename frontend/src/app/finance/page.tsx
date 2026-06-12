"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PublicPage } from "@/components/public-page";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { SubscriptionPlan } from "@/lib/types";

function limitText(value: number, unit: string): string {
  return value === -1 ? `Безлимит ${unit}` : `${value} ${unit}`;
}

export default function FinancePage() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .plans()
      .then(setPlans)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить тарифы"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PublicPage
      eyebrow="Тарифы"
      title="Планы под разные объемы данных"
      description="Тарифы публикуются из панели администратора и всегда загружаются из базы данных."
    >
      {loading ? (
        <section className="public-section">
          <h2>Загружаем тарифы</h2>
          <p>Получаем актуальные планы из базы данных.</p>
        </section>
      ) : error ? (
        <section className="public-section">
          <h2>Тарифы временно недоступны</h2>
          <p>{error}</p>
        </section>
      ) : plans.length ? (
        <section className="public-pricing-grid">
          {plans.map((plan) => (
            <article className="public-plan-card" key={plan.id}>
              <span className="soft-badge">{plan.code}</span>
              <strong>{formatMoney(plan.price_kzt, plan.currency)}</strong>
              <p>{plan.description || plan.name}</p>
              <ul>
                <li>{limitText(plan.max_jobs_per_month, "запусков / месяц")}</li>
                <li>{limitText(plan.max_records_per_month, "записей / месяц")}</li>
                <li>{plan.allowed_sources.length ? plan.allowed_sources.join(", ") : "Все источники"}</li>
              </ul>
              <Link className="primary-button wide" href="/register">
                Подключить тариф
              </Link>
            </article>
          ))}
        </section>
      ) : (
        <section className="public-section">
          <h2>Тарифы ещё не опубликованы</h2>
          <p>Администратор может добавить тарифы в панели управления. После публикации они появятся здесь автоматически.</p>
          <Link className="primary-button" href="/register">
            Создать аккаунт
          </Link>
        </section>
      )}
    </PublicPage>
  );
}
