"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { JobLauncher } from "@/components/job-launcher";
import { JobList } from "@/components/job-list";
import { api } from "@/lib/api";
import type { ParserJob } from "@/lib/types";

export default function DashboardPage() {
  const [jobs, setJobs] = useState<ParserJob[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    const jobsResponse = await api.jobs(false);
    setJobs(jobsResponse.items);
  }

  async function refresh() {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
    const timer = window.setInterval(() => load().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <AppShell eyebrow="Парсеры" title="Рабочий стол">
      <section className="split-layout parsehub-dashboard-layout">
        <JobLauncher onCreated={(job) => setJobs((items) => [job, ...items])} />
        <div className="panel-card parsehub-history-card">
          <div className="section-heading horizontal parsehub-history-heading">
            <div>
              <span className="eyebrow">История</span>
            </div>
            <button className="ghost-button parsehub-refresh-button" disabled={refreshing} onClick={refresh} type="button">
              {refreshing ? "Обновляем" : "Обновить"}
            </button>
          </div>
          <JobList jobs={jobs.slice(0, 6)} />
        </div>
      </section>
    </AppShell>
  );
}
