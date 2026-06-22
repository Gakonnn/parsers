"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, formatMoney, truncateMiddle } from "@/lib/format";
import type { AuditLog, Invoice, PaymentQrSetting, SubscriptionPlan, SupportMessage, UsageSummary, User } from "@/lib/types";

const sourceOptions = ["olx", "krisha", "2gis"];

type AdminSection = "support" | "users" | "plans" | "billing" | "audit";

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

type PaymentQrForm = {
  title: string;
  note: string;
  image_data: string;
  is_active: boolean;
};

const initialPaymentQrForm: PaymentQrForm = {
  title: "Kaspi QR",
  note: "Отсканируйте QR, оплатите тариф и отправьте ID чека.",
  image_data: "",
  is_active: true,
};

function receiptIdForInvoice(invoice: Invoice): string {
  const meta = invoice.metadata_json?.manual_qr;
  if (!meta || typeof meta !== "object" || Array.isArray(meta)) return invoice.provider_invoice_id || "-";
  const receiptId = (meta as { receipt_id?: unknown }).receipt_id;
  return typeof receiptId === "string" && receiptId.trim() ? receiptId : invoice.provider_invoice_id || "-";
}

const limitNumberFormatter = new Intl.NumberFormat("ru-KZ");

function formatLimitNumber(value?: number | null): string {
  if (value === undefined || value === null) return "-";
  if (value < 0) return "Безлимит";
  return limitNumberFormatter.format(value);
}

function formatRemainingRecords(usage?: UsageSummary): string {
  if (!usage) return "-";
  if (usage.subscription.plan.max_records_per_month < 0) return "Безлимит";
  return limitNumberFormatter.format(Math.max(0, usage.records_remaining));
}

function recordsLimitPercent(usage?: UsageSummary): number {
  const total = usage?.subscription.plan.max_records_per_month ?? 0;
  const used = usage?.records_used ?? 0;
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, (used / total) * 100));
}

export default function AdminPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [usageByUser, setUsageByUser] = useState<Record<string, UsageSummary>>({});
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [supportMessages, setSupportMessages] = useState<SupportMessage[]>([]);
  const [paymentQr, setPaymentQr] = useState<PaymentQrSetting | null>(null);
  const [selectedPlanByUser, setSelectedPlanByUser] = useState<Record<string, string>>({});
  const [planForm, setPlanForm] = useState<PlanForm>(initialPlanForm);
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const [paymentQrForm, setPaymentQrForm] = useState<PaymentQrForm>(initialPaymentQrForm);
  const [activeSection, setActiveSection] = useState<AdminSection>("support");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  const usersById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const pendingSupportCount = supportMessages.length;
  const pendingInvoiceCount = invoices.filter((invoice) => invoice.status !== "paid").length;
  const publicPlanCount = plans.filter((plan) => plan.is_public && plan.is_active).length;

  const sections: Array<{ key: AdminSection; label: string; hint: string; count: number }> = [
    { key: "support", label: "Поддержка", hint: "Обращения", count: pendingSupportCount },
    { key: "users", label: "Пользователи", hint: "Доступы", count: users.length },
    { key: "plans", label: "Тарифы", hint: "Планы", count: plans.length },
    { key: "billing", label: "Оплаты", hint: "Счета", count: pendingInvoiceCount },
    { key: "audit", label: "Журнал", hint: "События", count: audit.length },
  ];

  async function load() {
    const [usersResponse, auditResponse, invoiceResponse, planResponse, supportResponse, paymentQrResponse] = await Promise.all([
      api.adminUsers(),
      api.adminAudit(),
      api.adminInvoices(),
      api.adminPlans(),
      api.adminSupportMessages(),
      api.adminPaymentQr(),
    ]);
    setUsers(usersResponse.items);
    setAudit(auditResponse.items);
    setInvoices(invoiceResponse.items);
    setPlans(planResponse);
    setSupportMessages(supportResponse.items);
    setPaymentQr(paymentQrResponse);
    const usageEntries = await Promise.allSettled(
      usersResponse.items.map(async (user) => [user.id, await api.adminUserUsage(user.id)] as const),
    );
    const nextUsageByUser: Record<string, UsageSummary> = {};
    usageEntries.forEach((entry) => {
      if (entry.status === "fulfilled") nextUsageByUser[entry.value[0]] = entry.value[1];
    });
    setUsageByUser(nextUsageByUser);
    setPaymentQrForm(
      paymentQrResponse
        ? {
            title: paymentQrResponse.title,
            note: paymentQrResponse.note || "",
            image_data: paymentQrResponse.image_data || "",
            is_active: paymentQrResponse.is_active,
          }
        : initialPaymentQrForm,
    );
    setSelectedPlanByUser((current) => {
      const next = { ...current };
      usersResponse.items.forEach((user) => {
        if (!next[user.id]) next[user.id] = planResponse[0]?.code || "";
      });
      return next;
    });
  }

  function refreshAdmin() {
    setMessage("");
    load().catch((err) => setError(err instanceof Error ? err.message : "Нет доступа к админке"));
  }

  useEffect(() => {
    refreshAdmin();
  }, []);

  function setPlanField<K extends keyof PlanForm>(key: K, value: PlanForm[K]) {
    setPlanForm((current) => ({ ...current, [key]: value }));
  }

  function setPaymentQrField<K extends keyof PaymentQrForm>(key: K, value: PaymentQrForm[K]) {
    setPaymentQrForm((current) => ({ ...current, [key]: value }));
  }

  function handlePaymentQrFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") setPaymentQrField("image_data", reader.result);
    };
    reader.readAsDataURL(file);
  }

  async function savePaymentQr(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("payment-qr");
    setMessage("");
    try {
      const updated = await api.adminUpdatePaymentQr({
        title: paymentQrForm.title.trim() || "Kaspi QR",
        note: paymentQrForm.note.trim() || null,
        image_data: paymentQrForm.image_data,
        is_active: paymentQrForm.is_active,
      });
      setPaymentQr(updated);
      setMessage("QR-код оплаты сохранен.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось сохранить QR-код");
    } finally {
      setBusy("");
    }
  }

  async function savePlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(editingPlanId ? `save-plan-${editingPlanId}` : "create-plan");
    setMessage("");
    try {
      const payload = {
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
      };
      if (editingPlanId) {
        await api.adminUpdatePlan(editingPlanId, payload);
      } else {
        await api.adminCreatePlan(payload);
      }
      setPlanForm(initialPlanForm);
      setEditingPlanId(null);
      setMessage(editingPlanId ? "Тариф обновлен." : "Тариф создан.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось сохранить тариф");
    } finally {
      setBusy("");
    }
  }

  function editPlan(plan: SubscriptionPlan) {
    setEditingPlanId(plan.id);
    setPlanForm({
      code: plan.code,
      name: plan.name,
      description: plan.description || "",
      price_kzt: plan.price_kzt,
      max_records_per_month: plan.max_records_per_month,
      allowed_sources: plan.allowed_sources,
      is_public: plan.is_public,
    });
    setActiveSection("plans");
  }

  async function deletePlan(plan: SubscriptionPlan) {
    if (!window.confirm(`Удалить тариф "${plan.name}" из каталога?`)) return;
    setBusy(`delete-plan-${plan.id}`);
    setMessage("");
    try {
      await api.adminDeletePlan(plan.id);
      if (editingPlanId === plan.id) {
        setEditingPlanId(null);
        setPlanForm(initialPlanForm);
      }
      setMessage("Тариф удален.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось удалить тариф");
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

  async function deleteUser(user: User) {
    if (!window.confirm(`Удалить пользователя ${user.email}?`)) return;
    setBusy(`delete-user-${user.id}`);
    setMessage("");
    try {
      await api.adminDeleteUser(user.id);
      setMessage("Пользователь удален.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось удалить пользователя");
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

  async function deleteSupportMessage(item: SupportMessage) {
    if (!window.confirm(`Удалить обращение от ${item.email}?`)) return;
    setBusy(`delete-support-${item.id}`);
    setMessage("");
    try {
      await api.adminDeleteSupportMessage(item.id);
      setMessage("Обращение удалено.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось удалить обращение");
    } finally {
      setBusy("");
    }
  }

  if (error) {
    return (
      <AppShell eyebrow="Администрирование" title="Администратор">
        <div className="panel-card">
          <EmptyState title="Нет доступа" text={error} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell
      actions={<button className="ghost-button" type="button" onClick={refreshAdmin}>Обновить</button>}
      eyebrow="Администрирование"
      title="Администратор"
    >
      {message ? <div className={message.includes("Не удалось") ? "form-message error admin-message" : "form-message admin-message"}>{message}</div> : null}

      <section className="admin-overview-grid" aria-label="Сводка админ-панели">
        <button className="admin-overview-card" type="button" onClick={() => setActiveSection("support")}>
          <span>Открытые обращения</span>
          <strong>{pendingSupportCount}</strong>
          <small>{supportMessages.length} всего</small>
        </button>
        <button className="admin-overview-card" type="button" onClick={() => setActiveSection("users")}>
          <span>Пользователи</span>
          <strong>{users.length}</strong>
          <small>{users.filter((user) => user.role === "admin").length} админов</small>
        </button>
        <button className="admin-overview-card" type="button" onClick={() => setActiveSection("plans")}>
          <span>Публичные тарифы</span>
          <strong>{publicPlanCount}</strong>
          <small>{plans.length} в каталоге</small>
        </button>
        <button className="admin-overview-card" type="button" onClick={() => setActiveSection("billing")}>
          <span>Счета к проверке</span>
          <strong>{pendingInvoiceCount}</strong>
          <small>{invoices.length} последних</small>
        </button>
      </section>

      <nav className="admin-section-tabs" aria-label="Разделы админ-панели">
        {sections.map((section) => (
          <button
            aria-current={activeSection === section.key ? "page" : undefined}
            className={activeSection === section.key ? "admin-section-tab active" : "admin-section-tab"}
            key={section.key}
            type="button"
            onClick={() => setActiveSection(section.key)}
          >
            <span>{section.label}</span>
            <small>{section.hint}</small>
            <strong>{section.count}</strong>
          </button>
        ))}
      </nav>

      <div className="admin-section-panel" key={activeSection}>
        {activeSection === "support" ? (
          <section className="panel-card admin-support-panel">
            <div className="section-heading horizontal">
              <div><span className="eyebrow">Поддержка</span><h2>Обращения с сайта</h2></div>
              <button className="ghost-button" type="button" onClick={refreshAdmin}>Обновить</button>
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
                        <button className="ghost-button danger-button small-button" disabled={busy === `delete-support-${item.id}`} type="button" onClick={() => deleteSupportMessage(item).catch(() => undefined)}>
                          Удалить
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="Обращений пока нет" text="Сообщения из формы поддержки появятся здесь." />
            )}
          </section>
        ) : null}

        {activeSection === "users" ? (
          <section className="panel-card admin-users-panel">
            <div className="section-heading horizontal">
              <div><span className="eyebrow">Пользователи</span><h2>Пользователи и доступ</h2></div>
              <button className="ghost-button" type="button" onClick={refreshAdmin}>Обновить</button>
            </div>
            <div className="admin-user-list">
              {users.map((user) => {
                const usage = usageByUser[user.id];
                return (
                  <article className="admin-user-card" key={user.id}>
                    <div className="admin-user-main">
                      <strong>{user.full_name || user.email}</strong>
                      <span>{user.email}</span>
                      <small>{truncateMiddle(user.id)}</small>
                    </div>
                    <div className="admin-user-limit">
                      <span>Остаток записей</span>
                      <strong>{formatRemainingRecords(usage)}</strong>
                      <small>
                        {usage
                          ? `${formatLimitNumber(usage.records_used)} / ${formatLimitNumber(usage.subscription.plan.max_records_per_month)} использовано`
                          : "Загружаем лимит"}
                      </small>
                      <div className="admin-user-limit-bar" aria-hidden="true">
                        <i style={{ width: `${recordsLimitPercent(usage)}%` }} />
                      </div>
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
                      <button className="ghost-button danger-button" disabled={busy === `delete-user-${user.id}`} type="button" onClick={() => deleteUser(user).catch(() => undefined)}>
                        Удалить
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ) : null}

        {activeSection === "plans" ? (
          <section className="admin-grid">
            <div className="panel-card plan-builder-card">
              <div className="section-heading">
                <span className="eyebrow">Тарифы</span>
                <h2>{editingPlanId ? "Редактировать тариф" : "Создать тариф"}</h2>
              </div>
              <form className="admin-form" onSubmit={savePlan}>
                <div className="form-grid two equal">
                  <label className="field-block compact"><span>Код</span><input disabled={Boolean(editingPlanId)} value={planForm.code} onChange={(event) => setPlanField("code", event.target.value)} required /></label>
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
                <div className="button-row admin-form-actions">
                  <button className="primary-button wide" disabled={busy === "create-plan" || busy === `save-plan-${editingPlanId}`} type="submit">
                    {editingPlanId ? "Сохранить" : "Создать тариф"}
                  </button>
                  {editingPlanId ? (
                    <button className="ghost-button" type="button" onClick={() => { setEditingPlanId(null); setPlanForm(initialPlanForm); }}>
                      Отмена
                    </button>
                  ) : null}
                </div>
              </form>
            </div>

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
                      <button className="ghost-button" disabled={busy === `delete-plan-${plan.id}`} type="button" onClick={() => editPlan(plan)}>Редактировать</button>
                      <button className="ghost-button danger-button" disabled={busy === `delete-plan-${plan.id}`} type="button" onClick={() => deletePlan(plan).catch(() => undefined)}>Удалить</button>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {activeSection === "billing" ? (
          <section className="admin-payment-layout">
            <form className="panel-card admin-qr-settings-card" onSubmit={savePaymentQr}>
              <div className="section-heading horizontal">
                <div><span className="eyebrow">QR оплата</span><h2>QR-код для покупателей</h2></div>
                <StatusPill status={paymentQr?.is_active ? "active" : "pending"} />
              </div>
              <div className="admin-qr-settings-grid">
                <label className="qr-upload-box">
                  <input accept="image/*" type="file" onChange={handlePaymentQrFile} />
                  {paymentQrForm.image_data ? <img alt="Текущий QR-код оплаты" src={paymentQrForm.image_data} /> : <span>Загрузить QR</span>}
                </label>
                <div className="admin-qr-fields">
                  <label className="field-block compact"><span>Название</span><input value={paymentQrForm.title} onChange={(event) => setPaymentQrField("title", event.target.value)} /></label>
                  <label className="field-block compact"><span>Текст для клиента</span><textarea rows={3} value={paymentQrForm.note} onChange={(event) => setPaymentQrField("note", event.target.value)} /></label>
                  <label className="toggle-line"><input checked={paymentQrForm.is_active} type="checkbox" onChange={(event) => setPaymentQrField("is_active", event.target.checked)} /> QR активен</label>
                  <button className="primary-button wide" disabled={busy === "payment-qr" || !paymentQrForm.image_data} type="submit">{busy === "payment-qr" ? "Сохраняем..." : "Сохранить QR"}</button>
                </div>
              </div>
            </form>

            <section className="panel-card">
              <div className="section-heading horizontal">
                <div><span className="eyebrow">Модерация</span><h2>Заявки на оплату</h2></div>
                <button className="ghost-button" type="button" onClick={refreshAdmin}>Обновить</button>
              </div>
              <div className="data-table invoices-table admin-invoices-table payment-review-table">
                <div className="table-row table-head"><span>Клиент</span><span>Тариф</span><span>Сумма</span><span>ID чека</span><span>Статус</span><span>Действие</span></div>
                {invoices.map((invoice) => (
                  <div className="table-row" key={invoice.id}>
                    <span>{usersById.get(invoice.user_id)?.email || truncateMiddle(invoice.user_id)}</span>
                    <span>{invoice.plan.name}</span>
                    <span>{formatMoney(invoice.amount_kzt, invoice.currency)}</span>
                    <span className="receipt-code">{receiptIdForInvoice(invoice)}</span>
                    <span><StatusPill status={invoice.status} /></span>
                    <span>
                      <button className="ghost-button small-button" disabled={invoice.status === "paid" || busy === `invoice-${invoice.id}`} type="button" onClick={() => markInvoicePaid(invoice).catch(() => undefined)}>
                        Подтвердить
                      </button>
                    </span>
                  </div>
                ))}
              </div>
              {!invoices.length ? <EmptyState title="Заявок пока нет" text="Новые заявки появятся здесь после отправки ID чека пользователем." /> : null}
            </section>
          </section>
        ) : null}

        {activeSection === "audit" ? (
          <section className="panel-card">
            <div className="section-heading horizontal">
              <div><span className="eyebrow">Журнал</span><h2>Журнал действий</h2></div>
              <button className="ghost-button" type="button" onClick={refreshAdmin}>Обновить</button>
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
            {!audit.length ? <EmptyState title="Журнал пуст" text="События появятся здесь после действий пользователей и администраторов." /> : null}
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
