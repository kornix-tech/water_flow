import { useEffect, useMemo, useState } from "react";
import {
  createSoilCurve,
  deleteSoilCurve,
  getCalculation,
  getInputWorkbook,
  listCalculations,
  listSoilCurves,
  resetInputWorkbook,
  saveInputWorkbook
} from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import type { CalculationSummary, InputField, InputTab, InputWorkbook, SoilCurvePoint, SoilCurveTable, SoilCurveTableCreate, WeatherRow } from "../types";

const retentionOptions = [
  ["van_genuchten", "van Genuchten"],
  ["brooks_corey", "Brooks-Corey"],
  ["gardner", "Gardner"],
  ["tabular", "Табличная кривая"]
] as const;

const conductivityOptions = [
  ["mualem", "Mualem"],
  ["burdine", "Burdine"],
  ["corey", "Corey"],
  ["gardner", "Gardner"],
  ["tabular", "Табличная кривая"]
] as const;

const supportedSoilModelPairs = new Set([
  "van_genuchten:mualem",
  "van_genuchten:burdine",
  "van_genuchten:tabular",
  "brooks_corey:mualem",
  "brooks_corey:burdine",
  "brooks_corey:tabular",
  "tabular:tabular"
]);

function fieldByKey(workbook: InputWorkbook | null, key: string): InputField | null {
  for (const tab of workbook?.tabs ?? []) {
    const field = tab.fields.find((candidate) => candidate.key === key);
    if (field) {
      return field;
    }
  }
  return null;
}

function soilModelValidationMessage(workbook: InputWorkbook | null): string {
  const retentionModel = String(fieldByKey(workbook, "retention_model")?.value ?? "van_genuchten");
  const conductivityModel = String(fieldByKey(workbook, "conductivity_model")?.value ?? "mualem");
  if (supportedSoilModelPairs.has(`${retentionModel}:${conductivityModel}`)) {
    return "";
  }
  return [
    `Несовместимая или пока не проверенная пара моделей: ${retentionModel} + ${conductivityModel}.`,
    "Разрешены: van_genuchten + mualem, van_genuchten + burdine, brooks_corey + mualem, brooks_corey + burdine.",
    "Также доступны пары van_genuchten + tabular, brooks_corey + tabular и tabular + tabular, если для расчета сохранены нужные табличные кривые.",
    "Corey и Gardner показаны как варианты развития, но пока не включены в расчётный запуск."
  ].join(" ");
}

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

function emptyCurvePoint(pointIndex: number): SoilCurvePoint {
  return {
    point_index: pointIndex,
    pressure_head_m: null,
    pressure_pa: null,
    water_content: null,
    saturation: null,
    relative_permeability: null,
    hydraulic_conductivity_m_s: null,
    comment: ""
  };
}

function emptySoilCurveDraft(): SoilCurveTableCreate {
  return {
    curve_name: "lab_retention",
    curve_kind: "retention",
    retention_model: "tabular",
    conductivity_model: null,
    pressure_unit: "м",
    saturation_unit: "м3/м3",
    conductivity_unit: "м/с",
    comment: "",
    points: [emptyCurvePoint(0), emptyCurvePoint(1)]
  };
}

function numericOrNull(value: string): number | null {
  return value === "" ? null : Number(value);
}

function finiteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function numericFieldValue(workbook: InputWorkbook | null, key: string, fallback: number): number {
  const rawValue = fieldByKey(workbook, key)?.value;
  return typeof rawValue === "number" && Number.isFinite(rawValue) ? rawValue : fallback;
}

function curveRequiresRetention(curveKind: string): boolean {
  return curveKind === "retention" || curveKind === "retention_conductivity";
}

function curveRequiresConductivity(curveKind: string): boolean {
  return curveKind === "conductivity" || curveKind === "retention_conductivity";
}

function normalizedCurvePoint(point: SoilCurvePoint, thetaS: number, ksatMS: number) {
  const saturation = finiteNumber(point.saturation) ? point.saturation : finiteNumber(point.water_content) && thetaS > 0 ? point.water_content / thetaS : null;
  const capillaryPressurePa = finiteNumber(point.pressure_pa) ? Math.max(0, point.pressure_pa) : finiteNumber(point.pressure_head_m) ? Math.max(0, -1000 * 9.80665 * point.pressure_head_m) : null;
  const relativePermeability = finiteNumber(point.relative_permeability)
    ? point.relative_permeability
    : finiteNumber(point.hydraulic_conductivity_m_s) && ksatMS > 0
      ? point.hydraulic_conductivity_m_s / ksatMS
      : null;
  return { saturation, capillaryPressurePa, relativePermeability };
}

function sortedPreviewRows(points: SoilCurvePoint[], workbook: InputWorkbook | null) {
  const thetaS = numericFieldValue(workbook, "theta_s", 0.43);
  const ksatMS = numericFieldValue(workbook, "ksat_m_s", 1e-5);
  return points
    .map((point) => normalizedCurvePoint(point, thetaS, ksatMS))
    .filter((point) => finiteNumber(point.saturation))
    .sort((left, right) => Number(left.saturation) - Number(right.saturation));
}

function isMonotonic(values: number[]): boolean {
  if (values.length < 2) {
    return true;
  }
  const nondecreasing = values.every((value, index) => index === 0 || value >= values[index - 1]);
  const nonincreasing = values.every((value, index) => index === 0 || value <= values[index - 1]);
  return nondecreasing || nonincreasing;
}

function soilCurveValidationMessage(draft: SoilCurveTableCreate, workbook: InputWorkbook | null): string {
  const rows = sortedPreviewRows(draft.points, workbook);
  if (rows.length < 2) {
    return "Для табличной кривой нужны минимум две точки с насыщенностью S или влажностью θ.";
  }
  if (rows.some((row) => Number(row.saturation) < 0 || Number(row.saturation) > 1)) {
    return "Насыщенность S должна быть в диапазоне от 0 до 1.";
  }
  if (rows.some((row, index) => index > 0 && Number(row.saturation) <= Number(rows[index - 1].saturation))) {
    return "Значения насыщенности S не должны повторяться.";
  }
  if (curveRequiresRetention(draft.curve_kind)) {
    const pressures = rows.map((row) => row.capillaryPressurePa);
    if (pressures.some((value) => !finiteNumber(value))) {
      return "Для кривой водоудерживания заполните P, Па или h, м для каждой точки.";
    }
    if (!isMonotonic(pressures as number[])) {
      return "Капиллярное давление Pc(S) должно быть монотонным.";
    }
  }
  if (curveRequiresConductivity(draft.curve_kind)) {
    const relativePermeabilities = rows.map((row) => row.relativePermeability);
    if (relativePermeabilities.some((value) => !finiteNumber(value))) {
      return "Для кривой влагопроводности заполните kr или K, м/с для каждой точки.";
    }
    if (relativePermeabilities.some((value) => Number(value) < 0 || Number(value) > 1)) {
      return "Относительная проницаемость kr должна быть в диапазоне от 0 до 1.";
    }
    if (!isMonotonic(relativePermeabilities as number[])) {
      return "Кривая kr(S) должна быть монотонной.";
    }
  }
  return "";
}

function CurvePreview({ title, rows, valueKey, unit }: { title: string; rows: ReturnType<typeof sortedPreviewRows>; valueKey: "capillaryPressurePa" | "relativePermeability"; unit: string }) {
  const points = rows.filter((row) => finiteNumber(row[valueKey]));
  if (points.length < 2) {
    return null;
  }
  const width = 320;
  const height = 180;
  const padding = 28;
  const values = points.map((point) => Number(point[valueKey]));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const spanValue = maxValue - minValue || 1;
  const polyline = points
    .map((point) => {
      const x = padding + Number(point.saturation) * (width - 2 * padding);
      const y = height - padding - ((Number(point[valueKey]) - minValue) / spanValue) * (height - 2 * padding);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="curve-preview-card">
      <strong>{title}</strong>
      <svg className="curve-preview-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <line className="curve-axis" x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
        <line className="curve-axis" x1={padding} y1={padding} x2={padding} y2={height - padding} />
        <polyline className="curve-line" points={polyline} />
        {points.map((point, index) => {
          const x = padding + Number(point.saturation) * (width - 2 * padding);
          const y = height - padding - ((Number(point[valueKey]) - minValue) / spanValue) * (height - 2 * padding);
          return <circle key={`${title}:${index}`} className="curve-point" cx={x} cy={y} r="3" />;
        })}
        <text x={width / 2} y={height - 6} textAnchor="middle">S</text>
        <text x={8} y={16}>{unit}</text>
      </svg>
    </div>
  );
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
  const [soilCurves, setSoilCurves] = useState<SoilCurveTable[]>([]);
  const [soilCurveDraft, setSoilCurveDraft] = useState<SoilCurveTableCreate>(() => emptySoilCurveDraft());

  const activeTab = useMemo(() => workbook?.tabs.find((tab) => tab.id === activeTabId) ?? workbook?.tabs[0] ?? null, [workbook, activeTabId]);
  const soilModelError = useMemo(() => soilModelValidationMessage(workbook), [workbook]);
  const soilCurveError = useMemo(() => soilCurveValidationMessage(soilCurveDraft, workbook), [soilCurveDraft, workbook]);
  const soilCurvePreviewRows = useMemo(() => sortedPreviewRows(soilCurveDraft.points, workbook), [soilCurveDraft.points, workbook]);

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
      await refreshSoilCurves(next.calculation_id);
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

  async function refreshSoilCurves(calculationId = workbook?.calculation_id ?? null) {
    if (!calculationId) {
      setSoilCurves([]);
      return;
    }
    try {
      setSoilCurves(await listSoilCurves(calculationId));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось прочитать табличные кривые");
    }
  }

  function replaceTab(nextTab: InputTab) {
    setWorkbook((current) => (current ? { ...current, tabs: current.tabs.map((tab) => (tab.id === nextTab.id ? nextTab : tab)) } : current));
  }

  async function save() {
    if (!workbook) {
      return;
    }
    if (soilModelError) {
      setError(soilModelError);
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const saved = await saveInputWorkbook(workbook);
      setWorkbook(saved);
      setCalculationIdInLocation(saved.calculation_id);
      await refreshCalculations();
      await refreshSoilCurves(saved.calculation_id);
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
      setSoilCurves([]);
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
      await refreshSoilCurves(calculationId);
      setMessage(`${calculation.title} загружен из базы без пересчета.`);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить расчет");
    } finally {
      setSaving(false);
    }
  }

  function updateCurveDraft(patch: Partial<SoilCurveTableCreate>) {
    setSoilCurveDraft((current) => ({ ...current, ...patch }));
  }

  function updateCurvePoint(index: number, patch: Partial<SoilCurvePoint>) {
    setSoilCurveDraft((current) => ({
      ...current,
      points: current.points.map((point, pointIndex) => (pointIndex === index ? { ...point, ...patch } : point))
    }));
  }

  async function saveSoilCurve() {
    if (!workbook?.calculation_id) {
      setError("Сначала сохраните расчет в базу данных проекта.");
      return;
    }
    if (soilCurveError) {
      setError(soilCurveError);
      return;
    }
    try {
      await createSoilCurve(workbook.calculation_id, soilCurveDraft);
      setSoilCurveDraft(emptySoilCurveDraft());
      await refreshSoilCurves(workbook.calculation_id);
      setMessage("Табличная кривая сохранена в базе данных расчета.");
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось сохранить табличную кривую");
    }
  }

  async function removeSoilCurve(tableId: number) {
    if (!window.confirm("Удалить табличную кривую из расчета?")) {
      return;
    }
    try {
      await deleteSoilCurve(tableId);
      await refreshSoilCurves();
      setMessage("Табличная кривая удалена.");
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось удалить табличную кривую");
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
          <button className="primary" type="button" onClick={save} disabled={!workbook || saving || Boolean(soilModelError)}>
            {saving ? "Сохранение..." : "Сохранить"}
          </button>
        </div>
      </div>
      <ErrorNotice message={error} />
      <ErrorNotice message={soilModelError} />
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
          <div className="panel soil-curves-panel">
            <div className="panel-header">
              <h2>Табличные кривые почвы</h2>
              <div className="toolbar compact-toolbar">
                <button type="button" onClick={() => refreshSoilCurves()} disabled={!workbook.calculation_id}>
                  Обновить
                </button>
                <button type="button" onClick={saveSoilCurve} disabled={!workbook.calculation_id || Boolean(soilCurveError)}>
                  Сохранить кривую
                </button>
              </div>
            </div>
            {!workbook.calculation_id && <p className="muted">Сначала сохраните расчет. После этого табличные экспериментальные кривые будут записываться в SQLite как часть расчета.</p>}
            {workbook.calculation_id && (
              <>
                <div className="curve-draft-grid">
                  <label>
                    <span>Имя кривой</span>
                    <input value={soilCurveDraft.curve_name} onChange={(event) => updateCurveDraft({ curve_name: event.target.value })} />
                  </label>
                  <label>
                    <span>Тип</span>
                    <select value={soilCurveDraft.curve_kind} onChange={(event) => updateCurveDraft({ curve_kind: event.target.value })}>
                      <option value="retention">Водоудерживание</option>
                      <option value="conductivity">Влагопроводность</option>
                      <option value="retention_conductivity">Водоудерживание + влагопроводность</option>
                    </select>
                  </label>
                  <label>
                    <span>Модель</span>
                    <input value={soilCurveDraft.retention_model ?? ""} onChange={(event) => updateCurveDraft({ retention_model: event.target.value || null })} />
                  </label>
                  <label>
                    <span>Комментарий</span>
                    <input value={soilCurveDraft.comment ?? ""} onChange={(event) => updateCurveDraft({ comment: event.target.value })} />
                  </label>
                </div>
                <div className="weather-editor curve-editor">
                  <table>
                    <thead>
                      <tr>
                        <th>№</th>
                        <th>h, м</th>
                        <th>P, Па</th>
                        <th>θ, м3/м3</th>
                        <th>S</th>
                        <th>kr</th>
                        <th>K, м/с</th>
                        <th>Комментарий</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {soilCurveDraft.points.map((point, index) => (
                        <tr key={index}>
                          <td>{index + 1}</td>
                          <td><input type="number" step="any" value={point.pressure_head_m ?? ""} onChange={(event) => updateCurvePoint(index, { pressure_head_m: numericOrNull(event.target.value) })} /></td>
                          <td><input type="number" step="any" value={point.pressure_pa ?? ""} onChange={(event) => updateCurvePoint(index, { pressure_pa: numericOrNull(event.target.value) })} /></td>
                          <td><input type="number" step="any" value={point.water_content ?? ""} onChange={(event) => updateCurvePoint(index, { water_content: numericOrNull(event.target.value) })} /></td>
                          <td><input type="number" step="any" value={point.saturation ?? ""} onChange={(event) => updateCurvePoint(index, { saturation: numericOrNull(event.target.value) })} /></td>
                          <td><input type="number" step="any" value={point.relative_permeability ?? ""} onChange={(event) => updateCurvePoint(index, { relative_permeability: numericOrNull(event.target.value) })} /></td>
                          <td><input type="number" step="any" value={point.hydraulic_conductivity_m_s ?? ""} onChange={(event) => updateCurvePoint(index, { hydraulic_conductivity_m_s: numericOrNull(event.target.value) })} /></td>
                          <td><input value={point.comment ?? ""} onChange={(event) => updateCurvePoint(index, { comment: event.target.value })} /></td>
                          <td>
                            <button type="button" onClick={() => updateCurveDraft({ points: soilCurveDraft.points.filter((_, pointIndex) => pointIndex !== index).map((item, pointIndex) => ({ ...item, point_index: pointIndex })) })}>
                              Удалить
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <button type="button" onClick={() => updateCurveDraft({ points: [...soilCurveDraft.points, emptyCurvePoint(soilCurveDraft.points.length)] })}>
                    Добавить точку
                  </button>
                </div>
                {soilCurveError && <p className="inline-error">{soilCurveError}</p>}
                <div className="curve-preview-grid">
                  {curveRequiresRetention(soilCurveDraft.curve_kind) && <CurvePreview title="Pc(S)" rows={soilCurvePreviewRows} valueKey="capillaryPressurePa" unit="Па" />}
                  {curveRequiresConductivity(soilCurveDraft.curve_kind) && <CurvePreview title="kr(S)" rows={soilCurvePreviewRows} valueKey="relativePermeability" unit="kr" />}
                </div>
                <div className="curve-list">
                  {soilCurves.length === 0 && <p className="muted">Для этого расчета табличные кривые пока не сохранены.</p>}
                  {soilCurves.map((curve) => (
                    <div className="curve-card" key={curve.id}>
                      <div>
                        <strong>{curve.curve_name}</strong>
                        <small>{curve.curve_kind}, точек: {curve.points.length}</small>
                      </div>
                      <button type="button" onClick={() => removeSoilCurve(curve.id)}>
                        Удалить
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
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
                  ) : field.key === "retention_model" || field.key === "conductivity_model" ? (
                    <select value={String(field.value ?? "")} onChange={(event) => replaceTab(updateField(activeTab, field.key, event.target.value))}>
                      {(field.key === "retention_model" ? retentionOptions : conductivityOptions).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
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
