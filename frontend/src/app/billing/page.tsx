"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import type { Invoice, SubscriptionPlan, UsageSummary } from "@/lib/types";

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
      await api.createInvoice(planCode);
      setMessage("Счет создан. На следующем этапе подключим реальную платежную страницу.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось создать счет");
    }
  }

  return (
    <AppShell eyebrow="Оплата" title="Тарифы и оплата">
      <section className="billing-hero">
        <div>
          <span className="eyebrow">Текущий тариф</span>
          <h2>{usage?.subscription.plan.name || "Free"}</h2>
          <p>{usage?.jobs_used ?? 0} запусков и {usage?.records_used ?? 0} записей использовано в этом месяце.</p>
        </div>
        <StatusPill status={usage?.subscription.status || "active"} />
      </section>

      <section className="plans-grid">
        {plans.map((plan) => (
          <article className="plan-card" key={plan.id}>
            <span className="soft-badge">{plan.code}</span>
            <h3>{plan.name}</h3>
            <p>{plan.description || "Тариф для управления парсерами и выгрузками."}</p>
            <strong>{formatMoney(plan.price_kzt, plan.currency)}</strong>
            <ul>
              <li>{plan.max_jobs_per_month === -1 ? "Безлимит" : plan.max_jobs_per_month} запусков / месяц</li>
              <li>{plan.max_records_per_month === -1 ? "Безлимит" : plan.max_records_per_month} записей / месяц</li>
              <li>{plan.allowed_sources.length ? plan.allowed_sources.join(", ") : "Все источники"}</li>
            </ul>
            <button className="primary-button wide" type="button" onClick={() => createInvoice(plan.code)}>Выбрать тариф</button>
          </article>
        ))}
      </section>

      {message ? <p className="form-message">{message}</p> : null}

      <section className="panel-card">
        <div className="section-heading">
          <span className="eyebrow">Счета</span>
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
