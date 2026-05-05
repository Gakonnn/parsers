"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import type { PaymentProviderInfo, UsageSummary, User } from "@/lib/types";

export default function SettingsPage() {
  const [user, setUser] = useState<User | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [provider, setProvider] = useState<PaymentProviderInfo | null>(null);
  const [fullName, setFullName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"profile" | "password" | "load" | "">("");

  const profileName = useMemo(() => fullName.trim(), [fullName]);

  async function load() {
    setBusy("load");
    setError("");
    const [me, usageResponse, providerResponse] = await Promise.all([
      api.me(),
      api.usage().catch(() => null),
      api.paymentProvider().catch(() => null),
    ]);
    setUser(me);
    setUsage(usageResponse);
    setProvider(providerResponse);
    setFullName(me.full_name || "");
    setBusy("");
  }

  useEffect(() => {
    load().catch((err) => {
      setBusy("");
      setError(err instanceof Error ? err.message : "Не удалось загрузить настройки");
    });
  }, []);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("profile");
    setProfileMessage("");
    setError("");
    try {
      const updated = await api.updateMe({ full_name: profileName || null });
      setUser(updated);
      setFullName(updated.full_name || "");
      setProfileMessage("Профиль сохранен.");
      window.dispatchEvent(new Event("parserdesk:user-updated"));
    } catch (err) {
      setProfileMessage(err instanceof Error ? err.message : "Не удалось сохранить профиль");
    } finally {
      setBusy("");
    }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordMessage("");
    setError("");
    if (newPassword !== confirmPassword) {
      setPasswordMessage("Пароли не совпадают.");
      return;
    }
    setBusy("password");
    try {
      await api.changePassword({ current_password: currentPassword, new_password: newPassword });
      setPasswordMessage("Пароль изменен.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPasswordMessage(err instanceof Error ? err.message : "Не удалось изменить пароль");
    } finally {
      setBusy("");
    }
  }

  const currentPlan = usage?.subscription.plan;

  return (
    <AppShell eyebrow="Account" title="Кабинет и настройки">
      {error ? (
        <div className="panel-card">
          <EmptyState title="Не удалось загрузить кабинет" text={error} />
        </div>
      ) : null}

      <section className="settings-hero">
        <div>
          <span className="eyebrow">Profile</span>
          <h2>{user?.full_name || user?.email || "Профиль пользователя"}</h2>
          <p>Управляйте учетной записью, паролем и платежной интеграцией в одном месте.</p>
        </div>
        <div className="settings-hero-stats">
          <StatusPill status={usage?.subscription.status || "active"} />
          <div>
            <span>Тариф</span>
            <strong>{currentPlan?.name || "Free"}</strong>
          </div>
          <div>
            <span>Запуски / записи</span>
            <strong>{usage?.jobs_used ?? 0} / {usage?.records_used ?? 0}</strong>
          </div>
        </div>
      </section>

      <section className="settings-grid">
        <div className="panel-card settings-card">
          <div className="section-heading">
            <span className="eyebrow">Account</span>
            <h2>Профиль</h2>
          </div>
          <form className="settings-form" onSubmit={saveProfile}>
            <label className="field-block compact">
              <span>Имя и фамилия</span>
              <input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Например, Gakon N." />
            </label>
            <div className="info-grid">
              <div>
                <span>Email</span>
                <strong>{user?.email || "—"}</strong>
              </div>
              <div>
                <span>Роль</span>
                <strong>{user?.role === "admin" ? "Администратор" : "Пользователь"}</strong>
              </div>
              <div>
                <span>Создан</span>
                <strong>{formatDate(user?.created_at)}</strong>
              </div>
              <div>
                <span>Обновлен</span>
                <strong>{formatDate(user?.updated_at || user?.created_at)}</strong>
              </div>
            </div>
            {profileMessage ? <p className={profileMessage.includes("Не удалось") ? "form-message error" : "form-message"}>{profileMessage}</p> : null}
            <button className="primary-button wide" disabled={busy === "profile"} type="submit">Сохранить профиль</button>
          </form>
        </div>

        <div className="panel-card settings-card">
          <div className="section-heading">
            <span className="eyebrow">Security</span>
            <h2>Смена пароля</h2>
          </div>
          <form className="settings-form" onSubmit={savePassword}>
            <label className="field-block compact">
              <span>Текущий пароль</span>
              <input value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} type="password" required />
            </label>
            <label className="field-block compact">
              <span>Новый пароль</span>
              <input value={newPassword} onChange={(event) => setNewPassword(event.target.value)} type="password" required />
            </label>
            <label className="field-block compact">
              <span>Подтверждение</span>
              <input value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} type="password" required />
            </label>
            {passwordMessage ? <p className={passwordMessage.includes("Не удалось") ? "form-message error" : "form-message"}>{passwordMessage}</p> : null}
            <button className="primary-button wide" disabled={busy === "password"} type="submit">Обновить пароль</button>
          </form>
        </div>

        <div className="panel-card settings-card settings-card-wide">
          <div className="section-heading horizontal">
            <div>
              <span className="eyebrow">Billing</span>
              <h2>Платежная интеграция</h2>
            </div>
            <StatusPill status={provider?.checkout_mode || "mock"} />
          </div>
          {provider ? (
            <div className="provider-grid">
              <div>
                <span>Провайдер</span>
                <strong>{provider.provider_name}</strong>
              </div>
              <div>
                <span>Режим оплаты</span>
                <strong>{provider.checkout_mode}</strong>
              </div>
              <div>
                <span>Webhook</span>
                <strong>{provider.webhook_secret_configured ? "Настроен" : "Не настроен"}</strong>
              </div>
              <div>
                <span>Success URL</span>
                <strong>{provider.success_url || "—"}</strong>
              </div>
              <div>
                <span>Cancel URL</span>
                <strong>{provider.cancel_url || "—"}</strong>
              </div>
              <div>
                <span>Checkout template</span>
                <strong>{provider.checkout_url_template || "—"}</strong>
              </div>
            </div>
          ) : (
            <EmptyState title="Платежный блок" text="Сейчас доступны только базовые настройки. Здесь будет виден статус интеграции с провайдером оплаты." />
          )}
          <div className="settings-footnote">
            <div>
              <span>Текущий лимит</span>
              <strong>{formatMoney(currentPlan?.price_kzt || 0, currentPlan?.currency || "KZT")}</strong>
            </div>
            <div>
              <span>Осталось запусков</span>
              <strong>{usage?.jobs_remaining ?? 0}</strong>
            </div>
            <div>
              <span>Осталось записей</span>
              <strong>{usage?.records_remaining ?? 0}</strong>
            </div>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
