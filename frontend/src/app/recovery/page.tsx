"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { DataLeadHubFooter, DataLeadHubHeader } from "@/components/parsehub-chrome";
import { api, setToken } from "@/lib/api";

export default function RecoveryPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [codeRequested, setCodeRequested] = useState(false);
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"error" | "info">("error");

  async function requestCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setMessageType("error");
    setBusy(true);
    try {
      const response = await api.requestPasswordReset(email);
      setCodeRequested(true);
      setExpiresIn(response.expires_in_minutes);
      setMessageType("info");
      setMessage(`Если аккаунт существует, код восстановления отправлен на ${response.email}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось отправить код восстановления.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setMessageType("error");
    if (newPassword !== confirmPassword) {
      setMessage("Пароли не совпадают.");
      return;
    }
    setBusy(true);
    try {
      const response = await api.confirmPasswordReset(email, code, newPassword);
      setToken(response.access_token);
      router.replace("/jobs");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось восстановить пароль.");
    } finally {
      setBusy(false);
    }
  }

  async function resendCode() {
    setMessage("");
    setMessageType("error");
    setBusy(true);
    try {
      const response = await api.requestPasswordReset(email);
      setExpiresIn(response.expires_in_minutes);
      setMessageType("info");
      setMessage(`Новый код отправлен на ${response.email}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось отправить код повторно.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="parsehub-shell parsehub-public-shell">
      <DataLeadHubHeader mode="public" />

      <main className="parsehub-auth-main">
        <section className="parsehub-auth-card">
          <div className="parsehub-auth-logo">
            <img src="/logo/logo.png" alt="" />
          </div>
          <div className="parsehub-auth-copy">
            <h1>Восстановление</h1>
            <p>{codeRequested ? `Код отправлен на ${email}` : "Верните доступ через email"}</p>
          </div>

          {codeRequested ? (
            <form onSubmit={confirmReset} className="parsehub-auth-form">
              <label className="field-block">
                <span>Код из письма</span>
                <input
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  required
                  minLength={6}
                  maxLength={6}
                />
              </label>
              <label className="field-block">
                <span>Новый пароль</span>
                <input
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  type="password"
                  placeholder="••••••••"
                  required
                  minLength={8}
                />
              </label>
              <label className="field-block">
                <span>Повторите пароль</span>
                <input
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  type="password"
                  placeholder="••••••••"
                  required
                  minLength={8}
                />
              </label>
              <button className="parsehub-auth-submit" disabled={busy} type="submit">
                {busy ? "Проверяем..." : "Сменить пароль"}
              </button>
              <div className="auth-code-actions">
                <button className="secondary-button" disabled={busy} type="button" onClick={resendCode}>
                  Отправить ещё раз
                </button>
                <button className="secondary-button" disabled={busy} type="button" onClick={() => setCodeRequested(false)}>
                  Другой email
                </button>
              </div>
              {expiresIn ? <p className="auth-code-note">Код действует {expiresIn} минут.</p> : null}
              {message ? <p className={messageType === "error" ? "form-message error" : "form-message"}>{message}</p> : null}
            </form>
          ) : (
            <form onSubmit={requestCode} className="parsehub-auth-form">
              <label className="field-block">
                <span>Email аккаунта</span>
                <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" placeholder="example@mail.com" required />
              </label>
              <button className="parsehub-auth-submit" disabled={busy} type="submit">
                {busy ? "Отправляем..." : "Получить код"}
              </button>
              {message ? <p className={messageType === "error" ? "form-message error" : "form-message"}>{message}</p> : null}
            </form>
          )}

          <div className="parsehub-auth-footer">
            <p>
              Вспомнили пароль? <Link href="/login">Вернуться ко входу</Link>
            </p>
          </div>
        </section>
      </main>

      <DataLeadHubFooter />
    </div>
  );
}
