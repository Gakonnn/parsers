"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { DataLeadHubFooter, DataLeadHubHeader } from "@/components/parsehub-chrome";
import { api, getToken, setToken } from "@/lib/api";

export function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const isRegister = mode === "register";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"error" | "info">("error");
  const [verificationEmail, setVerificationEmail] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [codeExpiresIn, setCodeExpiresIn] = useState<number | null>(null);
  const awaitingVerification = Boolean(verificationEmail);

  useEffect(() => {
    if (getToken()) router.replace("/jobs");
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setMessageType("error");
    if (isRegister && password !== confirmPassword) {
      setMessage("Пароли не совпадают.");
      return;
    }
    if (isRegister && !agreed) {
      setMessage("Необходимо согласие с условиями использования.");
      return;
    }
    setBusy(true);
    try {
      if (isRegister) {
        const response = await api.register(email, password, "");
        setVerificationEmail(response.email);
        setCodeExpiresIn(response.expires_in_minutes);
        setVerificationCode("");
        setMessageType("info");
        setMessage(`Код подтверждения отправлен на ${response.email}.`);
      } else {
        const response = await api.login(email, password);
        setToken(response.access_token);
        router.replace("/jobs");
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Не удалось выполнить запрос.";
      if (!isRegister && errorMessage.includes("Email не подтвержден")) {
        setVerificationEmail(email.trim().toLowerCase());
        setVerificationCode("");
        setCodeExpiresIn(15);
        setMessageType("info");
        setMessage("Email не подтвержден. Мы отправили новый код на почту.");
      } else {
        setMessage(errorMessage);
      }
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setMessageType("error");
    setBusy(true);
    try {
      const response = await api.verifyEmail(verificationEmail, verificationCode);
      setToken(response.access_token);
      router.replace("/jobs");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось подтвердить email.");
    } finally {
      setBusy(false);
    }
  }

  async function resendCode() {
    setMessage("");
    setMessageType("error");
    setBusy(true);
    try {
      const response = await api.resendVerification(verificationEmail);
      setCodeExpiresIn(response.expires_in_minutes);
      setMessageType("info");
      setMessage(`Новый код отправлен на ${verificationEmail}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось отправить код повторно.");
    } finally {
      setBusy(false);
    }
  }

  function resetVerification() {
    setVerificationEmail("");
    setVerificationCode("");
    setCodeExpiresIn(null);
    setMessage("");
    setMessageType("error");
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
            <h1>{awaitingVerification ? "Подтверждение email" : isRegister ? "Регистрация" : "Вход"}</h1>
            <p>
              {awaitingVerification
                ? `Код отправлен на ${verificationEmail}`
                : isRegister
                  ? "Присоединяйтесь к DataLeadHub"
                  : "DataLeadHub Data Studio"}
            </p>
          </div>
          {awaitingVerification ? (
            <form onSubmit={verifyCode} className="parsehub-auth-form">
              <label className="field-block">
                <span>Код из письма</span>
                <input
                  value={verificationCode}
                  onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  required
                  minLength={6}
                  maxLength={6}
                />
              </label>
              <button className="parsehub-auth-submit" disabled={busy} type="submit">
                {busy ? "Проверяем..." : "Подтвердить email"}
              </button>
              <div className="auth-code-actions">
                <button className="secondary-button" disabled={busy} type="button" onClick={resendCode}>
                  Отправить ещё раз
                </button>
                <button className="secondary-button" disabled={busy} type="button" onClick={resetVerification}>
                  Изменить email
                </button>
              </div>
              {codeExpiresIn ? <p className="auth-code-note">Код действует {codeExpiresIn} минут.</p> : null}
              {message ? <p className={messageType === "error" ? "form-message error" : "form-message"}>{message}</p> : null}
            </form>
          ) : (
            <form onSubmit={submit} className="parsehub-auth-form">
              <label className="field-block">
                <span>Email</span>
                <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" placeholder="example@mail.com" required />
              </label>
              <label className="field-block">
                <span>Пароль</span>
                <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="••••••••" required minLength={8} />
              </label>
              {isRegister ? (
                <>
                  <label className="field-block">
                    <span>Подтверждение</span>
                    <input
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      type="password"
                      placeholder="••••••••"
                      required
                      minLength={8}
                    />
                  </label>
                  <label className="parsehub-agreement">
                    <input checked={agreed} onChange={(event) => setAgreed(event.target.checked)} type="checkbox" />
                    <span>
                      Я прочитал и согласен с <Link href="/offer">договором оферты</Link> и <Link href="/privacy">политикой конфиденциальности</Link>
                    </span>
                  </label>
                </>
              ) : null}
              <button className="parsehub-auth-submit" disabled={busy} type="submit">
                {busy ? "Проверяем..." : isRegister ? "Создать аккаунт" : "Войти"}
              </button>
              {message ? <p className={messageType === "error" ? "form-message error" : "form-message"}>{message}</p> : null}
            </form>
          )}
          <div className="parsehub-auth-footer">
            {isRegister ? (
              <p>Уже есть аккаунт? <Link href="/login">Войти</Link></p>
            ) : (
              <p>Забыли аккаунт? <Link href="/recovery">Восстановление</Link></p>
            )}
          </div>
        </section>
      </main>

      <DataLeadHubFooter />
    </div>
  );
}
