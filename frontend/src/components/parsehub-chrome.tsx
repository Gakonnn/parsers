"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

type HeaderMode = "public" | "app";
type NavigationItem = {
  href: string;
  label: string;
  aliases?: string[];
};

const publicNavigation: NavigationItem[] = [
  { href: "/", label: "Обзор" },
  { href: "/marketing", label: "Парсеры" },
  { href: "/structure", label: "Результаты" },
  { href: "/finance", label: "Тарифы" },
  { href: "/profile", label: "Кабинет" },
];

const appNavigation: NavigationItem[] = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/marketing", label: "Парсеры", aliases: ["/jobs"] },
  { href: "/structure", label: "Результаты", aliases: ["/results"] },
  { href: "/billing", label: "Тарифы", aliases: ["/orders", "/cart"] },
  { href: "/profile", label: "Кабинет", aliases: ["/settings"] },
];

const footerLinks = [
  { href: "/about", label: "О нас" },
  { href: "/privacy", label: "Политика конфиденциальности" },
  { href: "/offer", label: "Оферта" },
  { href: "/payment", label: "Оплата" },
  { href: "/guide", label: "Инструкция" },
];

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg aria-hidden="true" className="parsehub-social-icon" fill="none" viewBox="0 0 24 24">
      {children}
    </svg>
  );
}

const socials = [
  {
    label: "YouTube",
    icon: (
      <Icon>
        <path d="M21 8.3a3 3 0 0 0-2.1-2.1C17 5.7 12 5.7 12 5.7s-5 0-6.9.5A3 3 0 0 0 3 8.3 31 31 0 0 0 3 15.7a3 3 0 0 0 2.1 2.1c1.9.5 6.9.5 6.9.5s5 0 6.9-.5a3 3 0 0 0 2.1-2.1 31 31 0 0 0 0-7.4Z" stroke="currentColor" strokeWidth="1.8" />
        <path d="m10.4 14.8 4.2-2.8-4.2-2.8v5.6Z" fill="currentColor" />
      </Icon>
    ),
  },
  {
    label: "Instagram",
    icon: (
      <Icon>
        <rect height="16" rx="4.5" stroke="currentColor" strokeWidth="1.8" width="16" x="4" y="4" />
        <path d="M15.5 11.6a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0Z" stroke="currentColor" strokeWidth="1.8" />
        <path d="M16.6 7.4h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="2.4" />
      </Icon>
    ),
  },
  {
    label: "Telegram",
    icon: (
      <Icon>
        <path d="m20.5 4.5-17 6.6c-.9.35-.86 1.64.07 1.92l4.1 1.24 1.6 4.86c.28.86 1.42 1.02 1.93.27l2.3-3.37 4.03 3.05c.72.55 1.78.15 1.94-.74l2.6-12.3c.18-.9-.74-1.67-1.57-1.53Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
        <path d="m8 14.2 8.2-5.4-6.8 7.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      </Icon>
    ),
  },
  {
    label: "WhatsApp",
    icon: (
      <Icon>
        <path d="M7.8 18.7A8 8 0 1 0 5.3 16l-1 3.7 3.5-1Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
        <path d="M9.1 8.7c.2-.4.4-.4.7-.4h.5c.2 0 .4.1.5.4l.7 1.6c.1.3.1.5-.1.7l-.4.5c.7 1.2 1.6 2 2.8 2.7l.6-.5c.2-.2.5-.2.7-.1l1.6.7c.3.1.4.3.4.6v.5c0 .3-.1.6-.4.7-.6.4-1.4.5-2.1.3-2.8-.8-5.1-2.9-6.1-5.7-.2-.6-.1-1.4.2-2Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" />
      </Icon>
    ),
  },
];

export function ParseHubHeader({
  mode = "public",
  notificationsCount = 0,
  onLogout,
}: {
  mode?: HeaderMode;
  notificationsCount?: number;
  onLogout?: () => void;
}) {
  const pathname = usePathname();
  const [isScrolled, setIsScrolled] = useState(false);
  const [isLogoZoomed, setIsLogoZoomed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const navigation = mode === "app" ? appNavigation : publicNavigation;

  useEffect(() => {
    const update = () => setIsScrolled(window.scrollY > 10);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    document.body.classList.toggle("parsehub-mobile-menu-open", isMobileMenuOpen);
    return () => document.body.classList.remove("parsehub-mobile-menu-open");
  }, [isMobileMenuOpen]);

  const closeMobileMenu = () => setIsMobileMenuOpen(false);

  return (
    <>
      <header className={`parsehub-header${isScrolled ? " is-scrolled" : ""}`}>
        <div className="parsehub-header-inner">
          <Link className="parsehub-brand" href={mode === "app" ? "/dashboard" : "/"} aria-label="ParseHub">
            <span
              className="parsehub-logo-wrap"
              onMouseEnter={() => setIsLogoZoomed(true)}
              onMouseLeave={() => setIsLogoZoomed(false)}
              onMouseDown={() => setIsLogoZoomed(true)}
              onMouseUp={() => setIsLogoZoomed(false)}
            >
              <img src="/logo/logo.png" alt="" />
            </span>
            <strong>ParseHub</strong>
          </Link>

          <nav className="parsehub-nav" aria-label={mode === "app" ? "Основная навигация" : "Публичная навигация"}>
            {navigation.map((item) => {
              const active = pathname === item.href || item.aliases?.includes(pathname);
              return (
                <Link className={active ? "active" : ""} href={item.href} key={item.href}>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="parsehub-userbar">
            {mode === "app" ? (
              <>
                <Link className="parsehub-login-link" href="/notifications">
                  Уведомления{notificationsCount ? ` (${notificationsCount})` : ""}
                </Link>
                <button className="parsehub-register-link" type="button" onClick={onLogout}>
                  Выйти
                </button>
              </>
            ) : (
              <>
                <Link className="parsehub-login-link" href="/login">Вход</Link>
                <Link className="parsehub-register-link" href="/register">Регистрация</Link>
              </>
            )}
          </div>

          <button
            aria-controls="parsehub-mobile-menu"
            aria-expanded={isMobileMenuOpen}
            aria-label={isMobileMenuOpen ? "Закрыть меню" : "Открыть меню"}
            className="parsehub-mobile-trigger"
            onClick={() => setIsMobileMenuOpen((value) => !value)}
            type="button"
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </header>

      <div
        aria-hidden={!isMobileMenuOpen}
        className={`parsehub-mobile-overlay${isMobileMenuOpen ? " open" : ""}`}
        onClick={closeMobileMenu}
      />
      <aside
        aria-hidden={!isMobileMenuOpen}
        className={`parsehub-mobile-panel${isMobileMenuOpen ? " open" : ""}`}
        id="parsehub-mobile-menu"
      >
        <div className="parsehub-mobile-panel-head">
          <span>Навигация</span>
          <button aria-label="Закрыть меню" onClick={closeMobileMenu} type="button">×</button>
        </div>
        <nav aria-label="Мобильная навигация">
          {navigation.map((item) => {
            const active = pathname === item.href || item.aliases?.includes(pathname);
            return (
              <Link className={active ? "active" : ""} href={item.href} key={item.href} onClick={closeMobileMenu}>
                <MobileNavIcon label={item.label} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="parsehub-mobile-actions">
          {mode === "app" ? (
            <>
              <Link href="/notifications" onClick={closeMobileMenu}>
                Уведомления{notificationsCount ? ` (${notificationsCount})` : ""}
              </Link>
              <button
                type="button"
                onClick={() => {
                  closeMobileMenu();
                  onLogout?.();
                }}
              >
                Выйти
              </button>
            </>
          ) : (
            <>
              <Link href="/login" onClick={closeMobileMenu}>Вход</Link>
              <Link className="primary" href="/register" onClick={closeMobileMenu}>Регистрация</Link>
            </>
          )}
        </div>
      </aside>

      {isLogoZoomed && (
        <div className="parsehub-logo-preview" aria-hidden="true">
          <img src="/logo/logo.png" alt="" />
        </div>
      )}
    </>
  );
}

function MobileNavIcon({ label }: { label: string }) {
  const normalized = label.toLowerCase();
  if (normalized.includes("обзор")) {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h4A1.5 1.5 0 0 1 11 5.5v4A1.5 1.5 0 0 1 9.5 11h-4A1.5 1.5 0 0 1 4 9.5v-4Zm9 0A1.5 1.5 0 0 1 14.5 4h4A1.5 1.5 0 0 1 20 5.5v4a1.5 1.5 0 0 1-1.5 1.5h-4A1.5 1.5 0 0 1 13 9.5v-4ZM4 14.5A1.5 1.5 0 0 1 5.5 13h4a1.5 1.5 0 0 1 1.5 1.5v4A1.5 1.5 0 0 1 9.5 20h-4A1.5 1.5 0 0 1 4 18.5v-4Zm9 0a1.5 1.5 0 0 1 1.5-1.5h4a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5h-4a1.5 1.5 0 0 1-1.5-1.5v-4Z" />
      </svg>
    );
  }
  if (normalized.includes("парсер")) {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M7 4h10a2 2 0 0 1 2 2v12.4a1.6 1.6 0 0 1-2.42 1.38L12 17.05l-4.58 2.73A1.6 1.6 0 0 1 5 18.4V6a2 2 0 0 1 2-2Zm2 5h6m-6 4h4" />
      </svg>
    );
  }
  if (normalized.includes("результ")) {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M5 19V5h14v14H5Zm4-4 2.4-3 2 2.1L16 10" />
      </svg>
    );
  }
  if (normalized.includes("тариф")) {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M5 7h14v10H5V7Zm2.5 3h3m5 4h.01M9 14h.01" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 8a7 7 0 0 0-14 0" />
    </svg>
  );
}

export function ParseHubFooter() {
  const [form, setForm] = useState({ name: "", email: "", phone: "", question: "" });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const subject = encodeURIComponent("Вопрос в поддержку ParseHub");
    const body = encodeURIComponent(
      [
        `Имя или логин: ${form.name}`,
        `Email: ${form.email}`,
        `Телефон: ${form.phone || "-"}`,
        "",
        form.question,
      ].join("\n"),
    );
    window.location.href = `mailto:support@parsehub.kz?subject=${subject}&body=${body}`;
  }

  const canSubmit = useMemo(() => Boolean(form.name.trim() && form.email.trim() && form.question.trim()), [form]);

  return (
    <footer className="parsehub-footer">
      <div className="parsehub-footer-main">
        <div className="parsehub-footer-column">
          <h3>Документы и информация</h3>
          <nav aria-label="Документы">
            {footerLinks.map((link) => (
              <Link href={link.href} key={link.href}>{link.label}</Link>
            ))}
          </nav>
        </div>

        <div className="parsehub-footer-column parsehub-footer-social">
          <h3>Социальные сети</h3>
          <div className="parsehub-socials">
            {socials.map((social) => (
              <a href="#" aria-label={social.label} key={social.label}>
                {social.icon}
              </a>
            ))}
          </div>
        </div>

        <div className="parsehub-footer-column parsehub-footer-support">
          <h3>Служба поддержки ParseHub</h3>
          <form onSubmit={submit}>
            <input
              onChange={(event) => setForm((value) => ({ ...value, name: event.target.value }))}
              placeholder="Имя или логин"
              required
              value={form.name}
            />
            <input
              onChange={(event) => setForm((value) => ({ ...value, email: event.target.value }))}
              placeholder="example@any-mail.com"
              required
              type="email"
              value={form.email}
            />
            <input
              onChange={(event) => setForm((value) => ({ ...value, phone: event.target.value }))}
              placeholder="+77471234567"
              value={form.phone}
            />
            <textarea
              onChange={(event) => setForm((value) => ({ ...value, question: event.target.value }))}
              placeholder="Опишите ваш вопрос"
              required
              value={form.question}
            />
            <button disabled={!canSubmit} type="submit">
              <Icon>
                <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
              </Icon>
              Отправить
            </button>
          </form>
        </div>
      </div>

      <div className="parsehub-footer-bottom">
        <p>ParseHub Data Solutions</p>
        <span>2026 © Все права защищены ParseHub</span>
      </div>
    </footer>
  );
}
