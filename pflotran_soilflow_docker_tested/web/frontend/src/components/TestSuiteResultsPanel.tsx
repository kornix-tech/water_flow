import { useMemo, useState } from "react";
import type { TestSuiteResult, TestSuiteStatus } from "../types";
import { statusLabel } from "./StatusSummaryPanel";

function metricText(result: TestSuiteResult, key: string): string {
  const value = result.metrics[key];
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function failureStage(result: TestSuiteResult): string {
  return metricText(result, "failure_stage");
}

function strictStage(result: TestSuiteResult): string {
  return metricText(result, "strict_readiness_stage");
}

function gateStatus(result: TestSuiteResult): string {
  const value = result.metrics.strict_candidate_can_gate_suite;
  if (value === true || value === "true") {
    return "yes";
  }
  if (value === false || value === "false") {
    return "no";
  }
  return "-";
}

function uniqueValues(results: TestSuiteResult[], selector: (result: TestSuiteResult) => string): string[] {
  return Array.from(new Set(results.map(selector).filter((value) => value !== "-"))).sort();
}

export function TestSuiteResultsPanel({ suite }: { suite: TestSuiteStatus | null }) {
  const [statusFilter, setStatusFilter] = useState("all");
  const [failureStageFilter, setFailureStageFilter] = useState("all");
  const [strictStageFilter, setStrictStageFilter] = useState("all");
  const [gateFilter, setGateFilter] = useState("all");

  const results = suite?.results ?? [];
  const statusOptions = useMemo(() => uniqueValues(results, (result) => result.status), [results]);
  const failureStageOptions = useMemo(() => uniqueValues(results, failureStage), [results]);
  const strictStageOptions = useMemo(() => uniqueValues(results, strictStage), [results]);
  const gateOptions = useMemo(() => uniqueValues(results, gateStatus), [results]);
  const filteredResults = results.filter((result) => {
    if (statusFilter !== "all" && result.status !== statusFilter) {
      return false;
    }
    if (failureStageFilter !== "all" && failureStage(result) !== failureStageFilter) {
      return false;
    }
    if (strictStageFilter !== "all" && strictStage(result) !== strictStageFilter) {
      return false;
    }
    if (gateFilter !== "all" && gateStatus(result) !== gateFilter) {
      return false;
    }
    return true;
  });

  if (!suite) {
    return null;
  }

  return (
    <section className="suite-results-panel">
      <div className="suite-summary-header">
        <h3>Результаты verification-suite</h3>
        <span className={`status-pill status-pill-${suite.status.toLowerCase().replace(/_/g, "-")}`}>{statusLabel(suite.status)}</span>
      </div>
      <div className="suite-result-filters">
        <label>
          Статус
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">Все</option>
            {statusOptions.map((status) => (
              <option value={status} key={status}>
                {statusLabel(status)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Failure stage
          <select value={failureStageFilter} onChange={(event) => setFailureStageFilter(event.target.value)}>
            <option value="all">Все</option>
            {failureStageOptions.map((stage) => (
              <option value={stage} key={stage}>
                {stage}
              </option>
            ))}
          </select>
        </label>
        <label>
          Strict stage
          <select value={strictStageFilter} onChange={(event) => setStrictStageFilter(event.target.value)}>
            <option value="all">Все</option>
            {strictStageOptions.map((stage) => (
              <option value={stage} key={stage}>
                {stage}
              </option>
            ))}
          </select>
        </label>
        <label>
          Gate
          <select value={gateFilter} onChange={(event) => setGateFilter(event.target.value)}>
            <option value="all">Все</option>
            {gateOptions.map((value) => (
              <option value={value} key={value}>
                {value === "yes" ? "Допущен" : "Не допущен"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="suite-results-table-wrap">
        <table className="suite-results-table">
          <thead>
            <tr>
              <th>Тест</th>
              <th>Статус</th>
              <th>Уровень</th>
              <th>Failure stage</th>
              <th>Strict stage</th>
              <th>Gate</th>
              <th>Warnings</th>
              <th>Solver</th>
            </tr>
          </thead>
          <tbody>
            {filteredResults.map((result) => (
              <tr key={result.test_id}>
                <td className="mono">{result.test_id}</td>
                <td>{statusLabel(result.status)}</td>
                <td>{result.verification_level ?? "-"}</td>
                <td>{failureStage(result)}</td>
                <td>{strictStage(result)}</td>
                <td>{gateStatus(result) === "yes" ? "допущен" : gateStatus(result) === "no" ? "нет" : "-"}</td>
                <td>{metricText(result, "warning_count")}</td>
                <td>{metricText(result, "solver_timed_out") === "true" ? "timeout" : metricText(result, "solver_error_count")}</td>
              </tr>
            ))}
            {filteredResults.length === 0 && (
              <tr>
                <td colSpan={8}>Нет результатов под выбранные фильтры.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
