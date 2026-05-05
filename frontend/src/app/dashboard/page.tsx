"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { JobLauncher } from "@/components/job-launcher";
import { JobList } from "@/components/job-list";
import { MetricCard } from "@/components/metric-card";
import { ProgressRing } from "@/components/progress-ring";
import { api } from "@/lib/api";
import { percent } from "@/lib/format";
import type { ParserJob, UsageSummary } from "@/lib/types";

export default function DashboardPage() {
  const [jobs, setJobs] = useState<ParserJob[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  async function load() {
    const [jobsResponse, usageResponse] = await Promise.all([api.jobs(false), api.usage().catch(() => null)]);
    setJobs(jobsResponse.items);
    setUsage(usageResponse);
  }

  useEffect(() => {
    load().catch(() => undefined);
    const timer = window.setInterval(() => load().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const activeJobs = jobs.filter((job) => ["pending", "running"].includes(job.status)).length;
  const completed = jobs.filter((job) => job.status === "completed").length;
  const recordsPercent = usage ? percent(usage.records_used, usage.subscription.plan.max_records_per_month) : 0;

  return (
    <AppShell eyebrow="Control room" title="Панель управления">
      <section className="dashboard-grid">
        <MetricCard label="Активные задачи" value={activeJobs} note="очередь и выполнение" tone={activeJobs ? "warn" : "neutral"} />
        <MetricCard label="Успешные запуски" value={completed} note="последние задачи" tone="good" />
        <MetricCard label="Тариф" value={usage?.subscription.plan.name || "Free"} note={`${usage?.jobs_remaining ?? 0} запусков осталось`} />
        <div className="usage-card">
          <ProgressRing value={recordsPercent} label="records" />
          <div>
            <span className="eyebrow">Лимит записей</span>
            <strong>{usage?.records_used ?? 0} / {usage?.subscription.plan.max_records_per_month ?? 0}</strong>
            <p>Месячное использование по текущему тарифу.</p>
          </div>
        </div>
      </section>

      <section className="split-layout">
        <JobLauncher onCreated={(job) => setJobs((items) => [job, ...items])} />
        <div className="panel-card">
          <div className="section-heading">
            <span className="eyebrow">Recent activity</span>
            <h2>Последние задачи</h2>
          </div>
          <JobList jobs={jobs.slice(0, 6)} compact />
        </div>
      </section>
    </AppShell>
  );
}
