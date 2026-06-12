"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ParseHubFooter, ParseHubHeader } from "@/components/parsehub-chrome";
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

  useEffect(() => {
    if (getToken()) router.replace("/dashboard");
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
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
      const response = isRegister ? await api.register(email, password, "") : await api.login(email, password);
      setToken(response.access_token);
      router.replace("/dashboard");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось выполнить запрос.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="parsehub-shell parsehub-public-shell">
      <ParseHubHeader mode="public" />

      <main className="parsehub-auth-main">
        <section className="parsehub-auth-card">
          <div className="parsehub-auth-logo">
            <img src="/logo/logo.png" alt="" />
          </div>
          <div className="parsehub-auth-copy">
            <h1>{isRegister ? "Регистрация" : "Вход"}</h1>
            <p>{isRegister ? "Присоединяйтесь к ParseHub" : "ParseHub Data Studio"}</p>
          </div>
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
            {message ? <p className="form-message error">{message}</p> : null}
          </form>
          <div className="parsehub-auth-footer">
            {isRegister ? (
              <p>Уже есть аккаунт? <Link href="/login">Войти</Link></p>
            ) : (
              <p>Забыли аккаунт? <Link href="/recovery">Восстановление</Link></p>
            )}
          </div>
        </section>
      </main>

      <ParseHubFooter />
    </div>
  );
}
