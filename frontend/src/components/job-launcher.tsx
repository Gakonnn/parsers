"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  OLX_LOCATIONS,
  KRISHA_LOCATIONS,
  build2gisSearchUrl,
  buildKrishaListingUrl,
  buildOlxCategoryUrl,
  findKrishaLocationByAlias,
  parse2gisSearchUrl,
  parseKrishaListingUrl,
  parseOlxUrlPath,
} from "@/lib/parser-options";
import type { OlxCategoriesTree, ParserJob, ParserSource, TwoGisCitiesTree, TwoGisRubricsTree } from "@/lib/types";

const sourceDefaults: Record<ParserSource, { label: string; urlLabel: string; url: string; limitLabel: string; hint: string }> = {
  olx: {
    label: "OLX.kz",
    urlLabel: "Ссылка категории",
    url: "https://www.olx.kz/elektronika/",
    limitLabel: "Лимит объявлений",
    hint: "Выберите категорию и город, URL соберется как на OLX locations-list.",
  },
  krisha: {
    label: "Krisha.kz",
    urlLabel: "Ссылка листинга",
    url: "https://krisha.kz/prodazha/kvartiry/",
    limitLabel: "Лимит объявлений",
    hint: "Можно выбрать область, город или район. Самый глубокий уровень попадет в URL.",
  },
  "2gis": {
    label: "2GIS",
    urlLabel: "Ссылка поиска",
    url: "https://2gis.kz/astana/search/Поесть",
    limitLabel: "Максимум организаций",
    hint: "Выберите домен, город и рубрику. Поддерживаются 3 уровня рубрик.",
  },
  kolesa: {
    label: "Kolesa.kz",
    urlLabel: "Ссылка листинга",
    url: "https://kolesa.kz/cars/",
    limitLabel: "Лимит объявлений",
    hint: "Kolesa стартует через HTTP-листинг, телефоны берутся через API-сессии.",
  },
};

function buildParameters(source: ParserSource, url: string, limit: number): Record<string, unknown> {
  if (source === "olx") return { category_url: url, limit, output_name: "" };
  if (source === "2gis") {
    return {
      search_url: url,
      max_records: limit,
      delay_between_clicks: 250,
      format: "xlsx",
      start_maximized: false,
      run_via_agent: false,
      output_name: "",
    };
  }
  if (source === "krisha") {
    return {
      listing_url: url,
      listing_limit: limit,
      output_name: "result_random.json",
      driver: "selenium",
      browser: "chrome",
      no_proxy: true,
      headless: true,
      cookie_file: "",
      account_login: "",
      account_password: "",
    };
  }
  return {
    listing_url: url,
    listing_limit: limit,
    output_name: "kolesa_results.json",
    driver: "http",
    no_proxy: true,
    headless: true,
    verify_ssl: false,
  };
}

function selectedText(parts: string[]): string {
  return parts.filter(Boolean).join(" / ") || "Не выбрано";
}

export function JobLauncher({ onCreated }: { onCreated?: (job: ParserJob) => void }) {
  const [source, setSource] = useState<ParserSource>("2gis");
  const [url, setUrl] = useState(sourceDefaults["2gis"].url);
  const [limit, setLimit] = useState(50);
  const [manualUrl, setManualUrl] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const [olxTree, setOlxTree] = useState<OlxCategoriesTree | null>(null);
  const [olxLoading, setOlxLoading] = useState(false);
  const [olxError, setOlxError] = useState("");
  const [olxL1, setOlxL1] = useState("");
  const [olxL2, setOlxL2] = useState("");
  const [olxL3, setOlxL3] = useState("");
  const [olxLocation, setOlxLocation] = useState("");

  const [gisRubrics, setGisRubrics] = useState<TwoGisRubricsTree | null>(null);
  const [gisCities, setGisCities] = useState<TwoGisCitiesTree | null>(null);
  const [gisLoading, setGisLoading] = useState(false);
  const [gisError, setGisError] = useState("");
  const [gisDomain, setGisDomain] = useState("kz");
  const [gisCity, setGisCity] = useState("astana");
  const [gisL1, setGisL1] = useState("");
  const [gisL2, setGisL2] = useState("");
  const [gisL3, setGisL3] = useState("");

  const [krishaRoot, setKrishaRoot] = useState("");
  const [krishaCity, setKrishaCity] = useState("");
  const [krishaDistrict, setKrishaDistrict] = useState("");

  const selected = useMemo(() => sourceDefaults[source], [source]);
  const olxLevel1Items = olxTree?.level1 || [];
  const selectedOlxL1 = olxLevel1Items.find((item) => item.slug === olxL1);
  const olxLevel2Items = selectedOlxL1?.level2 || [];
  const selectedOlxL2 = olxLevel2Items.find((item) => item.slug === olxL2);
  const olxLevel3Items = selectedOlxL2?.level3 || [];

  const gisDomains = useMemo(() => {
    const preferred = ["kz", "ru", "kg", "uz", "az", "ae"];
    return [...new Set([...preferred, ...(gisCities?.domains || [])])].filter(Boolean);
  }, [gisCities]);
  const gisCityItems = useMemo(() => (gisCities?.cities || []).filter((city) => city.domain === gisDomain), [gisCities, gisDomain]);
  const gisLevel1Items = gisRubrics?.level1 || [];
  const selectedGisL1 = gisLevel1Items.find((item) => item.name === gisL1);
  const gisLevel2Items = selectedGisL1?.level2 || [];
  const selectedGisL2 = gisLevel2Items.find((item) => item.name === gisL2);
  const gisLevel3Items = selectedGisL2?.rubrics || [];

  const selectedKrishaRoot = KRISHA_LOCATIONS.find((item) => item.alias === krishaRoot) || KRISHA_LOCATIONS[0];
  const krishaCityItems = selectedKrishaRoot.cities || [];
  const selectedKrishaCity = krishaCityItems.find((item) => item.alias === krishaCity) || null;
  const krishaDistrictItems = selectedKrishaCity?.districts || selectedKrishaRoot.districts || [];

  useEffect(() => {
    if (source !== "olx" || olxTree || olxLoading) return;
    setOlxLoading(true);
    setOlxError("");
    api.olxCategories()
      .then((data) => setOlxTree(data))
      .catch((error) => setOlxError(error instanceof Error ? error.message : "Не удалось загрузить категории OLX"))
      .finally(() => setOlxLoading(false));
  }, [source, olxTree, olxLoading]);

  useEffect(() => {
    if (source !== "2gis" || gisLoading || (gisRubrics && gisCities)) return;
    setGisLoading(true);
    setGisError("");
    Promise.all([api.twoGisRubrics(), api.twoGisCities()])
      .then(([rubrics, cities]) => {
        setGisRubrics(rubrics);
        setGisCities(cities);
      })
      .catch((error) => setGisError(error instanceof Error ? error.message : "Не удалось загрузить справочники 2GIS"))
      .finally(() => setGisLoading(false));
  }, [source, gisLoading, gisRubrics, gisCities]);

  useEffect(() => {
    if (source !== "olx" || !olxTree?.level1.length) return;
    const parsed = parseOlxUrlPath(url);
    const first = olxTree.level1[0];
    setOlxL1(parsed.l1 || first.slug);
    setOlxL2(parsed.l2);
    setOlxL3(parsed.l3);
    setOlxLocation(parsed.location);
  }, [source, olxTree]);

  useEffect(() => {
    if (source !== "2gis") return;
    const parsed = parse2gisSearchUrl(url);
    setGisDomain(parsed.domain || "kz");
    setGisCity(parsed.city || "astana");
  }, [source]);

  useEffect(() => {
    if (source !== "2gis" || !gisLevel1Items.length) return;
    if (!gisL1) setGisL1(gisLevel1Items[0].name);
  }, [source, gisLevel1Items, gisL1]);

  useEffect(() => {
    if (source !== "2gis" || !gisCityItems.length) return;
    if (!gisCityItems.some((city) => city.code === gisCity)) {
      setGisCity(gisCityItems.find((city) => city.code === "astana")?.code || gisCityItems[0].code);
    }
  }, [source, gisCityItems, gisCity]);

  useEffect(() => {
    if (source !== "krisha") return;
    const parsed = parseKrishaListingUrl(url);
    const initial = findKrishaLocationByAlias(parsed.location);
    setKrishaRoot(initial.root.alias);
    setKrishaCity(initial.city?.alias || "");
    setKrishaDistrict(initial.district?.alias || "");
  }, [source]);

  const generatedUrl = useMemo(() => {
    if (source === "olx") return buildOlxCategoryUrl(olxL1, olxL2, olxL3, olxLocation);
    if (source === "2gis") return build2gisSearchUrl(gisDomain, gisCity, gisL3 || gisL2 || gisL1);
    if (source === "krisha") {
      const parsed = parseKrishaListingUrl(url);
      return buildKrishaListingUrl(parsed.baseParts, krishaDistrict || krishaCity || krishaRoot);
    }
    return url;
  }, [source, olxL1, olxL2, olxL3, olxLocation, gisDomain, gisCity, gisL1, gisL2, gisL3, krishaRoot, krishaCity, krishaDistrict, url]);

  useEffect(() => {
    if (manualUrl || source === "kolesa" || !generatedUrl || generatedUrl === url) return;
    setUrl(generatedUrl);
  }, [manualUrl, source, generatedUrl, url]);

  function changeSource(next: ParserSource) {
    setSource(next);
    setUrl(sourceDefaults[next].url);
    setManualUrl(false);
    setMessage("");
    if (next === "2gis") {
      setGisDomain("kz");
      setGisCity("astana");
      setGisL1("");
      setGisL2("");
      setGisL3("");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const safeLimit = Math.max(1, Math.min(5000, Number(limit) || 1));
      const finalUrl = manualUrl ? url.trim() : (generatedUrl || url).trim();
      const job = await api.createJob(source, buildParameters(source, finalUrl, safeLimit), safeLimit);
      setUrl(finalUrl);
      setMessage("Задача создана и поставлена в очередь.");
      onCreated?.(job);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось создать задачу");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="launcher-card" onSubmit={submit}>
      <div className="launcher-header">
        <div>
          <span className="eyebrow">Новый запуск</span>
          <h2>Создать задачу парсинга</h2>
        </div>
        <span className="soft-badge">готово к запуску</span>
      </div>

      <div className="source-switcher" role="tablist" aria-label="Источник парсинга">
        {(Object.keys(sourceDefaults) as ParserSource[]).map((key) => (
          <button key={key} type="button" className={key === source ? "active" : ""} onClick={() => changeSource(key)}>
            {sourceDefaults[key].label}
          </button>
        ))}
      </div>

      {source === "olx" ? (
        <div className="selector-card">
          <div className="selector-title"><strong>Категория и город OLX</strong><span>{olxLoading ? "Загрузка sitemap..." : selectedText([selectedOlxL1?.name || "", selectedOlxL2?.name || "", olxLevel3Items.find((item) => item.slug === olxL3)?.name || ""])}</span></div>
          {olxError ? <p className="selector-error">{olxError}. Можно включить ручной режим и вставить URL.</p> : null}
          <div className="selector-grid">
            <label className="field-block compact"><span>Категория</span><select value={olxL1} onChange={(event) => { setOlxL1(event.target.value); setOlxL2(""); setOlxL3(""); }}><option value="">Выберите</option>{olxLevel1Items.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label>
            <label className="field-block compact"><span>Подкатегория</span><select value={olxL2} onChange={(event) => { setOlxL2(event.target.value); setOlxL3(""); }} disabled={!olxLevel2Items.length}><option value="">Не выбрано</option>{olxLevel2Items.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label>
            <label className="field-block compact"><span>Раздел</span><select value={olxL3} onChange={(event) => setOlxL3(event.target.value)} disabled={!olxLevel3Items.length}><option value="">Не выбрано</option>{olxLevel3Items.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label>
            <label className="field-block compact"><span>Город</span><select value={olxLocation} onChange={(event) => setOlxLocation(event.target.value)}><option value="">Все города</option>{OLX_LOCATIONS.map((group) => <optgroup key={group.region} label={group.region}>{group.cities.map((city) => <option key={city.slug} value={city.slug}>{city.name}</option>)}</optgroup>)}</select></label>
          </div>
        </div>
      ) : null}

      {source === "2gis" ? (
        <div className="selector-card">
          <div className="selector-title"><strong>Город и рубрика 2GIS</strong><span>{gisLoading ? "Загрузка справочников..." : selectedText([gisCity, gisL1, gisL2, gisL3])}</span></div>
          {gisError ? <p className="selector-error">{gisError}. Можно включить ручной режим и вставить URL.</p> : null}
          <div className="selector-grid">
            <label className="field-block compact"><span>Домен</span><select value={gisDomain} onChange={(event) => { setGisDomain(event.target.value); setGisCity(""); }}>{gisDomains.map((domain) => <option key={domain} value={domain}>{domain}</option>)}</select></label>
            <label className="field-block compact"><span>Город</span><select value={gisCity} onChange={(event) => setGisCity(event.target.value)}>{gisCityItems.map((city) => <option key={`${city.domain}-${city.code}`} value={city.code}>{city.name} ({city.code})</option>)}</select></label>
            <label className="field-block compact"><span>Категория</span><select value={gisL1} onChange={(event) => { setGisL1(event.target.value); setGisL2(""); setGisL3(""); }}><option value="">Выберите</option>{gisLevel1Items.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
            <label className="field-block compact"><span>Рубрика 2-го уровня</span><select value={gisL2} onChange={(event) => { setGisL2(event.target.value); setGisL3(""); }} disabled={!gisLevel2Items.length}><option value="">Не выбрано</option>{gisLevel2Items.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
            <label className="field-block compact wide-selector"><span>Рубрика</span><select value={gisL3} onChange={(event) => setGisL3(event.target.value)} disabled={!gisLevel3Items.length}><option value="">Не выбрано</option>{gisLevel3Items.map((rubric) => <option key={rubric} value={rubric}>{rubric}</option>)}</select></label>
          </div>
        </div>
      ) : null}

      {source === "krisha" ? (
        <div className="selector-card">
          <div className="selector-title"><strong>Регион Krisha</strong><span>{selectedText([selectedKrishaRoot.name, selectedKrishaCity?.name || "", krishaDistrictItems.find((item) => item.alias === krishaDistrict)?.name || ""])}</span></div>
          <div className="selector-grid">
            <label className="field-block compact"><span>Область / город</span><select value={krishaRoot} onChange={(event) => { setKrishaRoot(event.target.value); setKrishaCity(""); setKrishaDistrict(""); }}>{KRISHA_LOCATIONS.map((item) => <option key={item.alias || "country"} value={item.alias}>{item.name}</option>)}</select></label>
            <label className="field-block compact"><span>Город</span><select value={krishaCity} onChange={(event) => { setKrishaCity(event.target.value); setKrishaDistrict(""); }} disabled={!krishaCityItems.length}><option value="">{selectedKrishaRoot.type === "region" ? "Вся область" : "Не требуется"}</option>{krishaCityItems.map((item) => <option key={item.alias} value={item.alias}>{item.name}</option>)}</select></label>
            <label className="field-block compact wide-selector"><span>Район</span><select value={krishaDistrict} onChange={(event) => setKrishaDistrict(event.target.value)} disabled={!krishaDistrictItems.length}><option value="">Весь город / регион</option>{krishaDistrictItems.map((item) => <option key={item.alias} value={item.alias}>{item.name}</option>)}</select></label>
          </div>
        </div>
      ) : null}

      <label className="field-block">
        <span>{selected.urlLabel}</span>
        <div className="url-control">
          <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder={selected.url} readOnly={!manualUrl && source !== "kolesa"} required />
          <button type="button" className="ghost-button" onClick={() => setManualUrl((value) => !value)}>
            {manualUrl ? "Авто" : "Вручную"}
          </button>
        </div>
      </label>

      <div className="form-grid two">
        <label className="field-block">
          <span>{selected.limitLabel}</span>
          <input min={1} max={5000} type="number" value={limit} onChange={(event) => setLimit(Number(event.target.value))} required />
        </label>
        <div className="hint-box">
          <strong>Рекомендация</strong>
          <span>{selected.hint}</span>
        </div>
      </div>

      <div className="form-footer">
        <button className="primary-button" disabled={busy} type="submit">
          {busy ? "Запускаю..." : "Запустить задачу"}
        </button>
        {message ? <p className={message.includes("Не удалось") ? "form-message error" : "form-message"}>{message}</p> : null}
      </div>
    </form>
  );
}
