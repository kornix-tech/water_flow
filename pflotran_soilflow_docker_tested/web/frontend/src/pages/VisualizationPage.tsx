import { useEffect, useState } from "react";
import { getRunFiles, listRuns, runVisualization } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { PlotFrame } from "../components/PlotFrame";
import type { RunInfo } from "../types";

const RUNS_REFRESH_MS = 5000;
const PLOT_FILES_REFRESH_MS = 5000;

function runNameFromLocation(): string {
  return new URLSearchParams(window.location.search).get("run")?.trim() ?? "";
}

function setRunNameInLocation(runName: string): void {
  const nextUrl = new URL(window.location.href);
  if (runName) {
    nextUrl.searchParams.set("run", runName);
  } else {
    nextUrl.searchParams.delete("run");
  }
  window.history.replaceState({}, "", `${nextUrl.pathname}${nextUrl.search}`);
}

export function VisualizationPage() {
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [runName, setRunNameState] = useState(runNameFromLocation);
  const [plotFiles, setPlotFiles] = useState<string[]>([]);
  const [plotFilesLoading, setPlotFilesLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function setRunName(nextRunName: string) {
    setRunNameState(nextRunName);
    setRunNameInLocation(nextRunName);
  }

  async function refreshRuns() {
    try {
      const next = await listRuns();
      setRuns(next);
      const requestedRunName = runNameFromLocation();
      const currentRunName = requestedRunName || runName;
      if (next.length && (!currentRunName || !next.some((run) => run.run_name === currentRunName))) {
        setRunName((next.find((run) => run.has_visualization) ?? next[0]).run_name);
      } else if (requestedRunName && requestedRunName !== runName) {
        setRunNameState(requestedRunName);
      }
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось получить список расчётов");
    }
  }

  useEffect(() => {
    refreshRuns();
    const timer = window.setInterval(refreshRuns, RUNS_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [runName]);

  const selectedRun = runs.find((run) => run.run_name === runName) ?? null;

  useEffect(() => {
    if (!runName || !selectedRun?.has_visualization) {
      setPlotFiles([]);
      setPlotFilesLoading(false);
      return;
    }
    let cancelled = false;
    async function refreshPlotFiles() {
      try {
        setPlotFilesLoading(true);
        const files = await getRunFiles(runName);
        if (!cancelled) {
          setPlotFiles(files);
          setError("");
        }
      } catch (caught) {
        if (!cancelled) {
          setPlotFiles([]);
          setError(caught instanceof Error ? caught.message : "Не удалось прочитать файлы графиков");
        }
      } finally {
        if (!cancelled) {
          setPlotFilesLoading(false);
        }
      }
    }
    refreshPlotFiles();
    const timer = window.setInterval(refreshPlotFiles, PLOT_FILES_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runName, selectedRun?.has_visualization]);

  async function generate() {
    setError("");
    try {
      const job = await runVisualization(runName);
      setMessage(`задание визуализации: ${job.job_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось поставить визуализацию в очередь");
    }
  }

  return (
    <section>
      <div className="page-title">
        <h1>Графики</h1>
        <button type="button" onClick={refreshRuns}>
          Обновить
        </button>
      </div>
      <ErrorNotice message={error} />
      <div className="toolbar">
        <select value={runName} onChange={(event) => setRunName(event.target.value)}>
          {runs.map((run) => (
            <option key={run.run_name} value={run.run_name}>
              {run.has_visualization ? run.run_name : `${run.run_name} (графики не построены)`}
            </option>
          ))}
        </select>
        <button className="primary" type="button" disabled={!runName} onClick={generate}>
          Построить графики
        </button>
        {message && <span className="notice">{message}</span>}
      </div>
      <div className="plot-layout">
        {selectedRun?.has_visualization ? (
          <PlotFrame runName={runName} />
        ) : (
          <div className="empty-panel">Для выбранного расчёта графики ещё не построены.</div>
        )}
        <div className="panel">
          <h2>Файлы графиков</h2>
          {plotFilesLoading && !plotFiles.length ? (
            <p className="muted">Файлы графиков загружаются.</p>
          ) : (
            <ul className="file-list dense">
              {plotFiles.map((file) => (
                <li key={file}>{file}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
