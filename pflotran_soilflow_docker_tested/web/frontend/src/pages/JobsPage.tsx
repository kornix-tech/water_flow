import { useEffect, useState } from "react";
import { cancelJob, getJobLog, listJobs } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { JobStatusBadge } from "../components/JobStatusBadge";
import { LogViewer } from "../components/LogViewer";
import { StatusSummaryPanel } from "../components/StatusSummaryPanel";
import { jobTimingLabel } from "../jobTiming";
import { jobKindLabel } from "../labels";
import type { JobRead, StatusSummaryItem } from "../types";

function selectedJobSummary(job: JobRead | null, jobs: JobRead[]): StatusSummaryItem[] {
  if (!job) {
    return [];
  }
  return [
    {
      kind: "job",
      title: "Задание",
      status: job.status,
      subtitle: job.run_name ?? job.id,
      source: "SQLite jobs",
      files: job.log_path ? [job.log_path] : [],
      messages: job.error_message ? [job.error_message] : [],
      metrics: [
        { label: "Тип", value: jobKindLabel(job.kind) },
        { label: "Оценка", value: jobTimingLabel(job, jobs) },
        { label: "Создано", value: new Date(job.created_at).toLocaleString() },
        { label: "Старт", value: job.started_at ? new Date(job.started_at).toLocaleString() : "-" },
        { label: "Финиш", value: job.finished_at ? new Date(job.finished_at).toLocaleString() : "-" },
        { label: "Код выхода", value: job.exit_code === null ? "-" : String(job.exit_code) },
      ],
    },
  ];
}

export function JobsPage() {
  const [jobs, setJobs] = useState<JobRead[]>([]);
  const [selected, setSelected] = useState<JobRead | null>(null);
  const [log, setLog] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const next = await listJobs();
      setJobs(next);
      if (selected) {
        const updated = next.find((job) => job.id === selected.id) ?? selected;
        setSelected(updated);
        setLog(await getJobLog(updated.id));
      }
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось обновить список заданий");
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => window.clearInterval(timer);
  }, [selected?.id]);

  async function selectJob(job: JobRead) {
    setSelected(job);
    try {
      setLog(await getJobLog(job.id));
      setError("");
    } catch (caught) {
      setLog("");
      setError(caught instanceof Error ? caught.message : "Не удалось прочитать лог задания");
    }
  }

  async function cancelSelected() {
    if (!selected) {
      return;
    }
    try {
      await cancelJob(selected.id);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось отменить задание");
    }
  }

  return (
    <section>
      <div className="page-title">
        <h1>Статус</h1>
        <button type="button" onClick={refresh}>
          Обновить
        </button>
      </div>
      <ErrorNotice message={error} />
      <div className="split">
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Статус</th>
                <th>Тип</th>
                <th>Расчёт</th>
                <th>Создано</th>
                <th>Оценка</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className={selected?.id === job.id ? "selected" : ""} onClick={() => selectJob(job)}>
                  <td>
                    <JobStatusBadge status={job.status} />
                  </td>
                  <td>{jobKindLabel(job.kind)}</td>
                  <td>{job.run_name ?? "-"}</td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>{jobTimingLabel(job, jobs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <div className="panel-header">
            <h2>Лог</h2>
            <button type="button" disabled={!selected || selected.status !== "running"} onClick={cancelSelected}>
              Отменить
            </button>
          </div>
          <StatusSummaryPanel title="Сводка состояния" items={selectedJobSummary(selected, jobs)} emptyText="Выберите задание слева." />
          <LogViewer text={log} />
        </div>
      </div>
    </section>
  );
}
