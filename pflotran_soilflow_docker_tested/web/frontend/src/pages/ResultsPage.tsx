import { useEffect, useState } from "react";
import { deleteCalculation, downloadRunZip, getCalculation, getRunStatusOverview, getRunTestSuiteStatus, listCalculations, listRuns, runCalculation } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { ResultFileList } from "../components/ResultFileList";
import { StatusSummaryPanel } from "../components/StatusSummaryPanel";
import { TestSuiteResultsPanel } from "../components/TestSuiteResultsPanel";
import { ROUTES } from "../routes";
import type { CalculationSummary, RunInfo, RunStatusOverview, TestSuiteStatus } from "../types";

interface ResultsPageProps {
  onNavigate: (path: string) => void;
}

export function ResultsPage({ onNavigate }: ResultsPageProps) {
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [calculations, setCalculations] = useState<CalculationSummary[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<RunInfo | null>(null);
  const [selectedCalculation, setSelectedCalculation] = useState<CalculationSummary | null>(null);
  const [selectedStandaloneRunName, setSelectedStandaloneRunName] = useState<string | null>(null);
  const [statusOverview, setStatusOverview] = useState<RunStatusOverview | null>(null);
  const [statusOverviewError, setStatusOverviewError] = useState("");
  const [testSuiteStatus, setTestSuiteStatus] = useState<TestSuiteStatus | null>(null);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const [next, calculationList] = await Promise.all([listRuns(), listCalculations(query)]);
      setRuns(next);
      setCalculations(calculationList);
      const standaloneRun = selectedStandaloneRunName ? next.find((run) => run.run_name === selectedStandaloneRunName) ?? null : null;
      if (standaloneRun) {
        setSelectedCalculation(null);
        setSelected(standaloneRun);
        setError("");
        return;
      }
      if (selectedStandaloneRunName) {
        setSelectedStandaloneRunName(null);
      }
      const nextCalculation = calculationList.find((calculation) => calculation.id === selectedCalculation?.id) ?? calculationList[0] ?? null;
      setSelectedCalculation(nextCalculation);
      setSelected((current) => {
        if (nextCalculation?.run_name) {
          return next.find((run) => run.run_name === nextCalculation.run_name) ?? null;
        }
        return next.find((run) => run.run_name === current?.run_name) ?? next[0] ?? null;
      });
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось прочитать результаты");
    }
  }

  async function refreshSearch() {
    try {
      const calculationList = await listCalculations(query);
      setCalculations(calculationList);
      setSelectedCalculation(calculationList[0] ?? null);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось найти расчеты");
    }
  }

  async function selectCalculation(calculation: CalculationSummary) {
    setSelectedStandaloneRunName(null);
    setSelectedCalculation(calculation);
    if (calculation.run_name) {
      setSelected(runs.find((run) => run.run_name === calculation.run_name) ?? null);
    } else {
      setSelected(null);
    }
    try {
      await getCalculation(calculation.id);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось открыть расчет");
    }
  }

  function selectStandaloneRun(run: RunInfo) {
    setSelectedStandaloneRunName(run.run_name);
    setSelectedCalculation(null);
    setSelected(run);
  }

  function openCalculationGraphs(calculation: CalculationSummary) {
    if (!calculation.run_name) {
      selectCalculation(calculation);
      return;
    }
    onNavigate(`${ROUTES.visualization}?run=${encodeURIComponent(calculation.run_name)}`);
  }

  async function startSelectedCalculation() {
    if (!selectedCalculation) {
      return;
    }
    try {
      await runCalculation(selectedCalculation.id);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось запустить расчет");
    }
  }

  function openSelectedCalculationInputs() {
    if (!selectedCalculation) {
      return;
    }
    onNavigate(`${ROUTES.inputs}?calculation_id=${selectedCalculation.id}`);
  }

  async function deleteSelectedCalculation() {
    if (!selectedCalculation) {
      return;
    }
    if (!window.confirm(`Удалить ${selectedCalculation.title}? Запись расчета и его папка результатов будут удалены.`)) {
      return;
    }
    try {
      await deleteCalculation(selectedCalculation.id);
      setSelected(null);
      setSelectedCalculation(null);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось удалить расчет");
    }
  }

  async function downloadZip(runName: string) {
    try {
      await downloadRunZip(runName);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось скачать ZIP");
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => window.clearInterval(timer);
  }, [query, selectedCalculation?.id, selectedStandaloneRunName]);

  useEffect(() => {
    if (!selected) {
      setStatusOverview(null);
      setStatusOverviewError("");
      setTestSuiteStatus(null);
      return;
    }
    let cancelled = false;
    getRunStatusOverview(selected.run_name)
      .then((overview) => {
        if (!cancelled) {
          setStatusOverview(overview);
          setStatusOverviewError("");
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setStatusOverview(null);
          setStatusOverviewError(caught instanceof Error ? caught.message : "Не удалось прочитать сводку состояния");
        }
      });
    if (selected.has_suite_status) {
      getRunTestSuiteStatus(selected.run_name)
        .then((suite) => {
          if (!cancelled) {
            setTestSuiteStatus(suite);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setTestSuiteStatus(null);
          }
        });
    } else {
      setTestSuiteStatus(null);
    }
    return () => {
      cancelled = true;
    };
  }, [selected?.run_name, selected?.has_suite_status]);

  const calculationRunNames = new Set(calculations.map((calculation) => calculation.run_name).filter(Boolean));
  const standaloneRuns = runs.filter((run) => !calculationRunNames.has(run.run_name));

  return (
    <section>
      <div className="page-title">
        <h1>Расчеты</h1>
        <div className="toolbar compact-toolbar">
          <input
            type="search"
            placeholder="найти расчет"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                refreshSearch();
              }
            }}
          />
          <button type="button" onClick={refreshSearch}>
            Найти
          </button>
          <button type="button" onClick={refresh}>
            Обновить
          </button>
        </div>
      </div>
      <ErrorNotice message={error} />
      <div className="split">
        <div className="panel">
          <ul className="run-list">
            {calculations.map((calculation) => (
              <li key={calculation.id}>
                <button
                  type="button"
                  className={selectedCalculation?.id === calculation.id ? "selected-button" : ""}
                  data-calculation-id={calculation.id}
                  onClick={() => openCalculationGraphs(calculation)}
                >
                  <span>{calculation.title}</span>
                  <small>{new Date(calculation.created_at).toLocaleString()}</small>
                  <small>{calculation.has_results ? "результаты готовы" : "без результатов"}</small>
                </button>
              </li>
            ))}
            {standaloneRuns.length > 0 && <li className="run-list-heading">Тестовые запуски</li>}
            {standaloneRuns.map((run) => (
              <li key={run.run_name}>
                <button
                  type="button"
                  className={!selectedCalculation && selected?.run_name === run.run_name ? "selected-button" : ""}
                  data-run-name={run.run_name}
                  onClick={() => selectStandaloneRun(run)}
                >
                  <span>{run.run_name}</span>
                  <small>{run.has_suite_status ? "сводка тестов" : "папка результата"}</small>
                  <small>{run.has_visualization ? "графики готовы" : "без графиков"}</small>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="panel">
          {selected ? (
            <>
              <div className="panel-header">
                <h2>{selectedCalculation ? selectedCalculation.title : selected.run_name}</h2>
                <div className="toolbar compact-toolbar">
                  {selectedCalculation && (
                    <>
                      <button type="button" onClick={openSelectedCalculationInputs}>
                        Открыть исходные данные
                      </button>
                      <button type="button" onClick={startSelectedCalculation}>
                        Запустить заново
                      </button>
                      <button type="button" onClick={deleteSelectedCalculation}>
                        Удалить
                      </button>
                    </>
                  )}
                  {selected.has_visualization && (
                    <button type="button" onClick={() => onNavigate(`${ROUTES.visualization}?run=${encodeURIComponent(selected.run_name)}`)}>
                      Открыть графики
                    </button>
                  )}
                  <button type="button" onClick={() => downloadZip(selected.run_name)}>
                    Скачать ZIP
                  </button>
                </div>
              </div>
              {selectedCalculation && (
                <dl className="kv compact">
                  <dt>Папка</dt>
                  <dd className="mono">{selected.run_name}</dd>
                  <dt>Статус</dt>
                  <dd>{selectedCalculation.status}</dd>
                </dl>
              )}
              <StatusSummaryPanel title="Сводка состояния" items={statusOverview?.items ?? []} error={statusOverviewError} />
              <TestSuiteResultsPanel suite={testSuiteStatus} />
              <ResultFileList runName={selected.run_name} files={selected.files} />
            </>
          ) : (
            <div className="empty-panel">
              {selectedCalculation ? (
                <div className="toolbar">
                  <button type="button" onClick={openSelectedCalculationInputs}>
                    Открыть исходные данные
                  </button>
                  <button className="primary" type="button" onClick={startSelectedCalculation}>
                    Запустить выбранный расчет
                  </button>
                  <button type="button" onClick={deleteSelectedCalculation}>
                    Удалить
                  </button>
                </div>
              ) : (
                "Сохраненные расчеты не найдены."
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
