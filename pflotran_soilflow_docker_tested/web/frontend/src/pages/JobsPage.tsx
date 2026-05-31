import { useEffect, useState } from "react";
import { cancelJob, getJobLog, listJobs } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { JobStatusBadge } from "../components/JobStatusBadge";
import { LogViewer } from "../components/LogViewer";
import { jobTimingLabel } from "../jobTiming";
import { jobKindLabel } from "../labels";
import type { JobRead } from "../types";

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
          {selected && (
            <dl className="kv compact">
              <dt>Задание</dt>
              <dd className="mono">{selected.id}</dd>
              <dt>Код</dt>
              <dd>{selected.exit_code ?? "-"}</dd>
            </dl>
          )}
          <LogViewer text={log} />
        </div>
      </div>
    </section>
  );
}
