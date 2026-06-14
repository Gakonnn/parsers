import type { ReactNode } from "react";
import { DataLeadHubFooter, DataLeadHubHeader } from "@/components/parsehub-chrome";

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
    <div className="parsehub-shell parsehub-public-shell">
      <DataLeadHubHeader mode="public" />
      <main className="public-page parsehub-main">
        <section className="public-hero">
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p>{description}</p>
        </section>

        {children}
      </main>
      <DataLeadHubFooter />
    </div>
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
