"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { ResultTable } from "@/components/result-table";
import { api, downloadResults } from "@/lib/api";
import type { ParserResult } from "@/lib/types";

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

export default function ResultsPage() {
  const [source, setSource] = useState<(typeof sources)[number]>("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [allUsers, setAllUsers] = useState(false);
  const [rows, setRows] = useState<ParserResult[]>([]);
  const [fields, setFields] = useState<string[]>([]);
  const [adservletExport, setAdservletExport] = useState(false);
  const [busy, setBusy] = useState(false);
  const visibleFields = adservletExport ? adservletFieldsFor(source) : fields;

  async function load(nextSource = source, nextAllUsers = allUsers) {
    const [results, fieldsResponse] = await Promise.all([
      api.results(nextSource, nextAllUsers),
      api.resultFields(nextSource, nextAllUsers).catch(() => ({ fields: [] })),
    ]);
    setRows(results.items);
    setFields(fieldsResponse.fields.slice(0, 18));
  }

  useEffect(() => {
    async function boot() {
      const me = await api.me();
      const admin = me.role === "admin";
      setIsAdmin(admin);
      setAllUsers(admin);
      await load(source, admin);
    }
    boot().catch(() => load().catch(() => undefined));
  }, []);

  async function exportData(format: "csv" | "xlsx" | "json") {
    setBusy(true);
    try {
      await downloadResults(format, source, allUsers, adservletExport && format === "xlsx");
    } finally {
      setBusy(false);
    }
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
            <select
              value={source}
              onChange={(event) => {
                const next = event.target.value as VisibleSource;
                setSource(next);
                load(next, allUsers).catch(() => undefined);
              }}
            >
              {sources.map((item) => <option key={item || "all"} value={item}>{item || "Все источники"}</option>)}
            </select>
          </label>
          {isAdmin ? (
            <label className="field-block">
              <span>Доступ</span>
              <select
                value={allUsers ? "all" : "mine"}
                onChange={(event) => {
                  const nextAllUsers = event.target.value === "all";
                  setAllUsers(nextAllUsers);
                  load(source, nextAllUsers).catch(() => undefined);
                }}
              >
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
            <strong>{rows.length}</strong>
            <span>записей в текущей выборке</span>
          </div>
          <div className="hint-box muted">
            <strong>{visibleFields.length}</strong>
            <span>{adservletExport ? "полей в adservlet-шаблоне" : "полей обнаружено в payload"}</span>
          </div>
        </div>
        <div className="field-cloud">
          {visibleFields.map((field, index) => <span key={`${field}-${index}`}>{field}</span>)}
        </div>
      </section>
      <ResultTable rows={rows} />
    </AppShell>
  );
}
