"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { ResultTable } from "@/components/result-table";
import { api, downloadResults } from "@/lib/api";
import { formatDate, truncateMiddle } from "@/lib/format";
import type { ParserJob, ParserResult } from "@/lib/types";

const sources = ["", "2gis", "olx", "krisha"] as const;
type VisibleSource = (typeof sources)[number];

const adservletBusinessFields = [
  "Phone",
  "phone_2",
  "phone_3",
  "whatsapp_1",
  "telegram_1",
  "Title / Name",
  "description",
  "rubrics (интересы)",
  "country",
  "Location",
  "district",
  "address",
  "email_1",
  "email_2",
  "email_3",
  "facebook_1",
  "instagram_1",
  "instagram_2",
  "instagram_3",
  "type",
];

const adservletOlxFields = [
  "Phone",
  "phone_2",
  "phone_3",
  "whatsapp_1",
  "telegram_1",
  "seller_name",
  "country",
  "Location",
  "Location",
  "category (интересы)",
  "title",
  "description",
  "пол",
  "возраст",
  "email_1",
  "email_2",
  "email_3",
  "facebook_1",
  "instagram_1",
  "instagram_2",
  "instagram_3",
];

function adservletFieldsFor(source: VisibleSource): string[] {
  if (source === "olx") return adservletOlxFields;
  if (source === "2gis" || source === "krisha") return adservletBusinessFields;
  return [...adservletBusinessFields, ...adservletOlxFields];
}

function jobProgress(job: ParserJob): string {
  const total = Number(job.progress_total || 0);
  const current = Number(job.progress_current || 0);
  if (!total) return "без лимита";
  return `${current}/${total}`;
}

function jobLabel(job: ParserJob): string {
  const status = String(job.status || "").toLowerCase();
  const statusText = status === "completed" ? "готово" : status || "статус";
  return `${job.source.toUpperCase()} · ${statusText} · ${jobProgress(job)} · ${formatDate(job.created_at)} · ${truncateMiddle(job.id)}`;
}

export default function ResultsPage() {
  const [source, setSource] = useState<(typeof sources)[number]>("");
  const [selectedJobId, setSelectedJobId] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [allUsers, setAllUsers] = useState(false);
  const [rows, setRows] = useState<ParserResult[]>([]);
  const [total, setTotal] = useState(0);
  const [fields, setFields] = useState<string[]>([]);
  const [jobs, setJobs] = useState<ParserJob[]>([]);
  const [adservletExport, setAdservletExport] = useState(false);
  const [busy, setBusy] = useState(false);
  const visibleFields = adservletExport ? adservletFieldsFor(source) : fields;

  const visibleJobs = useMemo(
    () => jobs.filter((job) => (!source || job.source === source) && (job.db_run_id || job.status === "completed")),
    [jobs, source],
  );
  const selectedJob = useMemo(() => jobs.find((job) => job.id === selectedJobId) || null, [jobs, selectedJobId]);

  async function load(nextSource = source, nextAllUsers = allUsers, nextJobId = selectedJobId) {
    const [results, fieldsResponse] = await Promise.all([
      api.results(nextSource, nextAllUsers, nextJobId),
      api.resultFields(nextSource, nextAllUsers, nextJobId).catch(() => ({ fields: [] })),
    ]);
    setRows(results.items);
    setTotal(results.total);
    setFields(fieldsResponse.fields.slice(0, 18));
  }

  async function loadJobs(nextAllUsers = allUsers) {
    const jobsResponse = await api.jobs(nextAllUsers);
    setJobs(jobsResponse.items);
    return jobsResponse.items;
  }

  useEffect(() => {
    async function boot() {
      const me = await api.me();
      const admin = me.role === "admin";
      setIsAdmin(admin);
      setAllUsers(admin);
      await Promise.all([loadJobs(admin), load(source, admin, "")]);
    }
    boot().catch(() => load().catch(() => undefined));
  }, []);

  async function exportData(format: "csv" | "xlsx" | "json") {
    setBusy(true);
    try {
      await downloadResults(format, source, allUsers, adservletExport && format === "xlsx", selectedJobId);
    } finally {
      setBusy(false);
    }
  }

  function changeSource(next: VisibleSource) {
    setSource(next);
    setSelectedJobId("");
    load(next, allUsers, "").catch(() => undefined);
  }

  function changeJob(nextJobId: string) {
    setSelectedJobId(nextJobId);
    const job = jobs.find((item) => item.id === nextJobId);
    const nextSource = job ? (job.source as VisibleSource) : source;
    if (job && sources.includes(nextSource)) setSource(nextSource);
    load(job && sources.includes(nextSource) ? nextSource : source, allUsers, nextJobId).catch(() => undefined);
  }

  async function changeAccess(nextAllUsers: boolean) {
    setAllUsers(nextAllUsers);
    setSelectedJobId("");
    await Promise.all([loadJobs(nextAllUsers), load(source, nextAllUsers, "")]);
  }

  return (
    <AppShell eyebrow="База данных" title="Результаты и выгрузка">
      <section className="panel-card export-panel">
        <div className="section-heading horizontal">
          <div>
            <span className="eyebrow">Студия выгрузки</span>
            <h2>Фильтр выгрузки</h2>
          </div>
          <div className="button-row">
            <button
              className="ghost-button"
              disabled={busy || adservletExport}
              onClick={() => exportData("csv")}
              title={adservletExport ? "Шаблон adservlet доступен в Excel" : undefined}
              type="button"
            >
              CSV
            </button>
            <button className="ghost-button" disabled={busy} onClick={() => exportData("xlsx")} type="button">Excel</button>
            <button
              className="ghost-button"
              disabled={busy || adservletExport}
              onClick={() => exportData("json")}
              title={adservletExport ? "Шаблон adservlet доступен в Excel" : undefined}
              type="button"
            >
              JSON
            </button>
          </div>
        </div>
        <div className="form-grid three">
          <label className="field-block">
            <span>Источник</span>
            <select value={source} onChange={(event) => changeSource(event.target.value as VisibleSource)}>
              {sources.map((item) => <option key={item || "all"} value={item}>{item || "Все источники"}</option>)}
            </select>
          </label>
          <label className="field-block run-select-field">
            <span>Запуск</span>
            <select value={selectedJobId} onChange={(event) => changeJob(event.target.value)}>
              <option value="">Все запуски{source ? ` ${source}` : ""}</option>
              {visibleJobs.map((job) => <option key={job.id} value={job.id}>{jobLabel(job)}</option>)}
            </select>
          </label>
          {isAdmin ? (
            <label className="field-block">
              <span>Доступ</span>
              <select value={allUsers ? "all" : "mine"} onChange={(event) => changeAccess(event.target.value === "all").catch(() => undefined)}>
                <option value="all">Все пользователи</option>
                <option value="mine">Только мои задачи</option>
              </select>
            </label>
          ) : null}
          <label className="toggle-line export-toggle">
            <input
              checked={adservletExport}
              onChange={(event) => setAdservletExport(event.target.checked)}
              type="checkbox"
            />
            <span>Парсинг для адсервлета</span>
          </label>
          <div className="hint-box">
            <strong>{total}</strong>
            <span>{selectedJob ? "записей в выбранном запуске" : "записей в текущей выборке"}</span>
          </div>
          <div className="hint-box muted">
            <strong>{visibleFields.length}</strong>
            <span>{adservletExport ? "полей в adservlet-шаблоне" : "полей обнаружено в payload"}</span>
          </div>
        </div>
        {selectedJob ? (
          <div className="selected-run-card">
            <div>
              <span>Выбранный запуск</span>
              <strong>{selectedJob.source.toUpperCase()} · {formatDate(selectedJob.created_at)}</strong>
            </div>
            <div>
              <span>Статус</span>
              <strong>{selectedJob.status}</strong>
            </div>
            <div>
              <span>Прогресс</span>
              <strong>{jobProgress(selectedJob)}</strong>
            </div>
            <button className="ghost-button small-button" type="button" onClick={() => changeJob("")}>Сбросить</button>
          </div>
        ) : null}
        <div className="field-cloud">
          {visibleFields.map((field, index) => <span key={`${field}-${index}`}>{field}</span>)}
        </div>
      </section>
      <ResultTable rows={rows} />
    </AppShell>
  );
}
