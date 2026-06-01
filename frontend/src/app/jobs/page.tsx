"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { JobLauncher } from "@/components/job-launcher";
import { JobList } from "@/components/job-list";
import { api } from "@/lib/api";
import type { ParserJob } from "@/lib/types";

export default function JobsPage() {
  const [jobs, setJobs] = useState<ParserJob[]>([]);

  async function load() {
    const response = await api.jobs(false);
    setJobs(response.items);
  }

  useEffect(() => {
    load().catch(() => undefined);
    const timer = window.setInterval(() => load().catch(() => undefined), 4000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <AppShell eyebrow="Очередь парсеров" title="Запуск и история парсеров">
      <section className="split-layout wide-left">
        <JobLauncher onCreated={(job) => setJobs((items) => [job, ...items])} />
        <div className="panel-card">
          <div className="section-heading horizontal">
            <div>
              <span className="eyebrow">История</span>
              <h2>Все задачи</h2>
            </div>
            <button className="ghost-button" type="button" onClick={() => load().catch(() => undefined)}>Обновить</button>
          </div>
          <JobList jobs={jobs} />
        </div>
      </section>
    </AppShell>
  );
}
