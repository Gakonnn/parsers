import Link from "next/link";
import type { ReactNode } from "react";

const publicLinks = [
  { href: "/about", label: "О нас" },
  { href: "/marketing", label: "Парсеры" },
  { href: "/structure", label: "Результаты" },
  { href: "/guide", label: "Инструкция" },
  { href: "/finance", label: "Тарифы" },
  { href: "/payment", label: "Оплата" },
  { href: "/privacy", label: "Политика" },
  { href: "/offer", label: "Оферта" },
];

export function PublicPage({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <main className="public-page">
      <nav className="public-nav" aria-label="Публичная навигация">
        <Link className="public-brand" href="/">
          <span>P</span>
          ParseHub
        </Link>
        <div>
          {publicLinks.map((link) => (
            <Link key={link.href} href={link.href}>
              {link.label}
            </Link>
          ))}
        </div>
        <Link className="public-login-link" href="/">
          Войти
        </Link>
      </nav>

      <section className="public-hero">
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </section>

      {children}

      <footer className="public-footer">
        <div>
          <strong>ParseHub Data Solutions</strong>
          <span>2026 © Все права защищены</span>
        </div>
        <nav aria-label="Документы">
          <Link href="/privacy">Политика</Link>
          <Link href="/offer">Оферта</Link>
          <Link href="/payment">Оплата</Link>
        </nav>
      </footer>
    </main>
  );
}

export function PublicCard({ title, text, marker }: { title: string; text: string; marker?: string }) {
  return (
    <article className="public-card">
      {marker ? <span className="public-card-marker">{marker}</span> : null}
      <h2>{title}</h2>
      <p>{text}</p>
    </article>
  );
}

export function PublicSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="public-section">
      <h2>{title}</h2>
      <div className="public-section-content">{children}</div>
    </section>
  );
}
