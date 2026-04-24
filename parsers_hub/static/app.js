const state = {
  parsers: {},
  selectedParser: null,
  jobs: [],
  selectedJobId: null,
  db: {
    records: [],
    total: 0,
    page: 1,
    pages: 1,
    filters: {
      source: "",
      run_status: "",
      has_phone: "",
      search: "",
      limit: 100,
      page: 1,
    },
  },
};

const tabsEl = document.getElementById("parser-tabs");
const formFieldsEl = document.getElementById("form-fields");
const formEl = document.getElementById("run-form");
const formMessageEl = document.getElementById("form-message");
const jobsListEl = document.getElementById("jobs-list");
const jobDetailsEl = document.getElementById("job-details");

const dbFilterFormEl = document.getElementById("db-filter-form");
const dbSummaryEl = document.getElementById("db-summary");
const dbResultsBodyEl = document.getElementById("db-results-body");
const dbPrevPageEl = document.getElementById("db-prev-page");
const dbNextPageEl = document.getElementById("db-next-page");
const dbSourceEl = document.getElementById("db-source");
const dbRunStatusEl = document.getElementById("db-run-status");
const dbHasPhoneEl = document.getElementById("db-has-phone");
const dbSearchEl = document.getElementById("db-search");
const dbLimitEl = document.getElementById("db-limit");

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function statusClass(status) {
  return `status-pill status-${status || "queued"}`;
}

function jobStatusLabel(status) {
  const map = {
    queued: "queued",
    running: "running",
    paused: "paused",
    completed: "completed",
    failed: "failed",
    stopped: "stopped",
  };
  return map[status] || status;
}

function renderTabs() {
  tabsEl.innerHTML = "";
  Object.entries(state.parsers).forEach(([key, parser]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `parser-tab ${state.selectedParser === key ? "active" : ""}`;
    button.innerHTML = `<strong>${parser.title}</strong><span>${parser.description}</span>`;
    button.addEventListener("click", () => {
      state.selectedParser = key;
      renderTabs();
      renderForm();
    });
    tabsEl.appendChild(button);
  });
}

function renderForm() {
  const parser = state.parsers[state.selectedParser];
  if (!parser) return;
  formFieldsEl.innerHTML = "";

  parser.fields.forEach((field) => {
    const wrapper = document.createElement("div");
    const fullWidth = field.type === "url" || field.name.includes("password");
    wrapper.className = `field ${fullWidth ? "full" : ""}`;

    if (field.type === "checkbox") {
      wrapper.className = "field checkbox-field";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = field.name;
      input.checked = Boolean(field.default);
      const label = document.createElement("label");
      label.textContent = field.label;
      label.htmlFor = field.name;
      input.id = field.name;
      wrapper.append(input, label);
      formFieldsEl.appendChild(wrapper);
      return;
    }

    const label = document.createElement("label");
    label.textContent = field.label;
    label.htmlFor = field.name;

    let input;
    if (field.type === "select") {
      input = document.createElement("select");
      field.options.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        if (optionValue === field.default) option.selected = true;
        input.appendChild(option);
      });
    } else {
      input = document.createElement("input");
      input.type = field.type === "number" ? "number" : field.type;
      if (field.default !== undefined) {
        input.value = field.default;
      }
    }

    input.name = field.name;
    input.id = field.name;
    if (field.required) input.required = true;
    wrapper.append(label, input);
    formFieldsEl.appendChild(wrapper);
  });
}

function collectFormPayload() {
  const parser = state.parsers[state.selectedParser];
  const payload = {};
  parser.fields.forEach((field) => {
    const input = formEl.elements[field.name];
    if (!input) return;
    payload[field.name] = field.type === "checkbox" ? input.checked : input.value;
  });
  return payload;
}

function renderJobs() {
  if (!state.jobs.length) {
    jobsListEl.innerHTML = `<div class="empty-state">Здесь появятся ваши запуски.</div>`;
    return;
  }

  jobsListEl.innerHTML = "";
  state.jobs.forEach((job) => {
    const card = document.createElement("div");
    card.className = `job-card ${state.selectedJobId === job.job_id ? "active" : ""}`;
    card.innerHTML = `
      <div class="job-card-top">
        <strong>${job.parser_key.toUpperCase()}</strong>
        <span class="${statusClass(job.status)}">${jobStatusLabel(job.status)}</span>
      </div>
      <div class="job-card-bottom">
        <span>${formatDateTime(job.created_at)}</span>
        <span>${basename(job.output_path)}</span>
      </div>
    `;
    card.addEventListener("click", () => {
      state.selectedJobId = job.job_id;
      renderJobs();
      loadJobDetails();
    });
    jobsListEl.appendChild(card);
  });
}

function renderJobDetails(job) {
  if (!job) {
    jobDetailsEl.className = "job-details empty-state";
    jobDetailsEl.textContent = "Выберите задачу справа, чтобы посмотреть детали запуска.";
    return;
  }

  jobDetailsEl.className = "job-details";
  const command = job.command.map((part) => {
    return /\s/.test(part) ? `"${part}"` : part;
  }).join(" ");
  const canPause = job.status === "running";
  const canStart = job.status === "paused";
  const canStop = job.status === "running" || job.status === "paused" || job.status === "queued";
  const canRestart = ["completed", "failed", "stopped"].includes(job.status);
  const snapshots = Array.isArray(job.snapshots) ? job.snapshots : [];

  jobDetailsEl.innerHTML = `
    <div class="detail-card">
      <div class="detail-row">
        <div class="detail-title">${job.parser_key.toUpperCase()} • ${job.job_id}</div>
        <span class="${statusClass(job.status)}">${jobStatusLabel(job.status)}</span>
      </div>
      <div class="detail-meta">
        <div class="detail-item">
          <span>Создано</span>
          <div>${formatDateTime(job.created_at)}</div>
        </div>
        <div class="detail-item">
          <span>Старт</span>
          <div>${formatDateTime(job.started_at)}</div>
        </div>
        <div class="detail-item">
          <span>Завершено</span>
          <div>${formatDateTime(job.finished_at)}</div>
        </div>
        <div class="detail-item">
          <span>Код возврата</span>
          <div>${job.return_code ?? "—"}</div>
        </div>
        <div class="detail-item">
          <span>Рабочая папка</span>
          <code>${job.cwd}</code>
        </div>
        <div class="detail-item">
          <span>Файл результата</span>
          <code>${job.output_path}</code>
        </div>
      </div>
      <div class="detail-actions" style="margin-top:16px;">
        <button class="ghost-button" type="button" id="refresh-job-btn">Обновить</button>
        <button class="ghost-button" type="button" id="save-job-btn">Сохранить текущий результат</button>
        <button class="ghost-button" type="button" id="pause-job-btn" ${canPause ? "" : "disabled"}>Пауза</button>
        <button class="ghost-button" type="button" id="start-job-btn" ${canStart ? "" : "disabled"}>Старт</button>
        <button class="ghost-button" type="button" id="restart-job-btn" ${canRestart ? "" : "disabled"}>Перезапуск</button>
        <button class="danger-button" type="button" id="stop-job-btn" ${canStop ? "" : "disabled"}>Стоп</button>
      </div>
      ${snapshots.length ? `
        <div class="detail-item" style="margin-top:14px;">
          <span>Сохранённые снапшоты</span>
          <div class="snapshot-list">
            ${snapshots.slice().reverse().map((p) => `<code>${p}</code>`).join("")}
          </div>
        </div>` : ""}
    </div>
    <div class="detail-card">
      <div class="detail-title" style="margin-bottom:10px;">Команда запуска</div>
      <pre class="command-box">${escapeHtml(command)}</pre>
    </div>
    <div class="detail-card">
      <div class="detail-title" style="margin-bottom:10px;">Лог</div>
      <pre class="log-box">${escapeHtml(job.log || "Лог пока пуст.")}</pre>
    </div>
  `;

  const refreshBtn = document.getElementById("refresh-job-btn");
  refreshBtn?.addEventListener("click", loadJobDetails);

  const saveBtn = document.getElementById("save-job-btn");
  saveBtn?.addEventListener("click", async () => {
    await runJobAction(job.job_id, "save", "Снапшот сохранён.");
  });

  const pauseBtn = document.getElementById("pause-job-btn");
  pauseBtn?.addEventListener("click", async () => {
    await runJobAction(job.job_id, "pause", "Задача поставлена на паузу.");
  });

  const startBtn = document.getElementById("start-job-btn");
  startBtn?.addEventListener("click", async () => {
    await runJobAction(job.job_id, "start", "Задача продолжена.");
  });

  const restartBtn = document.getElementById("restart-job-btn");
  restartBtn?.addEventListener("click", async () => {
    await runJobAction(job.job_id, "restart", "Задача перезапущена как новый запуск.");
  });

  const stopBtn = document.getElementById("stop-job-btn");
  stopBtn?.addEventListener("click", async () => {
    await runJobAction(job.job_id, "stop", "Задача остановлена.");
  });
}

function basename(path) {
  const parts = String(path).split("/");
  return parts[parts.length - 1] || path;
}

async function runJobAction(jobId, action, successText) {
  try {
    const data = await api(`/api/jobs/${jobId}/${action}`, { method: "POST", body: "{}" });
    if (data.job?.job_id) {
      state.selectedJobId = data.job.job_id;
    }
    formMessageEl.textContent = successText;
    await refreshJobs();
    await loadJobDetails();
  } catch (error) {
    formMessageEl.textContent = error.message;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ru-KZ", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function clip(value, maxLen = 120) {
  const text = String(value || "").trim();
  if (!text) return "—";
  return text.length > maxLen ? `${text.slice(0, maxLen - 1)}…` : text;
}

function renderDbTable() {
  const records = state.db.records;
  if (!records.length) {
    dbResultsBodyEl.innerHTML = `<tr><td colspan="11" class="db-empty">Нет записей по текущим фильтрам.</td></tr>`;
  } else {
    dbResultsBodyEl.innerHTML = records.map((row) => {
      const source = escapeHtml(row.source || "");
      const createdAt = escapeHtml(formatDateTime(row.created_at));
      const runId = escapeHtml(clip(row.run_id, 14));
      const extId = escapeHtml(row.external_id || "");
      const title = escapeHtml(clip(row.title || "", 80));
      const phone = escapeHtml(clip(row.phone || "", 40));
      const price = escapeHtml(clip(row.price || "", 20));
      const location = escapeHtml(clip(row.location || "", 40));
      const status = escapeHtml(row.record_status || row.run_status || "");
      const error = escapeHtml(clip(row.error || "", 80));
      const url = String(row.url || "");
      const safeUrl = escapeHtml(url);
      const urlCell = url ? `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(clip(url, 50))}</a>` : "—";

      return `
        <tr>
          <td>${createdAt || "—"}</td>
          <td>${source || "—"}</td>
          <td title="${escapeHtml(row.run_id || "")}">${runId}</td>
          <td>${extId || "—"}</td>
          <td title="${escapeHtml(row.title || "")}">${title}</td>
          <td>${phone}</td>
          <td>${price}</td>
          <td title="${escapeHtml(row.location || "")}">${location}</td>
          <td>${status || "—"}</td>
          <td title="${escapeHtml(row.error || "")}">${error}</td>
          <td>${urlCell}</td>
        </tr>
      `;
    }).join("");
  }

  dbSummaryEl.textContent = `Всего: ${state.db.total} • Страница ${state.db.page} / ${state.db.pages}`;
  dbPrevPageEl.disabled = state.db.page <= 1;
  dbNextPageEl.disabled = state.db.page >= state.db.pages;
}

function buildDbQuery(filters) {
  const params = new URLSearchParams();
  if (filters.source) params.set("source", filters.source);
  if (filters.run_status) params.set("run_status", filters.run_status);
  if (filters.has_phone) params.set("has_phone", filters.has_phone);
  if (filters.search) params.set("search", filters.search);
  params.set("limit", String(filters.limit || 100));
  params.set("page", String(filters.page || 1));
  return params.toString();
}

function syncDbFormWithState() {
  dbSourceEl.value = state.db.filters.source || "";
  dbRunStatusEl.value = state.db.filters.run_status || "";
  dbHasPhoneEl.value = state.db.filters.has_phone || "";
  dbSearchEl.value = state.db.filters.search || "";
  dbLimitEl.value = String(state.db.filters.limit || 100);
}

async function loadDbRecords() {
  try {
    const query = buildDbQuery(state.db.filters);
    const data = await api(`/api/db/records?${query}`);
    state.db.records = data.records || [];
    state.db.total = data.total || 0;
    state.db.page = data.filters?.page || state.db.filters.page || 1;
    state.db.pages = data.pages || 1;
    renderDbTable();
  } catch (error) {
    dbResultsBodyEl.innerHTML = `<tr><td colspan="11" class="db-empty">Ошибка загрузки БД: ${escapeHtml(error.message)}</td></tr>`;
    dbSummaryEl.textContent = "Ошибка загрузки.";
  }
}

async function loadConfig() {
  const data = await api("/api/config");
  state.parsers = data.parsers;
  state.selectedParser = Object.keys(state.parsers)[0];
  renderTabs();
  renderForm();
}

async function refreshJobs() {
  const data = await api("/api/jobs");
  state.jobs = data.jobs;
  if (!state.selectedJobId && state.jobs.length) {
    state.selectedJobId = state.jobs[0].job_id;
  }
  renderJobs();
}

async function loadJobDetails() {
  if (!state.selectedJobId) {
    renderJobDetails(null);
    return;
  }
  try {
    const job = await api(`/api/jobs/${state.selectedJobId}`);
    renderJobDetails(job);
  } catch (error) {
    renderJobDetails(null);
  }
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  formMessageEl.textContent = "Запускаю задачу...";
  try {
    const payload = collectFormPayload();
    const data = await api("/api/run", {
      method: "POST",
      body: JSON.stringify({
        parser_key: state.selectedParser,
        payload,
      }),
    });
    formMessageEl.textContent = `Задача ${data.job.job_id} запущена.`;
    state.selectedJobId = data.job.job_id;
    await refreshJobs();
    await loadJobDetails();
    await loadDbRecords();
  } catch (error) {
    formMessageEl.textContent = error.message;
  }
});

dbFilterFormEl?.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.db.filters.source = dbSourceEl.value;
  state.db.filters.run_status = dbRunStatusEl.value;
  state.db.filters.has_phone = dbHasPhoneEl.value;
  state.db.filters.search = dbSearchEl.value.trim();
  state.db.filters.limit = Number(dbLimitEl.value || 100);
  state.db.filters.page = 1;
  await loadDbRecords();
});

dbPrevPageEl?.addEventListener("click", async () => {
  if (state.db.filters.page <= 1) return;
  state.db.filters.page -= 1;
  await loadDbRecords();
});

dbNextPageEl?.addEventListener("click", async () => {
  if (state.db.filters.page >= state.db.pages) return;
  state.db.filters.page += 1;
  await loadDbRecords();
});

async function boot() {
  syncDbFormWithState();
  await loadConfig();
  await refreshJobs();
  await loadJobDetails();
  await loadDbRecords();

  window.setInterval(async () => {
    await refreshJobs();
    await loadJobDetails();
  }, 2500);

  window.setInterval(async () => {
    await loadDbRecords();
  }, 6000);
}

boot().catch((error) => {
  formMessageEl.textContent = error.message;
});
