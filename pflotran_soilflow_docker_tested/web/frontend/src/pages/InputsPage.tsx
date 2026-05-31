import { useEffect, useMemo, useState } from "react";
import { getCalculation, getInputWorkbook, listCalculations, resetInputWorkbook, saveInputWorkbook } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import type { CalculationSummary, InputField, InputTab, InputWorkbook, WeatherRow } from "../types";

function fieldInputType(field: InputField): string {
  if (field.value_type === "number") {
    return "number";
  }
  if (field.value_type === "date") {
    return "date";
  }
  return "text";
}

function fieldValue(field: InputField): string | number {
  if (field.value === null || field.value === undefined) {
    return "";
  }
  return field.value as string | number;
}

function updateField(tab: InputTab, key: string, value: string | number | boolean | null): InputTab {
  return {
    ...tab,
    fields: tab.fields.map((field) => (field.key === key ? { ...field, value } : field))
  };
}

function updateWeather(tab: InputTab, index: number, patch: Partial<WeatherRow>): InputTab {
  return {
    ...tab,
    weather: tab.weather.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row))
  };
}

function emptyWeatherRow(): WeatherRow {
  return {
    row: null,
    date: new Date().toISOString().slice(0, 10),
    precipitation_mm_day: 0,
    irrigation_mm_day: 0,
    epot_mm_day: 0,
    tpot_mm_day: 0,
    groundwater_depth_m: null,
    comment: ""
  };
}

function calculationIdFromLocation(): number | null {
  const rawValue = new URLSearchParams(window.location.search).get("calculation_id");
  if (!rawValue) {
    return null;
  }
  const parsed = Number(rawValue);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function setCalculationIdInLocation(calculationId: number | null): void {
  const nextUrl = new URL(window.location.href);
  if (calculationId) {
    nextUrl.searchParams.set("calculation_id", String(calculationId));
  } else {
    nextUrl.searchParams.delete("calculation_id");
  }
  window.history.replaceState({}, "", `${nextUrl.pathname}${nextUrl.search}`);
}

export function InputsPage() {
  const [workbook, setWorkbook] = useState<InputWorkbook | null>(null);
  const [activeTabId, setActiveTabId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [calculations, setCalculations] = useState<CalculationSummary[]>([]);
  const [search, setSearch] = useState("");

  const activeTab = useMemo(() => workbook?.tabs.find((tab) => tab.id === activeTabId) ?? workbook?.tabs[0] ?? null, [workbook, activeTabId]);

  async function loadWorkbook() {
    try {
      const calculationId = calculationIdFromLocation();
      const [next, calculationList] = await Promise.all([
        calculationId ? getCalculation(calculationId).then((calculation) => calculation.input) : getInputWorkbook(),
        listCalculations(search)
      ]);
      setWorkbook(next);
      setCalculations(calculationList);
      setActiveTabId((current) => current || next.tabs[0]?.id || "");
      if (calculationId && next.calculation_title) {
        setMessage(`${next.calculation_title} загружен из базы без пересчета.`);
      }
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось прочитать исходные данные");
    }
  }

  useEffect(() => {
    loadWorkbook();
  }, []);

  async function refreshCalculations(query = search) {
    try {
      setCalculations(await listCalculations(query));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось прочитать список расчетов");
    }
  }

  function replaceTab(nextTab: InputTab) {
    setWorkbook((current) => (current ? { ...current, tabs: current.tabs.map((tab) => (tab.id === nextTab.id ? nextTab : tab)) } : current));
  }

  async function save() {
    if (!workbook) {
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const saved = await saveInputWorkbook(workbook);
      setWorkbook(saved);
      setCalculationIdInLocation(saved.calculation_id);
      await refreshCalculations();
      setMessage(`${saved.calculation_title ?? "Расчет"} сохранен в базе данных проекта.`);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить исходные данные");
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    if (!window.confirm("Восстановить исходные данные из шаблона? Несохраненные изменения формы будут заменены.")) {
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const restored = await resetInputWorkbook();
      setWorkbook(restored);
      setActiveTabId(restored.tabs[0]?.id || "");
      setCalculationIdInLocation(null);
      setMessage("Исходные данные восстановлены из JSON-шаблона. Для записи в базу нажмите «Сохранить». ");
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось восстановить шаблон");
    } finally {
      setSaving(false);
    }
  }

  async function loadCalculation(calculationId: number) {
    setSaving(true);
    setMessage("");
    try {
      const calculation = await getCalculation(calculationId);
      setWorkbook(calculation.input);
      setActiveTabId(calculation.input.tabs[0]?.id || "");
      setCalculationIdInLocation(calculationId);
      setMessage(`${calculation.title} загружен из базы без пересчета.`);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить расчет");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <div className="page-title">
        <h1>Исходные данные</h1>
        <div className="toolbar compact-toolbar">
          <button type="button" onClick={loadWorkbook}>
            Обновить
          </button>
          <button type="button" onClick={reset} disabled={saving}>
            Сбросить
          </button>
          <button className="primary" type="button" onClick={save} disabled={!workbook || saving}>
            {saving ? "Сохранение..." : "Сохранить"}
          </button>
        </div>
      </div>
      <ErrorNotice message={error} />
      {message && <div className="notice">{message}</div>}
      {workbook && (
        <>
          <div className="source-meta">
            <span>{workbook.calculation_title ?? "Новый расчет из шаблона"}</span>
            <span>{workbook.calculation_created_at ? new Date(workbook.calculation_created_at).toLocaleString() : "еще не сохранен в базе"}</span>
            <span>Источник: база данных проекта</span>
          </div>
          <div className="panel calculation-browser">
            <div className="panel-header">
              <h2>Ранее сохраненные расчеты</h2>
              <div className="toolbar compact-toolbar">
                <input
                  type="search"
                  placeholder="номер, дата, статус"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      refreshCalculations(event.currentTarget.value);
                    }
                  }}
                />
                <button type="button" onClick={() => refreshCalculations()}>
                  Найти
                </button>
              </div>
            </div>
            <ul className="run-list calculation-list">
              {calculations.map((calculation) => (
                <li key={calculation.id}>
                  <button type="button" className={workbook.calculation_id === calculation.id ? "selected-button" : ""} onClick={() => loadCalculation(calculation.id)}>
                    <span>{calculation.title}</span>
                    <small>{new Date(calculation.created_at).toLocaleString()}</small>
                    <small>{calculation.has_results ? "результаты готовы" : "без результатов"}</small>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="tabs">
            {workbook.tabs.map((tab) => (
              <button type="button" key={tab.id} className={activeTab?.id === tab.id ? "tab-active" : ""} onClick={() => setActiveTabId(tab.id)}>
                {tab.title}
              </button>
            ))}
          </div>
          {activeTab?.description && <p className="muted source-description">{activeTab.description}</p>}
          {activeTab?.kind === "fields" && (
            <div className="field-grid">
              {activeTab.fields.map((field) => (
                <label className="source-field" key={`${field.sheet}:${field.key}`}>
                  <span className="source-field-name">{field.key}</span>
                  {field.value_type === "boolean" ? (
                    <input
                      type="checkbox"
                      checked={Boolean(field.value)}
                      onChange={(event) => replaceTab(updateField(activeTab, field.key, event.target.checked))}
                    />
                  ) : (
                    <input
                      type={fieldInputType(field)}
                      step={field.value_type === "number" ? "any" : undefined}
                      value={fieldValue(field)}
                      onChange={(event) => {
                        const nextValue = field.value_type === "number" && event.target.value !== "" ? Number(event.target.value) : event.target.value;
                        replaceTab(updateField(activeTab, field.key, nextValue));
                      }}
                    />
                  )}
                  <em>{field.description || "Пояснение для параметра не задано."}</em>
                </label>
              ))}
            </div>
          )}
          {activeTab?.kind === "weather" && (
            <div className="weather-editor">
              <table>
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Осадки</th>
                    <th>Полив</th>
                    <th>Epot</th>
                    <th>Tpot</th>
                    <th>ГВ</th>
                    <th>Комментарий</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {activeTab.weather.map((row, index) => (
                    <tr key={`${row.row ?? "new"}:${index}`}>
                      <td>
                        <input type="date" value={row.date.slice(0, 10)} onChange={(event) => replaceTab(updateWeather(activeTab, index, { date: event.target.value }))} />
                      </td>
                      <td>
                        <input type="number" step="any" value={row.precipitation_mm_day} onChange={(event) => replaceTab(updateWeather(activeTab, index, { precipitation_mm_day: Number(event.target.value) }))} />
                      </td>
                      <td>
                        <input type="number" step="any" value={row.irrigation_mm_day} onChange={(event) => replaceTab(updateWeather(activeTab, index, { irrigation_mm_day: Number(event.target.value) }))} />
                      </td>
                      <td>
                        <input type="number" step="any" value={row.epot_mm_day} onChange={(event) => replaceTab(updateWeather(activeTab, index, { epot_mm_day: Number(event.target.value) }))} />
                      </td>
                      <td>
                        <input type="number" step="any" value={row.tpot_mm_day} onChange={(event) => replaceTab(updateWeather(activeTab, index, { tpot_mm_day: Number(event.target.value) }))} />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="any"
                          value={row.groundwater_depth_m ?? ""}
                          onChange={(event) => replaceTab(updateWeather(activeTab, index, { groundwater_depth_m: event.target.value === "" ? null : Number(event.target.value) }))}
                        />
                      </td>
                      <td>
                        <input type="text" value={row.comment ?? ""} onChange={(event) => replaceTab(updateWeather(activeTab, index, { comment: event.target.value }))} />
                      </td>
                      <td>
                        <button type="button" onClick={() => replaceTab({ ...activeTab, weather: activeTab.weather.filter((_, rowIndex) => rowIndex !== index) })}>
                          Удалить
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button type="button" onClick={() => replaceTab({ ...activeTab, weather: [...activeTab.weather, emptyWeatherRow()] })}>
                Добавить день
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
