"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PublicPage } from "@/components/public-page";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { SubscriptionPlan } from "@/lib/types";

function limitText(value: number, unit: string): string {
  return value === -1 ? `Безлимит${unit ? ` ${unit}` : ""}` : `${value}${unit ? ` ${unit}` : ""}`;
}

function perRecordText(plan: SubscriptionPlan): string {
  if (plan.max_records_per_month <= 0 || plan.price_kzt <= 0) return formatMoney(0, plan.currency);
  return formatMoney(Math.ceil(plan.price_kzt / plan.max_records_per_month), plan.currency);
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
        <section className="public-pricing-grid parsehub-pricing-grid parsehub-public-pricing-grid">
          {plans.map((plan) => (
            <article className="public-plan-card parsehub-plan-card" key={plan.id}>
              <div className="parsehub-plan-band">{plan.code}</div>
              <div className="parsehub-plan-body">
              <h2>{plan.name}</h2>
              <p>{plan.description || "Премиальные лимиты для ваших задач."}</p>
              <strong className="parsehub-price">{formatMoney(plan.price_kzt, plan.currency)}</strong>
              <span className="parsehub-price-period">в месяц</span>
              <ul>
                <li><span>Запусков:</span><strong>{limitText(plan.max_jobs_per_month, "")}</strong></li>
                <li><span>Записей:</span><strong>{limitText(plan.max_records_per_month, "")}</strong></li>
                <li><span>Цена за 1 запись:</span><em>{perRecordText(plan)}</em></li>
              </ul>
              <Link className="primary-button wide" href="/register">
                Подключить тариф
              </Link>
              </div>
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
