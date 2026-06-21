"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, formatMoney, formatPerRecordPrice } from "@/lib/format";
import type { Invoice, PaymentQrSetting, SubscriptionPlan, UsageSummary } from "@/lib/types";

function limitLabel(value: number, suffix: string): string {
  return value === -1 ? "Безлимит" : `${new Intl.NumberFormat("ru-KZ").format(value)}${suffix ? ` ${suffix}` : ""}`;
}

function quotaLabel(value?: number | null): string {
  if (value === undefined || value === null) return "-";
  if (value < 0) return "Безлимит";
  return new Intl.NumberFormat("ru-KZ").format(value);
}

type ManualQrMetadata = {
  receipt_id?: string;
  submitted_at?: string;
  status?: string;
  qr_title?: string;
};

function manualQrMeta(invoice: Invoice): ManualQrMetadata {
  const meta = invoice.metadata_json?.manual_qr;
  return meta && typeof meta === "object" && !Array.isArray(meta) ? (meta as ManualQrMetadata) : {};
}

function invoiceProviderLabel(invoice: Invoice): string {
  if (invoice.provider === "manual_qr") return "QR + ID чека";
  return invoice.provider || "-";
}

export default function BillingPage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [paymentQr, setPaymentQr] = useState<PaymentQrSetting | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<SubscriptionPlan | null>(null);
  const [receiptId, setReceiptId] = useState("");
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [isSuccessModalOpen, setIsSuccessModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  async function load() {
    const [usageResponse, plansResponse, invoicesResponse, qrResponse] = await Promise.all([
      api.usage(),
      api.plans(),
      api.invoices(),
      api.paymentQr(),
    ]);
    setUsage(usageResponse);
    setPlans(plansResponse);
    setInvoices(invoicesResponse.items);
    setPaymentQr(qrResponse);
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : "Не удалось загрузить тарифы"));
  }, []);

  const currentPlan = usage?.subscription.plan;

  function openPayment(plan: SubscriptionPlan) {
    setSelectedPlan(plan);
    setReceiptId("");
    setMessage("");
    setIsPaymentModalOpen(true);
  }

  async function submitPaymentRequest() {
    if (!selectedPlan) return;
    const normalizedReceiptId = receiptId.trim();
    if (!normalizedReceiptId) {
      setMessage("Введите ID или номер чека после оплаты.");
      return;
    }
    setIsSubmitting(true);
    setMessage("");
    try {
      await api.createInvoice(selectedPlan.code, normalizedReceiptId);
      setIsPaymentModalOpen(false);
      setIsSuccessModalOpen(true);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось отправить чек на модерацию");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AppShell eyebrow="Оплата" title="Тарифы и оплата">
      <section className="billing-subscription-hero">
        <div className="billing-subscription-copy">
          <span className="eyebrow">Управление подпиской</span>
          <h2>Статус аккаунта</h2>
          <p>Проверяйте остаток записей и управляйте текущим тарифным планом.</p>
        </div>
        <div className="billing-subscription-summary" aria-label="Остаток от тарифа">
          <span className="billing-summary-title">Остаток от тарифа</span>
          <div className="billing-summary-metrics">
            <div>
              <span>План</span>
              <strong className="parsehub-plan-name">{currentPlan?.name || "-"}</strong>
            </div>
            <div>
              <span>Записей</span>
              <strong>{quotaLabel(usage?.records_remaining ?? currentPlan?.max_records_per_month)}</strong>
            </div>
          </div>
          <StatusPill status={usage?.subscription.status || "active"} />
        </div>
      </section>

      <section className="manual-payment-note">
        <div>
          <span className="eyebrow">Единый способ оплаты</span>
          <h2>Оплата по QR с проверкой чека</h2>
          <p>Выберите тариф, отсканируйте QR-код, оплатите и отправьте ID чека. Администратор проверит заявку и активирует тариф.</p>
        </div>
        <span className={paymentQr?.image_data ? "payment-ready-pill" : "payment-ready-pill muted"}>
          {paymentQr?.image_data ? "QR настроен" : "QR ожидает настройки"}
        </span>
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
                <li><span>Записей:</span><strong>{limitLabel(plan.max_records_per_month, "")}</strong></li>
                <li><span>Цена за 1 запись:</span><em>{formatPerRecordPrice(plan.price_kzt, plan.max_records_per_month, plan.currency)}</em></li>
              </ul>
              <button
                className="primary-button wide parsehub-plan-button"
                disabled={usage?.subscription.plan.code === plan.code}
                type="button"
                onClick={() => openPayment(plan)}
              >
                {usage?.subscription.plan.code === plan.code ? "Выбрано" : "Оплатить по QR"}
              </button>
            </div>
          </article>
        ))}
      </section>

      {message ? <p className="form-message">{message}</p> : null}

      <section className="panel-card parsehub-invoices-card">
        <div className="section-heading">
          <span className="eyebrow">Документация</span>
          <h2>История заявок</h2>
        </div>
        <div className="data-table invoices-table">
          <div className="table-row table-head"><span>Тариф</span><span>Сумма</span><span>ID чека</span><span>Статус</span><span>Дата</span></div>
          {invoices.map((invoice) => {
            const meta = manualQrMeta(invoice);
            return (
              <div className="table-row" key={invoice.id}>
                <span>{invoice.plan.name}</span>
                <span>{formatMoney(invoice.amount_kzt, invoice.currency)}</span>
                <span>{meta.receipt_id || invoiceProviderLabel(invoice)}</span>
                <span><StatusPill status={invoice.status} /></span>
                <span>{formatDate(invoice.created_at)}</span>
              </div>
            );
          })}
        </div>
      </section>

      {isPaymentModalOpen && selectedPlan ? (
        <div className="payment-modal-backdrop" role="presentation" onMouseDown={() => setIsPaymentModalOpen(false)}>
          <section
            aria-labelledby="payment-modal-title"
            aria-modal="true"
            className="payment-modal-card"
            role="dialog"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button className="modal-close-button" type="button" aria-label="Закрыть" onClick={() => setIsPaymentModalOpen(false)}>×</button>
            <div className="payment-modal-grid">
              <div className="payment-order-info">
                <span className="eyebrow">Заказ</span>
                <h2 id="payment-modal-title">Оплата тарифа {selectedPlan.name}</h2>
                <dl className="payment-order-list">
                  <div><dt>Тариф</dt><dd>{selectedPlan.name}</dd></div>
                  <div><dt>Цена</dt><dd>{formatMoney(selectedPlan.price_kzt, selectedPlan.currency)}</dd></div>
                  <div><dt>Записей</dt><dd>{limitLabel(selectedPlan.max_records_per_month, "")}</dd></div>
                  <div><dt>Цена записи</dt><dd>{formatPerRecordPrice(selectedPlan.price_kzt, selectedPlan.max_records_per_month, selectedPlan.currency)}</dd></div>
                </dl>
                <p>После оплаты введите ID или номер чека. Заявка попадет администратору на проверку.</p>
              </div>
              <div className="payment-qr-box">
                <span>{paymentQr?.title || "QR для оплаты"}</span>
                {paymentQr?.image_data ? (
                  <img alt="QR код для оплаты тарифа" src={paymentQr.image_data} />
                ) : (
                  <div className="qr-placeholder">QR еще не загружен администратором</div>
                )}
                {paymentQr?.note ? <small>{paymentQr.note}</small> : null}
              </div>
            </div>
            <label className="field-block compact receipt-field">
              <span>ID / номер чека</span>
              <input
                autoFocus
                placeholder="Например: 123456789"
                value={receiptId}
                onChange={(event) => setReceiptId(event.target.value)}
              />
            </label>
            <div className="payment-modal-actions">
              <button className="secondary-button" type="button" onClick={() => setIsPaymentModalOpen(false)}>Отмена</button>
              <button className="primary-button" disabled={isSubmitting || !paymentQr?.image_data} type="button" onClick={() => submitPaymentRequest()}>
                {isSubmitting ? "Отправляем..." : "Отправить на проверку"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {isSuccessModalOpen ? (
        <div className="payment-modal-backdrop" role="presentation" onMouseDown={() => setIsSuccessModalOpen(false)}>
          <section className="payment-success-card" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
            <span className="success-orb">✓</span>
            <h2>Заявка отправлена</h2>
            <p>Оплата принята на модерацию. Администратор проверит ID чека в ближайшее время и активирует тариф после подтверждения.</p>
            <button className="primary-button wide" type="button" onClick={() => setIsSuccessModalOpen(false)}>Понятно</button>
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}
