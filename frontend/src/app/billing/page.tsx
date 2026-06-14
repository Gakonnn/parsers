"use client";

import QRCode from "qrcode";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, formatMoney, formatPerRecordPrice } from "@/lib/format";
import type { Invoice, PaymentProviderInfo, SubscriptionPlan, UsageSummary } from "@/lib/types";

type PaymentMethod = "kaspi_qr" | "manual";

type KaspiQrMetadata = {
  qr_operation_id?: string;
  qr_token?: string;
  expire_date?: string;
  receipt_url?: string;
  status?: string;
  status_kind?: string;
};

function limitLabel(value: number, suffix: string): string {
  return value === -1 ? "Безлимит" : `${value}${suffix ? ` ${suffix}` : ""}`;
}

function quotaLabel(value?: number | null): string {
  if (value === undefined || value === null) return "—";
  if (value < 0) return "Безлимит";
  return new Intl.NumberFormat("ru-KZ").format(value);
}

function kaspiMeta(invoice: Invoice | null): KaspiQrMetadata {
  const meta = invoice?.metadata_json?.kaspi_qr;
  return meta && typeof meta === "object" && !Array.isArray(meta) ? (meta as KaspiQrMetadata) : {};
}

function providerLabel(provider: string): string {
  if (provider === "kaspi_qr") return "Kaspi QR";
  if (provider === "manual") return "Ручная";
  return provider || "—";
}

export default function BillingPage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [provider, setProvider] = useState<PaymentProviderInfo | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("kaspi_qr");
  const [activeInvoice, setActiveInvoice] = useState<Invoice | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [isCheckingPayment, setIsCheckingPayment] = useState(false);
  const [message, setMessage] = useState("");

  async function load() {
    const [usageResponse, plansResponse, invoicesResponse, providerResponse] = await Promise.all([
      api.usage(),
      api.plans(),
      api.invoices(),
      api.paymentProvider(),
    ]);
    setUsage(usageResponse);
    setPlans(plansResponse);
    setInvoices(invoicesResponse.items);
    setProvider(providerResponse);
    setPaymentMethod((current) => (providerResponse.kaspi_qr_enabled ? current : "manual"));
    const pendingKaspiInvoice = invoicesResponse.items.find(
      (invoice) => invoice.provider === "kaspi_qr" && invoice.status === "pending" && (invoice.payment_url || kaspiMeta(invoice).qr_token),
    );
    setActiveInvoice((current) => current ?? pendingKaspiInvoice ?? null);
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : "Не удалось загрузить тарифы"));
  }, []);

  const activeKaspiMeta = useMemo(() => kaspiMeta(activeInvoice), [activeInvoice]);
  const activeQrToken = activeInvoice?.payment_url || activeKaspiMeta.qr_token || "";
  const kaspiEnabled = Boolean(provider?.kaspi_qr_enabled);
  const canUseKaspi = kaspiEnabled && provider !== null;
  const currentPlan = usage?.subscription.plan;

  useEffect(() => {
    let cancelled = false;
    if (!activeQrToken) {
      setQrDataUrl("");
      return;
    }
    QRCode.toDataURL(activeQrToken, {
      margin: 1,
      width: 280,
      color: { dark: "#0f172a", light: "#ffffff" },
      errorCorrectionLevel: "M",
    })
      .then((url) => {
        if (!cancelled) setQrDataUrl(url);
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl("");
      });
    return () => {
      cancelled = true;
    };
  }, [activeQrToken]);

  async function refreshKaspiStatus(invoiceId = activeInvoice?.id) {
    if (!invoiceId) return;
    setIsCheckingPayment(true);
    try {
      const updatedInvoice = await api.syncKaspiInvoice(invoiceId);
      setActiveInvoice(updatedInvoice);
      setInvoices((current) => current.map((invoice) => (invoice.id === updatedInvoice.id ? updatedInvoice : invoice)));
      if (updatedInvoice.status === "paid") {
        setMessage("Оплата Kaspi QR подтверждена. Тариф активирован.");
        await load();
      } else if (updatedInvoice.status === "expired") {
        setMessage("Срок действия Kaspi QR истек. Создайте новый счет.");
      } else if (updatedInvoice.status === "failed") {
        setMessage("Kaspi QR оплата не прошла. Можно создать новый счет или выбрать ручную оплату.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось проверить статус Kaspi QR");
    } finally {
      setIsCheckingPayment(false);
    }
  }

  useEffect(() => {
    if (!activeInvoice || activeInvoice.provider !== "kaspi_qr" || activeInvoice.status !== "pending") return;
    const timer = window.setInterval(() => {
      void refreshKaspiStatus(activeInvoice.id);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [activeInvoice?.id, activeInvoice?.status]);

  async function createInvoice(planCode: string) {
    setMessage("");
    try {
      const selectedProvider: PaymentMethod = paymentMethod === "kaspi_qr" && canUseKaspi ? "kaspi_qr" : "manual";
      const invoice = await api.createInvoice(planCode, selectedProvider);
      if (invoice.provider === "kaspi_qr") setActiveInvoice(invoice);
      setMessage(
        invoice.provider === "kaspi_qr"
          ? "Kaspi QR счет создан. Отсканируйте QR-код или откройте ссылку оплаты."
          : "Счет создан. Администратор сможет подтвердить оплату вручную.",
      );
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось создать счет");
    }
  }

  return (
    <AppShell eyebrow="Оплата" title="Тарифы и оплата">
      <section className="billing-subscription-hero">
        <div className="billing-subscription-copy">
          <span className="eyebrow">Управление подпиской</span>
          <h2>Статус аккаунта</h2>
          <p>Проверяйте остатки лимитов и управляйте своим текущим тарифным планом.</p>
        </div>
        <div className="billing-subscription-summary" aria-label="Остаток от тарифа">
          <span className="billing-summary-title">Остаток от тарифа</span>
          <div className="billing-summary-metrics">
            <div>
              <span>План</span>
              <strong className="parsehub-plan-name">{currentPlan?.name || "—"}</strong>
            </div>
            <div>
              <span>Запусков</span>
              <strong>{quotaLabel(usage?.jobs_remaining ?? currentPlan?.max_jobs_per_month)}</strong>
            </div>
            <div>
              <span>Записей</span>
              <strong>{quotaLabel(usage?.records_remaining ?? currentPlan?.max_records_per_month)}</strong>
            </div>
          </div>
          <StatusPill status={usage?.subscription.status || "active"} />
        </div>
      </section>

      <section className="payment-method-panel">
        <div className="section-heading compact">
          <span className="eyebrow">Способ оплаты</span>
          <h2>Выберите, как оплатить тариф</h2>
        </div>
        <div className="payment-method-grid" role="radiogroup" aria-label="Способ оплаты">
          <button
            className={`payment-option${paymentMethod === "kaspi_qr" ? " selected" : ""}`}
            disabled={!kaspiEnabled}
            type="button"
            role="radio"
            aria-checked={paymentMethod === "kaspi_qr"}
            onClick={() => setPaymentMethod("kaspi_qr")}
          >
            <span>Kaspi QR</span>
            <strong>Оплата через Kaspi Bank</strong>
            <small>{kaspiEnabled ? "QR создаётся сразу после выбора тарифа." : "Нужно настроить Kaspi POS env на сервере."}</small>
          </button>
          <button
            className={`payment-option${paymentMethod === "manual" ? " selected" : ""}`}
            type="button"
            role="radio"
            aria-checked={paymentMethod === "manual"}
            onClick={() => setPaymentMethod("manual")}
          >
            <span>Ручная оплата</span>
            <strong>Подтверждение администратором</strong>
            <small>Оставляем как запасной вариант для счета или тестирования.</small>
          </button>
        </div>
      </section>

      {activeInvoice?.provider === "kaspi_qr" && activeQrToken ? (
        <section className="kaspi-qr-panel">
          <div className="kaspi-qr-copy">
            <span className="eyebrow">Kaspi QR</span>
            <h2>{activeInvoice.plan.name}</h2>
            <p>
              Сумма: <strong>{formatMoney(activeInvoice.amount_kzt, activeInvoice.currency)}</strong>. Статус Kaspi:{" "}
              <strong>{activeKaspiMeta.status || activeInvoice.status}</strong>
            </p>
            {activeKaspiMeta.expire_date ? <p className="muted-text">QR действует до {formatDate(activeKaspiMeta.expire_date)}.</p> : null}
            <div className="kaspi-payment-actions">
              <a className="primary-button" href={activeQrToken} rel="noreferrer" target="_blank">
                Открыть оплату
              </a>
              <button className="secondary-button" disabled={isCheckingPayment} type="button" onClick={() => refreshKaspiStatus()}>
                {isCheckingPayment ? "Проверяем..." : "Проверить оплату"}
              </button>
            </div>
          </div>
          <div className="kaspi-qr-code" aria-label="Kaspi QR код">
            {qrDataUrl ? <img alt="Kaspi QR для оплаты тарифа" src={qrDataUrl} /> : <span>QR</span>}
          </div>
        </section>
      ) : null}

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
                onClick={() => createInvoice(plan.code)}
              >
                {usage?.subscription.plan.code === plan.code
                  ? "Выбрано"
                  : paymentMethod === "kaspi_qr" && kaspiEnabled
                    ? "Оплатить Kaspi QR"
                    : "Создать счет"}
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
          <div className="table-row table-head"><span>Тариф</span><span>Сумма</span><span>Способ</span><span>Статус</span><span>Дата</span></div>
          {invoices.map((invoice) => (
            <div className="table-row" key={invoice.id}>
              <span>{invoice.plan.name}</span>
              <span>{formatMoney(invoice.amount_kzt, invoice.currency)}</span>
              <span>
                {invoice.provider === "kaspi_qr" && (invoice.payment_url || kaspiMeta(invoice).qr_token) ? (
                  <button className="inline-action" type="button" onClick={() => setActiveInvoice(invoice)}>
                    {providerLabel(invoice.provider)}
                  </button>
                ) : (
                  providerLabel(invoice.provider)
                )}
              </span>
              <span><StatusPill status={invoice.status} /></span>
              <span>{formatDate(invoice.created_at)}</span>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
