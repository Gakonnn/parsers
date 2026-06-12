"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import type { Invoice, SubscriptionPlan, UsageSummary } from "@/lib/types";

function limitLabel(value: number, suffix: string): string {
  return value === -1 ? "Безлимит" : `${value}${suffix ? ` ${suffix}` : ""}`;
}

function perRecordLabel(plan: SubscriptionPlan): string {
  if (plan.max_records_per_month <= 0 || plan.price_kzt <= 0) return formatMoney(0, plan.currency);
  return formatMoney(Math.ceil(plan.price_kzt / plan.max_records_per_month), plan.currency);
}

export default function BillingPage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [message, setMessage] = useState("");

  async function load() {
    const [usageResponse, plansResponse, invoicesResponse] = await Promise.all([api.usage(), api.plans(), api.invoices()]);
    setUsage(usageResponse);
    setPlans(plansResponse);
    setInvoices(invoicesResponse.items);
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : "Не удалось загрузить тарифы"));
  }, []);

  async function createInvoice(planCode: string) {
    setMessage("");
    try {
      const invoice = await api.createInvoice(planCode);
      setMessage(
        invoice.payment_url
          ? "Счет создан. Перейдите по ссылке оплаты из истории счетов."
          : "Счет создан. Оплата будет обработана через подключенного провайдера или администратором.",
      );
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось создать счет");
    }
  }

  return (
    <AppShell eyebrow="Оплата" title="Тарифы и оплата">
      <section className="billing-hero parsehub-billing-hero">
        <div>
          <span className="eyebrow">Текущий тариф</span>
          <h2>{usage?.subscription.plan.name || "—"}</h2>
          <p>{usage?.jobs_used ?? 0} запусков и {usage?.records_used ?? 0} записей использовано в этом месяце.</p>
        </div>
        <StatusPill status={usage?.subscription.status || "active"} />
      </section>

      <section className="plans-grid parsehub-pricing-grid">
        {plans.map((plan) => (
          <article className={`plan-card parsehub-plan-card${usage?.subscription.plan.code === plan.code ? " selected" : ""}`} key={plan.id}>
            <div className="parsehub-plan-band">{plan.code}</div>
            <div className="parsehub-plan-body">
              <h3>{plan.name}</h3>
              <p>{plan.description || "Премиальные лимиты для ваших задач."}</p>
              <strong className="parsehub-price">{formatMoney(plan.price_kzt, plan.currency)}</strong>
              <span className="parsehub-price-period">в месяц</span>
              <ul>
                <li><span>Запусков:</span><strong>{limitLabel(plan.max_jobs_per_month, "")}</strong></li>
                <li><span>Записей:</span><strong>{limitLabel(plan.max_records_per_month, "")}</strong></li>
                <li><span>Цена за 1 запись:</span><em>{perRecordLabel(plan)}</em></li>
              </ul>
              <button
                className="primary-button wide parsehub-plan-button"
                disabled={usage?.subscription.plan.code === plan.code}
                type="button"
                onClick={() => createInvoice(plan.code)}
              >
                {usage?.subscription.plan.code === plan.code ? "Выбрано" : "Выбрать тариф"}
              </button>
            </div>
          </article>
        ))}
      </section>

      {message ? <p className="form-message">{message}</p> : null}

      <section className="panel-card parsehub-invoices-card">
        <div className="section-heading">
          <span className="eyebrow">Документация</span>
          <h2>История счетов</h2>
        </div>
        <div className="data-table invoices-table">
          <div className="table-row table-head"><span>Тариф</span><span>Сумма</span><span>Статус</span><span>Дата</span></div>
          {invoices.map((invoice) => (
            <div className="table-row" key={invoice.id}>
              <span>{invoice.plan.name}</span>
              <span>{formatMoney(invoice.amount_kzt, invoice.currency)}</span>
              <span><StatusPill status={invoice.status} /></span>
              <span>{formatDate(invoice.created_at)}</span>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
