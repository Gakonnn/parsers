"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { ProgressRing } from "@/components/progress-ring";
import { StatusPill } from "@/components/status-pill";
import { api } from "@/lib/api";
import { formatDate, percent, truncateMiddle } from "@/lib/format";
import type { ParserJobLive } from "@/lib/types";

function paramRows(parameters: Record<string, unknown>): [string, string][] {
  return Object.entries(parameters || {}).map(([key, value]) => [key, typeof value === "object" ? JSON.stringify(value) : String(value ?? "")]);
}

export default function JobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const router = useRouter();
  const jobId = Array.isArray(params.jobId) ? params.jobId[0] : params.jobId;
  const [data, setData] = useState<ParserJobLive | null>(null);
  const [error, setError] = useState("");
  const [busyAction, setBusyAction] = useState<"stop" | "retry" | "">("");

  const load = useCallback(async () => {
    if (!jobId) return;
    try {
      const response = await api.jobLive(jobId);
      setData(response);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить задачу");
    }
  }, [jobId]);

  useEffect(() => {
    load().catch(() => undefined);
    const timer = window.setInterval(() => load().catch(() => undefined), 2500);
    return () => window.clearInterval(timer);
  }, [load]);

  const job = data?.job;
  const runner = data?.runner;
  const liveProgress = runner?.progress?.percent ?? (job ? percent(job.progress_current, job.progress_total) : 0);
  const current = runner?.progress?.current ?? job?.progress_current ?? 0;
  const total = runner?.progress?.total ?? job?.progress_total ?? 0;
  const logText = runner?.log || job?.error_message || "Лог появится после старта runner-процесса.";
  const parameters = useMemo(() => paramRows(job?.parameters || {}), [job?.parameters]);
  const canStop = Boolean(job?.runner_job_id && ["pending", "running"].includes(job.status));

  async function stopJob() {
    if (!job) return;
    setBusyAction("stop");
    try {
      const response = await api.stopJob(job.id);
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось остановить задачу");
    } finally {
      setBusyAction("");
    }
  }

  async function retryJob() {
    if (!job) return;
    setBusyAction("retry");
    try {
      const retry = await api.retryJob(job.id);
      router.push(`/jobs/${retry.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось повторить задачу");
    } finally {
      setBusyAction("");
    }
  }

  return (
    <AppShell
      eyebrow="Job detail"
      title="Детали задачи"
      actions={<Link className="ghost-button" href="/jobs">Назад к задачам</Link>}
    >
      {error ? <div className="form-message error detail-message">{error}</div> : null}
      {!job ? (
        <div className="panel-card"><EmptyState title="Загрузка задачи" text="Получаем состояние задачи и live-лог из parser hub." /></div>
      ) : (
        <div className="job-detail-layout">
          <section className="job-hero-card">
            <div className="job-hero-copy">
              <span className="eyebrow">{job.source}</span>
              <h2>{truncateMiddle(job.id, 10)}</h2>
              <div className="job-meta-line">
                <StatusPill status={job.status} />
                <span>Создана {formatDate(job.created_at)}</span>
                {job.runner_job_id ? <span>Runner {truncateMiddle(job.runner_job_id, 6)}</span> : <span>Runner ожидается</span>}
              </div>
            </div>
            <ProgressRing value={liveProgress} label="job" />
          </section>

          <section className="detail-grid">
            <article className="panel-card job-facts">
              <div className="section-heading horizontal">
                <div><span className="eyebrow">Прогресс</span><h2>Состояние</h2></div>
                <button className="ghost-button" type="button" onClick={() => load().catch(() => undefined)}>Обновить</button>
              </div>
              <dl>
                <div><dt>Обработано</dt><dd>{current} / {total || "?"}</dd></div>
                <div><dt>Runner статус</dt><dd>{runner?.status || "нет live-снимка"}</dd></div>
                <div><dt>Return code</dt><dd>{runner?.return_code ?? "-"}</dd></div>
                <div><dt>Файл результата</dt><dd>{runner?.output_path || job.result_path || "-"}</dd></div>
                <div><dt>Начало</dt><dd>{formatDate(job.started_at)}</dd></div>
                <div><dt>Финиш</dt><dd>{formatDate(job.finished_at)}</dd></div>
              </dl>
              <div className="job-actions-row">
                <button className="ghost-button" disabled={!canStop || busyAction !== ""} type="button" onClick={stopJob}>
                  {busyAction === "stop" ? "Останавливаю..." : "Остановить"}
                </button>
                <button className="primary-button" disabled={busyAction !== ""} type="button" onClick={retryJob}>
                  {busyAction === "retry" ? "Создаю..." : "Повторить запуск"}
                </button>
              </div>
            </article>

            <article className="panel-card job-params">
              <div className="section-heading"><span className="eyebrow">Входные данные</span><h2>Параметры</h2></div>
              <div className="param-list">
                {parameters.map(([key, value]) => (
                  <div key={key}><span>{key}</span><strong>{value || "-"}</strong></div>
                ))}
              </div>
            </article>
          </section>

          <section className="panel-card log-panel">
            <div className="section-heading horizontal">
              <div><span className="eyebrow">Live-лог</span><h2>Лог выполнения</h2></div>
              {runner?.stop_requested ? <span className="soft-badge">stop requested</span> : null}
            </div>
            <pre>{logText}</pre>
          </section>
        </div>
      )}
    </AppShell>
  );
}
