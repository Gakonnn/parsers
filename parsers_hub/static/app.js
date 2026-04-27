const state = {
  parsers: {},
  selectedParser: null,
  jobs: [],
  selectedJobId: null,
  rubrics2gis: {
    loaded: false,
    loading: false,
    error: "",
    level1: [],
  },
  olxCategories: {
    loaded: false,
    loading: false,
    error: "",
    level1: [],
    manualUrl: false,
  },
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
  exports: {
    fields: [],
    jobs: [],
  },
};
const currentPage = document.body?.dataset?.page || "hub";

const tabsEl = document.getElementById("parser-tabs");
const formFieldsEl = document.getElementById("form-fields");
const formEl = document.getElementById("run-form");
const formMessageEl = document.getElementById("form-message");
const jobsListEl = document.getElementById("jobs-list");
const jobDetailsEl = document.getElementById("job-details");
const jobsSearchEl = document.getElementById("jobs-search");
const statTotalJobsEl = document.getElementById("stat-total-jobs");
const statRunningJobsEl = document.getElementById("stat-running-jobs");
const statDbTotalEl = document.getElementById("stat-db-total");

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
const dbExportFormEl = document.getElementById("db-export-form");
const dbExportFieldsEl = document.getElementById("db-export-fields");
const dbExportFieldsAllEl = document.getElementById("export-fields-all");
const dbExportJobsEl = document.getElementById("db-export-jobs");
const dbExportMessageEl = document.getElementById("db-export-message");
const exportSourceEl = document.getElementById("export-source");
const exportFormatEl = document.getElementById("export-format");
const exportRunStatusEl = document.getElementById("export-run-status");
const exportHasPhoneEl = document.getElementById("export-has-phone");
const exportDateFromEl = document.getElementById("export-date-from");
const exportDateToEl = document.getElementById("export-date-to");
const exportSearchEl = document.getElementById("export-search");
const exportMaxRowsEl = document.getElementById("export-max-rows");
const exportFileNameEl = document.getElementById("export-file-name");
let jobsSearchQuery = "";

const OLX_LOCATIONS = [
  {
    region: "Популярные города",
    cities: [
      { name: "Алматы", slug: "alma-ata" },
      { name: "Астана", slug: "astana" },
      { name: "Шымкент", slug: "shymkent" },
      { name: "Караганда", slug: "karaganda" },
      { name: "Актобе", slug: "aktobe" },
      { name: "Павлодар", slug: "pavlodar" },
      { name: "Тараз", slug: "taraz" },
      { name: "Усть-Каменогорск", slug: "ust-kamenogorsk" },
      { name: "Атырау", slug: "atyrau" },
      { name: "Костанай", slug: "kostanay" },
      { name: "Актау", slug: "aktau" },
      { name: "Семей", slug: "semey" },
      { name: "Кызылорда", slug: "kyzylorda" },
      { name: "Уральск", slug: "uralsk" },
      { name: "Петропавловск", slug: "petropavlovsk" },
      { name: "Кокшетау", slug: "kokshetau" },
      { name: "Туркестан", slug: "turkestan" },
      { name: "Талдыкорган", slug: "taldykorgan" },
      { name: "Каскелен", slug: "kaskelen" },
      { name: "Талгар", slug: "talgar" },
    ],
  },
  {
    region: "Алматинская область",
    cities: [
      { name: "Конаев (Капчагай)", slug: "kapshagay_1485" },
      { name: "Есик", slug: "esik" },
      { name: "Жаркент", slug: "zharkent" },
      { name: "Текели", slug: "tekeli" },
      { name: "Шелек", slug: "shelek" },
      { name: "Боралдай", slug: "boralday" },
      { name: "Отеген батыра", slug: "otegen-batyr" },
    ],
  },
];

const OLX_LOCATION_SLUGS = new Set(OLX_LOCATIONS.flatMap((group) => group.cities.map((city) => city.slug)));

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

function jobProgress(job) {
  const progress = job?.progress && typeof job.progress === "object" ? job.progress : {};
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  return {
    current: Number(progress.current || 0),
    total: Number(progress.total || 0),
    percent,
    label: progress.label || (job?.status === "completed" ? "Готово" : "Ожидание старта"),
    indeterminate: Boolean(progress.indeterminate),
  };
}

function progressHtml(job, variant = "compact") {
  const progress = jobProgress(job);
  const barClass = [
    "job-progress",
    `job-progress-${variant}`,
    progress.indeterminate ? "indeterminate" : "",
    job?.status ? `job-progress-${job.status}` : "",
  ].filter(Boolean).join(" ");
  const width = progress.indeterminate ? 42 : progress.percent;
  return `
    <div class="${barClass}" aria-label="Прогресс ${escapeHtml(progress.label)}">
      <div class="job-progress-track">
        <span class="job-progress-fill" style="width:${width}%"></span>
      </div>
      <div class="job-progress-meta">
        <span>${escapeHtml(progress.label)}</span>
        <strong>${progress.indeterminate ? "live" : `${progress.percent}%`}</strong>
      </div>
    </div>
  `;
}

function renderTabs() {
  if (!tabsEl) return;
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

function setFormMessage(text, type = "info") {
  if (!formMessageEl) return;
  formMessageEl.textContent = text;
  formMessageEl.classList.remove("success", "error");
  if (type === "success") formMessageEl.classList.add("success");
  if (type === "error") formMessageEl.classList.add("error");
}

function setExportMessage(text, type = "info") {
  if (!dbExportMessageEl) return;
  dbExportMessageEl.textContent = text;
  dbExportMessageEl.classList.remove("success", "error");
  if (type === "success") dbExportMessageEl.classList.add("success");
  if (type === "error") dbExportMessageEl.classList.add("error");
}

function renderForm() {
  if (!formFieldsEl || !formEl) return;
  const parser = state.parsers[state.selectedParser];
  if (!parser) return;
  formFieldsEl.innerHTML = "";

  parser.fields.forEach((field) => {
    if (field.type === "olx_category_selector") {
      const wrapper = document.createElement("div");
      wrapper.className = "field full";
      wrapper.innerHTML = `
        <label>${field.label}</label>
        <div id="olx-category-picker" class="rubric-picker">
          <div class="empty-state">Загружаю категории OLX...</div>
        </div>
      `;
      formFieldsEl.appendChild(wrapper);
      renderOlxCategoryPicker();
      return;
    }

    if (field.type === "2gis_rubric_selector") {
      const wrapper = document.createElement("div");
      wrapper.className = "field full";
      wrapper.innerHTML = `
        <label>${field.label}</label>
        <div id="2gis-rubric-picker" class="rubric-picker">
          <div class="empty-state">Загружаю рубрики 2GIS...</div>
        </div>
      `;
      formFieldsEl.appendChild(wrapper);
      render2gisRubricPicker();
      return;
    }

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
    if (state.selectedParser === "olx" && field.name === "category_url") {
      input.readOnly = !state.olxCategories.manualUrl;
    }
    wrapper.append(label, input);
    formFieldsEl.appendChild(wrapper);
  });
}

function collectFormPayload() {
  if (!formEl) return {};
  const parser = state.parsers[state.selectedParser];
  if (!parser) return {};
  const payload = {};
  parser.fields.forEach((field) => {
    const input = formEl.elements[field.name];
    if (!input) return;
    payload[field.name] = field.type === "checkbox" ? input.checked : input.value;
  });
  return payload;
}

async function load2gisRubrics() {
  if (state.rubrics2gis.loaded || state.rubrics2gis.loading) return;
  state.rubrics2gis.loading = true;
  state.rubrics2gis.error = "";
  try {
    const data = await api("/api/2gis/rubrics");
    state.rubrics2gis.loaded = true;
    state.rubrics2gis.level1 = Array.isArray(data.level1) ? data.level1 : [];
  } catch (error) {
    state.rubrics2gis.error = error.message;
  } finally {
    state.rubrics2gis.loading = false;
  }
}

function parse2gisSearchUrl(rawUrl) {
  const text = String(rawUrl || "").trim();
  const fallback = { domain: "kz", city: "astana", rubric: "" };
  const match = text.match(/^https?:\/\/2gis\.([a-z.]+)\/([^/]+)\/search\/(.+)$/i);
  if (!match) return fallback;
  const safeDecode = (value) => {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  };
  const domain = match[1] || fallback.domain;
  const city = safeDecode(match[2] || fallback.city);
  const rubric = safeDecode((match[3] || "").replace(/\+/g, "%20"));
  return {
    domain,
    city,
    rubric,
  };
}

function build2gisSearchUrl(domain, city, rubric) {
  const safeDomain = String(domain || "kz").trim().toLowerCase() || "kz";
  const safeCity = String(city || "astana").trim() || "astana";
  const safeRubric = String(rubric || "").trim();
  if (!safeRubric) return "";
  return `https://2gis.${safeDomain}/${encodeURIComponent(safeCity)}/search/${encodeURIComponent(safeRubric)}`;
}

function fillSelectOptions(selectEl, values, selectedValue = "") {
  selectEl.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    if (value === selectedValue) option.selected = true;
    selectEl.appendChild(option);
  });
}

function fillSelectOptionsWithEmpty(selectEl, values, selectedValue = "", emptyLabel = "Не выбрано") {
  selectEl.innerHTML = "";
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = emptyLabel;
  if (!selectedValue) emptyOption.selected = true;
  selectEl.appendChild(emptyOption);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    if (value === selectedValue) option.selected = true;
    selectEl.appendChild(option);
  });
}

function fillSelectOptionsObjects(selectEl, items, selectedValue = "") {
  selectEl.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    if (item.value === selectedValue) option.selected = true;
    selectEl.appendChild(option);
  });
}

function fillSelectOptionsObjectsWithEmpty(selectEl, items, selectedValue = "", emptyLabel = "Не выбрано") {
  selectEl.innerHTML = "";
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = emptyLabel;
  if (!selectedValue) emptyOption.selected = true;
  selectEl.appendChild(emptyOption);
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    if (item.value === selectedValue) option.selected = true;
    selectEl.appendChild(option);
  });
}

function fillOlxLocationOptions(selectEl, selectedValue = "") {
  selectEl.innerHTML = "";
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = "Все города Казахстана";
  if (!selectedValue) emptyOption.selected = true;
  selectEl.appendChild(emptyOption);

  OLX_LOCATIONS.forEach((group) => {
    const optgroup = document.createElement("optgroup");
    optgroup.label = group.region;
    group.cities.forEach((city) => {
      const option = document.createElement("option");
      option.value = city.slug;
      option.textContent = city.name;
      if (city.slug === selectedValue) option.selected = true;
      optgroup.appendChild(option);
    });
    selectEl.appendChild(optgroup);
  });
}

async function loadOlxCategories() {
  if (state.olxCategories.loaded || state.olxCategories.loading) return;
  state.olxCategories.loading = true;
  state.olxCategories.error = "";
  try {
    const data = await api("/api/olx/categories");
    state.olxCategories.loaded = true;
    state.olxCategories.level1 = Array.isArray(data.level1) ? data.level1 : [];
  } catch (error) {
    state.olxCategories.error = error.message;
  } finally {
    state.olxCategories.loading = false;
  }
}

function parseOlxUrlPath(rawUrl) {
  const text = String(rawUrl || "").trim();
  const fallback = { l1: "", l2: "", l3: "", location: "" };
  const match = text.match(/^https?:\/\/(?:www\.)?olx\.kz\/([^?#]+)$/i);
  if (!match) return fallback;
  const path = match[1].replace(/\/+$/, "");
  const parts = path.split("/").filter(Boolean);
  const location = OLX_LOCATION_SLUGS.has(parts[parts.length - 1]) ? parts.pop() : "";
  return {
    l1: parts[0] || "",
    l2: parts[1] || "",
    l3: parts[2] || "",
    location,
  };
}

function buildOlxCategoryUrl(l1, l2 = "", l3 = "", location = "") {
  const parts = [l1, l2, l3, location].filter(Boolean);
  if (!parts.length) return "";
  return `https://www.olx.kz/${parts.join("/")}/`;
}

function renderOlxCategoryPicker() {
  const picker = document.getElementById("olx-category-picker");
  if (!picker || state.selectedParser !== "olx") return;

  if (!state.olxCategories.loaded && !state.olxCategories.loading) {
    loadOlxCategories().then(() => renderOlxCategoryPicker());
  }

  if (state.olxCategories.loading) {
    picker.innerHTML = `<div class="empty-state">Загружаю категории OLX...</div>`;
    return;
  }
  if (state.olxCategories.error) {
    picker.innerHTML = `<div class="empty-state">Ошибка загрузки категорий: ${escapeHtml(state.olxCategories.error)}</div>`;
    return;
  }
  if (!state.olxCategories.level1.length) {
    picker.innerHTML = `<div class="empty-state">Категории не найдены.</div>`;
    return;
  }

  picker.innerHTML = `
    <div class="grid grid-2">
      <div>
        <label for="olx-level1">Категория (L1)</label>
        <select id="olx-level1"></select>
      </div>
      <div>
        <label for="olx-level2">Подкатегория (L2)</label>
        <select id="olx-level2"></select>
      </div>
      <div class="full">
        <label for="olx-level3">Раздел (L3)</label>
        <select id="olx-level3"></select>
      </div>
      <div class="full olx-location-card">
        <label for="olx-location">Город объявлений</label>
        <select id="olx-location"></select>
        <p class="field-hint">Как в OLX locations-list: город добавляется в конец ссылки поиска.</p>
      </div>
      <div class="full manual-input-row">
        <button type="button" class="ghost-button" id="olx-manual-btn">${state.olxCategories.manualUrl ? "Вернуть авто-режим" : "Редактировать вручную"}</button>
      </div>
    </div>
  `;

  const level1El = document.getElementById("olx-level1");
  const level2El = document.getElementById("olx-level2");
  const level3El = document.getElementById("olx-level3");
  const locationEl = document.getElementById("olx-location");
  const manualBtn = document.getElementById("olx-manual-btn");
  const urlInput = formEl.elements.category_url;
  if (!level1El || !level2El || !level3El || !locationEl || !manualBtn || !urlInput) return;

  const level1Items = state.olxCategories.level1;
  const initial = parseOlxUrlPath(urlInput.value);
  fillOlxLocationOptions(locationEl, initial.location);
  fillSelectOptionsObjects(
    level1El,
    level1Items.map((item) => ({ value: item.slug, label: item.name || item.slug })),
    initial.l1 || level1Items[0]?.slug || ""
  );

  const syncLevel2 = (preferredL2 = "", preferredL3 = "") => {
    const selectedL1 = level1Items.find((item) => item.slug === level1El.value) || level1Items[0];
    const level2Items = selectedL1?.level2 || [];
    fillSelectOptionsObjectsWithEmpty(
      level2El,
      level2Items.map((item) => ({ value: item.slug, label: item.name || item.slug })),
      preferredL2
    );
    const selectedL2 = level2Items.find((item) => item.slug === level2El.value);
    const level3Items = selectedL2?.level3 || [];
    fillSelectOptionsObjectsWithEmpty(
      level3El,
      level3Items.map((item) => ({ value: item.slug, label: item.name || item.slug })),
      preferredL3
    );
  };

  const applyOlxUrl = () => {
    if (state.olxCategories.manualUrl) return;
    const l1 = level1El.value || "";
    const l2 = level2El.value || "";
    const l3 = level3El.value || "";
    const location = locationEl.value || "";
    const url = buildOlxCategoryUrl(l1, l2, l3, location);
    if (url) {
      urlInput.value = url;
      setFormMessage(`Ссылка обновлена: ${url}`);
    }
  };

  syncLevel2(initial.l2, initial.l3);
  urlInput.readOnly = !state.olxCategories.manualUrl;

  level1El.addEventListener("change", () => {
    syncLevel2("", "");
    applyOlxUrl();
  });
  level2El.addEventListener("change", () => {
    syncLevel2(level2El.value, "");
    applyOlxUrl();
  });
  level3El.addEventListener("change", applyOlxUrl);
  locationEl.addEventListener("change", applyOlxUrl);

  manualBtn.addEventListener("click", () => {
    state.olxCategories.manualUrl = !state.olxCategories.manualUrl;
    urlInput.readOnly = !state.olxCategories.manualUrl;
    manualBtn.textContent = state.olxCategories.manualUrl ? "Вернуть авто-режим" : "Редактировать вручную";
    if (!state.olxCategories.manualUrl) {
      applyOlxUrl();
    }
  });
}

function render2gisRubricPicker() {
  const picker = document.getElementById("2gis-rubric-picker");
  if (!picker || state.selectedParser !== "2gis") return;

  if (!state.rubrics2gis.loaded && !state.rubrics2gis.loading) {
    load2gisRubrics().then(() => render2gisRubricPicker());
  }

  if (state.rubrics2gis.loading) {
    picker.innerHTML = `<div class="empty-state">Загружаю рубрики 2GIS...</div>`;
    return;
  }
  if (state.rubrics2gis.error) {
    picker.innerHTML = `<div class="empty-state">Ошибка загрузки рубрик: ${escapeHtml(state.rubrics2gis.error)}</div>`;
    return;
  }
  if (!state.rubrics2gis.level1.length) {
    picker.innerHTML = `<div class="empty-state">Рубрики не найдены.</div>`;
    return;
  }

  const searchUrlInput = formEl.elements.search_url;
  const parsed = parse2gisSearchUrl(searchUrlInput?.value);
  picker.innerHTML = `
    <div class="grid grid-2">
      <div>
        <label for="rubric-domain">Домен</label>
        <select id="rubric-domain">
          <option value="kz">kz</option>
          <option value="ru">ru</option>
          <option value="com">com</option>
        </select>
      </div>
      <div>
        <label for="rubric-city">Город (slug)</label>
        <input id="rubric-city" type="text" value="${escapeHtml(parsed.city || "astana")}" placeholder="astana" />
      </div>
      <div>
        <label for="rubric-level1">Категория</label>
        <select id="rubric-level1"></select>
      </div>
      <div>
        <label for="rubric-level2">Рубрика 2го уровня</label>
        <select id="rubric-level2"></select>
      </div>
      <div class="full">
        <label for="rubric-level3">Рубрика</label>
        <select id="rubric-level3"></select>
      </div>
      <div class="full">
        <button type="button" class="ghost-button" id="rubric-apply-btn">Подставить рубрику в ссылку</button>
      </div>
    </div>
  `;

  const domainEl = document.getElementById("rubric-domain");
  const cityEl = document.getElementById("rubric-city");
  const level1El = document.getElementById("rubric-level1");
  const level2El = document.getElementById("rubric-level2");
  const level3El = document.getElementById("rubric-level3");
  const applyBtn = document.getElementById("rubric-apply-btn");

  if (!domainEl || !cityEl || !level1El || !level2El || !level3El || !applyBtn) return;
  domainEl.value = parsed.domain || "kz";

  const level1Items = state.rubrics2gis.level1;
  fillSelectOptions(level1El, level1Items.map((x) => x.name), level1Items[0]?.name || "");

  const syncLevel2 = (preferredLevel2 = "", preferredRubric = "") => {
    const selectedLevel1 = level1Items.find((x) => x.name === level1El.value) || level1Items[0];
    const level2Items = selectedLevel1?.level2 || [];
    fillSelectOptionsWithEmpty(level2El, level2Items.map((x) => x.name), preferredLevel2);
    const selectedLevel2 = level2Items.find((x) => x.name === level2El.value);
    const rubrics = selectedLevel2?.rubrics || [];
    fillSelectOptionsWithEmpty(level3El, rubrics, preferredRubric);
  };

  const applyToSearchUrl = () => {
    if (!searchUrlInput) return;
    const rubric = level3El.value || level2El.value || level1El.value || "";
    const url = build2gisSearchUrl(domainEl.value, cityEl.value, rubric);
    if (url) {
      searchUrlInput.value = url;
      setFormMessage(`Ссылка обновлена: ${url}`);
    }
  };

  let initialLevel1 = level1Items[0]?.name || "";
  let initialLevel2 = "";
  let initialLevel3 = "";
  for (const item of level1Items) {
    const foundLevel2 = (item.level2 || []).find((x) => (x.rubrics || []).includes(parsed.rubric));
    if (foundLevel2) {
      initialLevel1 = item.name;
      initialLevel2 = foundLevel2.name;
      initialLevel3 = parsed.rubric || "";
      break;
    }
  }
  level1El.value = initialLevel1;
  syncLevel2(initialLevel2, initialLevel3);

  level1El.addEventListener("change", () => {
    syncLevel2("", "");
    applyToSearchUrl();
  });
  level2El.addEventListener("change", () => {
    syncLevel2(level2El.value, "");
    applyToSearchUrl();
  });
  applyBtn.addEventListener("click", applyToSearchUrl);
  level3El.addEventListener("change", applyToSearchUrl);
}

function renderJobs() {
  if (!jobsListEl) return;
  const query = jobsSearchQuery.trim().toLowerCase();
  const jobsToRender = !query ? state.jobs : state.jobs.filter((job) => {
    const haystack = `${job.job_id} ${job.parser_key} ${job.status} ${job.output_path || ""}`.toLowerCase();
    return haystack.includes(query);
  });

  if (!jobsToRender.length) {
    jobsListEl.innerHTML = `<div class="empty-state">Здесь появятся ваши запуски.</div>`;
    return;
  }

  jobsListEl.innerHTML = "";
  jobsToRender.forEach((job) => {
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
      ${progressHtml(job, "compact")}
    `;
    card.addEventListener("click", () => {
      state.selectedJobId = job.job_id;
      renderJobs();
      loadJobDetails();
    });
    jobsListEl.appendChild(card);
  });
}

function updateHeaderStats() {
  if (statTotalJobsEl) {
    statTotalJobsEl.textContent = String(state.jobs.length);
  }
  if (statRunningJobsEl) {
    const active = state.jobs.filter((job) => ["running", "queued", "paused"].includes(job.status)).length;
    statRunningJobsEl.textContent = String(active);
  }
  if (statDbTotalEl) {
    statDbTotalEl.textContent = String(state.db.total || 0);
  }
}

function renderJobDetails(job) {
  if (!jobDetailsEl) return;
  if (!job) {
    jobDetailsEl.className = "job-details empty-state";
    jobDetailsEl.textContent = "Выберите задачу справа, чтобы посмотреть детали запуска.";
    return;
  }

  jobDetailsEl.className = "job-details";
  const command = (job.command || []).map((part) => {
    return /\s/.test(part) ? `"${part}"` : part;
  }).join(" ");
  const canPause = job.status === "running";
  const canStart = job.status === "paused";
  const canStop = job.status === "running" || job.status === "paused" || job.status === "queued";
  const canRestart = ["completed", "failed", "stopped"].includes(job.status);
  const snapshots = Array.isArray(job.snapshots) ? job.snapshots : [];
  const progress = jobProgress(job);

  jobDetailsEl.innerHTML = `
    <div class="detail-card">
      <div class="detail-row">
        <div class="detail-title">${job.parser_key.toUpperCase()} • ${job.job_id}</div>
        <span class="${statusClass(job.status)}">${jobStatusLabel(job.status)}</span>
      </div>
      <div class="progress-hero">
        <div>
          <span>Прогресс парсинга</span>
          <strong>${escapeHtml(progress.label)}</strong>
        </div>
        <b>${progress.indeterminate ? "live" : `${progress.percent}%`}</b>
      </div>
      ${progressHtml(job, "detail")}
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
      <pre class="log-box">${escapeHtml(trimLog(job.log || "Лог пока пуст."))}</pre>
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
    setFormMessage(successText, "success");
    await refreshJobs();
    await loadJobDetails();
  } catch (error) {
    setFormMessage(error.message, "error");
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

function trimLog(value, maxChars = 200000, maxLines = 1500) {
  const text = String(value || "");
  const lines = text.split("\n");
  const tailLines = lines.length > maxLines ? lines.slice(-maxLines) : lines;
  const tailText = tailLines.join("\n");
  if (tailText.length <= maxChars) return tailText;
  return tailText.slice(tailText.length - maxChars);
}

function clip(value, maxLen = 120) {
  const text = String(value || "").trim();
  if (!text) return "—";
  return text.length > maxLen ? `${text.slice(0, maxLen - 1)}…` : text;
}

function renderDbTable() {
  if (!dbResultsBodyEl || !dbSummaryEl) return;
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
  updateHeaderStats();
}

function renderExportFieldSelector() {
  if (!dbExportFieldsEl) return;
  if (!state.exports.fields.length) {
    dbExportFieldsEl.innerHTML = `<div class="empty-state">Поля выгрузки загружаются...</div>`;
    return;
  }
  dbExportFieldsEl.innerHTML = state.exports.fields.map((field) => (
    `<label class="db-export-field">
      <input type="checkbox" name="export-field" value="${escapeHtml(field.key)}" checked />
      <span>${escapeHtml(field.label)}</span>
    </label>`
  )).join("");
}

function collectExportPayload() {
  const checked = Array.from(document.querySelectorAll('input[name="export-field"]:checked'))
    .map((item) => item.value);
  return {
    format: exportFormatEl?.value || "xlsx",
    file_name: exportFileNameEl?.value.trim() || "",
    fields: checked,
    filters: {
      source: exportSourceEl?.value || "",
      run_status: exportRunStatusEl?.value || "",
      has_phone: exportHasPhoneEl?.value || "",
      date_from: exportDateFromEl?.value || "",
      date_to: exportDateToEl?.value || "",
      search: exportSearchEl?.value.trim() || "",
      max_rows: exportMaxRowsEl?.value || "50000",
    },
  };
}

function renderExportJobs() {
  if (!dbExportJobsEl) return;
  if (!state.exports.jobs.length) {
    dbExportJobsEl.innerHTML = `<div class="empty-state">Здесь появятся задачи выгрузки.</div>`;
    return;
  }
  dbExportJobsEl.innerHTML = state.exports.jobs.map((job) => {
    const progress = Number(job.progress || 0);
    const isDone = job.status === "completed";
    const isRunning = ["queued", "running"].includes(job.status);
    const downloadButton = isDone && job.output_path
      ? `<a class="ghost-button" href="/api/db/exports/${job.job_id}/download" target="_blank" rel="noopener noreferrer">Скачать</a>`
      : "";
    const stopButton = isRunning
      ? `<button class="danger-button" type="button" data-export-stop="${job.job_id}">Остановить</button>`
      : "";
    return `
      <div class="db-export-job">
        <div class="db-export-job-top">
          <strong>${escapeHtml(job.file_name || job.job_id)}</strong>
          <span class="${statusClass(job.status)}">${jobStatusLabel(job.status)}</span>
        </div>
        <div class="db-export-job-meta">
          <span>${formatDateTime(job.created_at)}</span>
          <span>Формат: ${escapeHtml(job.format || "")}</span>
          <span>Строк: ${job.exported_rows || 0} / ${job.total_rows || 0}</span>
        </div>
        <div class="db-export-progress"><span style="width:${progress}%"></span></div>
        ${job.error ? `<div class="form-message error" style="margin-top:8px;">${escapeHtml(job.error)}</div>` : ""}
        <div class="db-export-job-actions">
          ${downloadButton}
          ${stopButton}
        </div>
      </div>
    `;
  }).join("");

  dbExportJobsEl.querySelectorAll("[data-export-stop]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const jobId = btn.getAttribute("data-export-stop");
      if (!jobId) return;
      try {
        await api(`/api/db/exports/${jobId}/stop`, { method: "POST", body: "{}" });
        setExportMessage(`Выгрузка ${jobId} остановлена.`, "success");
        await loadExportJobs();
      } catch (error) {
        setExportMessage(error.message, "error");
      }
    });
  });
}

async function loadExportConfig() {
  try {
    const source = exportSourceEl?.value || "";
    const query = new URLSearchParams();
    if (source) query.set("source", source);
    const data = await api(`/api/db/export/config?${query.toString()}`);
    state.exports.fields = Array.isArray(data.fields) ? data.fields : [];
    renderExportFieldSelector();
    setExportMessage(`Поля загружены: ${state.exports.fields.length}`);
  } catch (error) {
    setExportMessage(`Ошибка конфигурации выгрузки: ${error.message}`, "error");
  }
}

async function loadExportJobs() {
  try {
    const data = await api("/api/db/exports");
    state.exports.jobs = Array.isArray(data.jobs) ? data.jobs : [];
    renderExportJobs();
  } catch (error) {
    setExportMessage(`Ошибка загрузки задач выгрузки: ${error.message}`, "error");
  }
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
  if (!dbSourceEl || !dbRunStatusEl || !dbHasPhoneEl || !dbSearchEl || !dbLimitEl) return;
  dbSourceEl.value = state.db.filters.source || "";
  dbRunStatusEl.value = state.db.filters.run_status || "";
  dbHasPhoneEl.value = state.db.filters.has_phone || "";
  dbSearchEl.value = state.db.filters.search || "";
  dbLimitEl.value = String(state.db.filters.limit || 100);
}

async function loadDbRecords() {
  if (!dbResultsBodyEl || !dbSummaryEl) return;
  try {
    const query = buildDbQuery(state.db.filters);
    const data = await api(`/api/db/records?${query}`);
    state.db.records = data.records || [];
    state.db.total = data.total || 0;
    state.db.page = data.filters?.page || state.db.filters.page || 1;
    state.db.pages = data.pages || 1;
    renderDbTable();
  } catch (error) {
    if (dbResultsBodyEl) {
      dbResultsBodyEl.innerHTML = `<tr><td colspan="11" class="db-empty">Ошибка загрузки БД: ${escapeHtml(error.message)}</td></tr>`;
    }
    if (dbSummaryEl) {
      dbSummaryEl.textContent = "Ошибка загрузки.";
    }
    updateHeaderStats();
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
  updateHeaderStats();
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

if (formEl) {
  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormMessage("Запускаю задачу...");
    try {
      if (state.selectedParser === "olx" && !state.olxCategories.manualUrl) {
        const level1El = document.getElementById("olx-level1");
        const level2El = document.getElementById("olx-level2");
        const level3El = document.getElementById("olx-level3");
        const locationEl = document.getElementById("olx-location");
        const categoryUrlInput = formEl.elements.category_url;
        if (categoryUrlInput && level1El) {
          const url = buildOlxCategoryUrl(
            level1El.value,
            level2El?.value || "",
            level3El?.value || "",
            locationEl?.value || "",
          );
          if (url) categoryUrlInput.value = url;
        }
      }

      if (state.selectedParser === "2gis") {
        const domainEl = document.getElementById("rubric-domain");
        const cityEl = document.getElementById("rubric-city");
        const level1El = document.getElementById("rubric-level1");
        const level2El = document.getElementById("rubric-level2");
        const level3El = document.getElementById("rubric-level3");
        const searchUrlInput = formEl.elements.search_url;
        if (domainEl && cityEl && searchUrlInput) {
          const rubric = (level3El?.value || level2El?.value || level1El?.value || "").trim();
          const url = build2gisSearchUrl(domainEl.value, cityEl.value, rubric);
          if (url) searchUrlInput.value = url;
        }
      }
      const payload = collectFormPayload();
      const data = await api("/api/run", {
        method: "POST",
        body: JSON.stringify({
          parser_key: state.selectedParser,
          payload,
        }),
      });
      setFormMessage(`Задача ${data.job.job_id} запущена.`, "success");
      state.selectedJobId = data.job.job_id;
      await refreshJobs();
      await loadJobDetails();
      await loadDbTotalsOnly();
    } catch (error) {
      setFormMessage(error.message, "error");
    }
  });
}

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

dbExportFieldsAllEl?.addEventListener("click", () => {
  const all = dbExportFieldsEl?.querySelectorAll('input[name="export-field"]') || [];
  all.forEach((item) => {
    item.checked = true;
  });
});

exportSourceEl?.addEventListener("change", async () => {
  await loadExportConfig();
});

dbExportFormEl?.addEventListener("submit", async (event) => {
  event.preventDefault();
  setExportMessage("Запускаю выгрузку...");
  try {
    const payload = collectExportPayload();
    if (!payload.fields.length) {
      setExportMessage("Выбери хотя бы одно поле для выгрузки.", "error");
      return;
    }
    const data = await api("/api/db/export", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setExportMessage(`Выгрузка ${data.job.job_id} запущена.`, "success");
    await loadExportJobs();
  } catch (error) {
    setExportMessage(error.message, "error");
  }
});

jobsSearchEl?.addEventListener("input", () => {
  jobsSearchQuery = jobsSearchEl.value || "";
  renderJobs();
});

async function loadDbTotalsOnly() {
  try {
    const data = await api("/api/db/records?limit=1&page=1");
    state.db.total = data.total || 0;
    updateHeaderStats();
  } catch {
    // Ignore totals refresh errors to avoid noisy UX.
  }
}

function startPolling(task, intervalMs) {
  return window.setInterval(() => {
    if (document.hidden) return;
    task().catch(() => {});
  }, intervalMs);
}

async function bootHubPage() {
  await loadConfig();
  await refreshJobs();
  await loadJobDetails();
  await loadDbTotalsOnly();

  startPolling(async () => {
    await refreshJobs();
    await loadJobDetails();
  }, 3000);

  startPolling(loadDbTotalsOnly, 12000);
}

async function bootDbPage() {
  syncDbFormWithState();
  await refreshJobs();
  await loadDbRecords();

  startPolling(loadDbRecords, 12000);
  startPolling(refreshJobs, 15000);
}

async function bootExportPage() {
  await loadExportConfig();
  await loadExportJobs();
  await refreshJobs();
  await loadDbTotalsOnly();

  startPolling(loadExportJobs, 5000);
  startPolling(refreshJobs, 15000);
  startPolling(loadDbTotalsOnly, 15000);
}

async function boot() {
  if (currentPage === "db") {
    await bootDbPage();
    return;
  }
  if (currentPage === "export") {
    await bootExportPage();
    return;
  }
  await bootHubPage();
}

boot().catch((error) => {
  setFormMessage(error.message, "error");
});
