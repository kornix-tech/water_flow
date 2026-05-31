import { useState } from "react";
import { runTest, runTestSuite } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { JobStatusBadge } from "../components/JobStatusBadge";
import { ROUTES } from "../routes";
import type { JobCreated } from "../types";

const tests = [
  ["all", "Запустить все тесты"],
  ["linear_darcy", "Линейный Darcy"],
  ["hydrostatic_vg_no_flow", "Гидростатика VG"],
  ["unit_gradient_unsat", "Единичный градиент"],
  ["transient_uniform_storage_vg", "Нестационарное хранение"]
];

export function TestsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [lastJob, setLastJob] = useState<JobCreated | null>(null);
  const [error, setError] = useState("");

  async function start(testName: string) {
    setError("");
    try {
      const job = testName === "all" ? await runTestSuite() : await runTest(testName);
      setLastJob(job);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось поставить тест в очередь");
    }
  }

  return (
    <section>
      <div className="page-title">
        <h1>Тесты</h1>
        <button type="button" onClick={() => onNavigate(ROUTES.jobs)}>
          Открыть статус
        </button>
      </div>
      <ErrorNotice message={error} />
      <div className="panel">
        <div className="button-grid">
          {tests.map(([testName, label]) => (
            <button className="primary" type="button" key={testName} onClick={() => start(testName)}>
              {label}
            </button>
          ))}
        </div>
        {lastJob && (
          <div className="notice">
            задание: <span className="mono">{lastJob.job_id}</span>, <JobStatusBadge status={lastJob.status} />
          </div>
        )}
      </div>
    </section>
  );
}
