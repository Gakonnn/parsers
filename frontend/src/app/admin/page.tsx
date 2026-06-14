"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, formatMoney, truncateMiddle } from "@/lib/format";
import type { AuditLog, Invoice, SubscriptionPlan, SupportMessage, User } from "@/lib/types";

const sourceOptions = ["olx", "krisha", "2gis"];

type PlanForm = {
  code: string;
  name: string;
  description: string;
  price_kzt: number;
  max_records_per_month: number;
  allowed_sources: string[];
  is_public: boolean;
};

const initialPlanForm: PlanForm = {
  code: "business",
  name: "Business",
  description: "Коммерческий тариф для регулярного парсинга и выгрузок.",
  price_kzt: 25000,
  max_records_per_month: 10000,
  allowed_sources: ["olx", "krisha", "2gis"],
  is_public: true,
};

export default function AdminPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [supportMessages, setSupportMessages] = useState<SupportMessage[]>([]);
  const [selectedPlanByUser, setSelectedPlanByUser] = useState<Record<string, string>>({});
  const [planForm, setPlanForm] = useState<PlanForm>(initialPlanForm);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  const usersById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);

  async function load() {
    const [usersResponse, auditResponse, invoiceResponse, planResponse, supportResponse] = await Promise.all([
      api.adminUsers(),
      api.adminAudit(),
      api.adminInvoices(),
      api.adminPlans(),
      api.adminSupportMessages(),
    ]);
    setUsers(usersResponse.items);
    setAudit(auditResponse.items);
    setInvoices(invoiceResponse.items);
    setPlans(planResponse);
    setSupportMessages(supportResponse.items);
    setSelectedPlanByUser((current) => {
      const next = { ...current };
      usersResponse.items.forEach((user) => {
        if (!next[user.id]) next[user.id] = planResponse[0]?.code || "";
      });
      return next;
    });
  }

  useEffect(() => {
    load().catch((err) => setError(err instanceof Error ? err.message : "Нет доступа к админке"));
  }, []);

  function setPlanField<K extends keyof PlanForm>(key: K, value: PlanForm[K]) {
    setPlanForm((current) => ({ ...current, [key]: value }));
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create-plan");
    setMessage("");
    try {
      await api.adminCreatePlan({
        code: planForm.code.trim().toLowerCase(),
        name: planForm.name.trim(),
        description: planForm.description.trim() || null,
        price_kzt: Number(planForm.price_kzt) || 0,
        currency: "KZT",
        billing_period: "monthly",
        max_records_per_month: Number(planForm.max_records_per_month),
        allowed_sources: planForm.allowed_sources,
        is_active: true,
        is_public: planForm.is_public,
      });
      setPlanForm(initialPlanForm);
      setMessage("Тариф создан.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось создать тариф");
    } finally {
      setBusy("");
    }
  }

  async function updateUser(user: User, patch: Partial<Pick<User, "role" | "is_active" | "is_verified">>) {
    setBusy(`user-${user.id}`);
    setMessage("");
    try {
      await api.adminUpdateUser(user.id, patch);
      setMessage("Пользователь обновлен.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось обновить пользователя");
    } finally {
      setBusy("");
    }
  }

  async function assignPlan(user: User) {
    const planCode = selectedPlanByUser[user.id];
    if (!planCode) return;
    setBusy(`assign-${user.id}`);
    setMessage("");
    try {
      await api.adminAssignSubscription(user.id, planCode);
      setMessage(`Тариф ${planCode} назначен пользователю ${user.email}.`);
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось назначить тариф");
    } finally {
      setBusy("");
    }
  }

  async function togglePlan(plan: SubscriptionPlan, field: "is_active" | "is_public") {
    setBusy(`plan-${plan.id}`);
    setMessage("");
    try {
      await api.adminUpdatePlan(plan.id, { [field]: !plan[field] });
      setMessage("Тариф обновлен.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось обновить тариф");
    } finally {
      setBusy("");
    }
  }

  async function markInvoicePaid(invoice: Invoice) {
    setBusy(`invoice-${invoice.id}`);
    setMessage("");
    try {
      await api.adminMarkInvoicePaid(invoice.id);
      setMessage("Счет подтвержден как оплаченный.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось подтвердить оплату");
    } finally {
      setBusy("");
    }
  }

  async function updateSupportMessage(item: SupportMessage, status: "new" | "in_progress" | "closed") {
    setBusy(`support-${item.id}`);
    setMessage("");
    try {
      await api.adminUpdateSupportMessage(item.id, status);
      setMessage("Статус обращения обновлен.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось обновить обращение");
    } finally {
      setBusy("");
    }
  }

  if (error) {
    return (
      <AppShell eyebrow="Администрирование" title="Админ-панель">
        <div className="panel-card">
          <EmptyState title="Нет доступа" text={error} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell eyebrow="Администрирование" title="Админ-панель">
      {message ? <div className={message.includes("Не удалось") ? "form-message error admin-message" : "form-message admin-message"}>{message}</div> : null}

      <section className="panel-card admin-support-panel">
        <div className="section-heading horizontal">
          <div><span className="eyebrow">Поддержка</span><h2>Обращения с сайта</h2></div>
          <button className="ghost-button" type="button" onClick={() => load().catch(() => undefined)}>Обновить</button>
        </div>
        {supportMessages.length ? (
          <div className="admin-support-list">
            {supportMessages.map((item) => (
              <article className="admin-support-card" key={item.id}>
                <div className="admin-support-main">
                  <div>
                    <strong>{item.name}</strong>
                    <span>{item.email}{item.phone ? ` · ${item.phone}` : ""}</span>
                  </div>
                  <StatusPill status={item.status} />
                </div>
                <p>{item.message}</p>
                <div className="admin-support-footer">
                  <small>{formatDate(item.created_at)} · {item.source}</small>
                  <div className="button-row">
                    <button className="ghost-button small-button" disabled={busy === `support-${item.id}` || item.status === "new"} type="button" onClick={() => updateSupportMessage(item, "new").catch(() => undefined)}>Новое</button>
                    <button className="ghost-button small-button" disabled={busy === `support-${item.id}` || item.status === "in_progress"} type="button" onClick={() => updateSupportMessage(item, "in_progress").catch(() => undefined)}>В работе</button>
                    <button className="ghost-button small-button" disabled={busy === `support-${item.id}` || item.status === "closed"} type="button" onClick={() => updateSupportMessage(item, "closed").catch(() => undefined)}>Закрыто</button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Обращений пока нет" text="Сообщения из формы поддержки появятся здесь." />
        )}
      </section>

      <section className="admin-control-grid">
        <div className="panel-card admin-users-panel">
          <div className="section-heading horizontal">
            <div><span className="eyebrow">Пользователи</span><h2>Пользователи и доступ</h2></div>
            <button className="ghost-button" type="button" onClick={() => load().catch(() => undefined)}>Обновить</button>
          </div>
          <div className="admin-user-list">
            {users.map((user) => (
              <article className="admin-user-card" key={user.id}>
                <div className="admin-user-main">
                  <strong>{user.full_name || user.email}</strong>
                  <span>{user.email}</span>
                  <small>{truncateMiddle(user.id)}</small>
                </div>
                <div className="admin-user-controls">
                  <label>
                    <span>Роль</span>
                    <select value={user.role} disabled={busy === `user-${user.id}`} onChange={(event) => updateUser(user, { role: event.target.value }).catch(() => undefined)}>
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </label>
                  <label>
                    <span>Статус</span>
                    <select value={user.is_active ? "active" : "blocked"} disabled={busy === `user-${user.id}`} onChange={(event) => updateUser(user, { is_active: event.target.value === "active" }).catch(() => undefined)}>
                      <option value="active">Активен</option>
                      <option value="blocked">Отключен</option>
                    </select>
                  </label>
                  <label>
                    <span>Тариф</span>
                    <select value={selectedPlanByUser[user.id] || ""} onChange={(event) => setSelectedPlanByUser((current) => ({ ...current, [user.id]: event.target.value }))}>
                      {plans.map((plan) => <option key={plan.id} value={plan.code}>{plan.name} ({plan.code})</option>)}
                    </select>
                  </label>
                  <button className="primary-button" disabled={!plans.length || busy === `assign-${user.id}`} type="button" onClick={() => assignPlan(user).catch(() => undefined)}>
                    Назначить
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="panel-card plan-builder-card">
          <div className="section-heading"><span className="eyebrow">Тарифы</span><h2>Создать тариф</h2></div>
          <form className="admin-form" onSubmit={createPlan}>
            <div className="form-grid two equal">
              <label className="field-block compact"><span>Код</span><input value={planForm.code} onChange={(event) => setPlanField("code", event.target.value)} required /></label>
              <label className="field-block compact"><span>Название</span><input value={planForm.name} onChange={(event) => setPlanField("name", event.target.value)} required /></label>
            </div>
            <label className="field-block compact"><span>Описание</span><input value={planForm.description} onChange={(event) => setPlanField("description", event.target.value)} /></label>
            <div className="form-grid two equal">
              <label className="field-block compact"><span>Цена KZT</span><input min={0} type="number" value={planForm.price_kzt} onChange={(event) => setPlanField("price_kzt", Number(event.target.value))} /></label>
              <label className="field-block compact"><span>Записей / месяц</span><input min={-1} type="number" value={planForm.max_records_per_month} onChange={(event) => setPlanField("max_records_per_month", Number(event.target.value))} /></label>
            </div>
            <div className="source-checkboxes">
              {sourceOptions.map((source) => (
                <label key={source}>
                  <input
                    checked={planForm.allowed_sources.includes(source)}
                    type="checkbox"
                    onChange={(event) => {
                      setPlanField(
                        "allowed_sources",
                        event.target.checked
                          ? [...planForm.allowed_sources, source]
                          : planForm.allowed_sources.filter((item) => item !== source),
                      );
                    }}
                  />
                  {source}
                </label>
              ))}
            </div>
            <label className="toggle-line"><input checked={planForm.is_public} type="checkbox" onChange={(event) => setPlanField("is_public", event.target.checked)} /> Публичный тариф</label>
            <button className="primary-button wide" disabled={busy === "create-plan"} type="submit">Создать тариф</button>
          </form>
        </div>
      </section>

      <section className="admin-grid">
        <div className="panel-card">
          <div className="section-heading"><span className="eyebrow">Каталог тарифов</span><h2>Тарифы</h2></div>
          <div className="plan-admin-list">
            {plans.map((plan) => (
              <article key={plan.id}>
                <div>
                  <strong>{plan.name}</strong>
                  <span>{plan.code} · {formatMoney(plan.price_kzt, plan.currency)}</span>
                </div>
                <small>{plan.max_records_per_month} записей · {plan.allowed_sources.join(", ") || "all"}</small>
                <div className="button-row">
                  <button className="ghost-button" disabled={busy === `plan-${plan.id}`} type="button" onClick={() => togglePlan(plan, "is_active").catch(() => undefined)}>{plan.is_active ? "Отключить" : "Включить"}</button>
                  <button className="ghost-button" disabled={busy === `plan-${plan.id}`} type="button" onClick={() => togglePlan(plan, "is_public").catch(() => undefined)}>{plan.is_public ? "Скрыть" : "Опубликовать"}</button>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="panel-card">
          <div className="section-heading"><span className="eyebrow">Оплаты</span><h2>Счета</h2></div>
          <div className="data-table invoices-table admin-invoices-table">
            <div className="table-row table-head"><span>Клиент</span><span>Сумма</span><span>Статус</span><span>Действие</span></div>
            {invoices.map((invoice) => (
              <div className="table-row" key={invoice.id}>
                <span>{usersById.get(invoice.user_id)?.email || truncateMiddle(invoice.user_id)}</span>
                <span>{formatMoney(invoice.amount_kzt, invoice.currency)}</span>
                <span><StatusPill status={invoice.status} /></span>
                <span>
                  <button className="ghost-button small-button" disabled={invoice.status === "paid" || busy === `invoice-${invoice.id}`} type="button" onClick={() => markInvoicePaid(invoice).catch(() => undefined)}>
                    Подтвердить
                  </button>
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel-card">
        <div className="section-heading horizontal">
          <div><span className="eyebrow">Журнал</span><h2>Журнал действий</h2></div>
          <button className="ghost-button" type="button" onClick={() => load().catch(() => undefined)}>Обновить</button>
        </div>
        <div className="audit-list">
          {audit.map((item) => (
            <article key={item.id}>
              <span>{formatDate(item.created_at)}</span>
              <strong>{item.event_type}</strong>
              <p>{item.message || item.entity_type || "system event"}</p>
              <small>{truncateMiddle(item.entity_id || item.id)}</small>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
