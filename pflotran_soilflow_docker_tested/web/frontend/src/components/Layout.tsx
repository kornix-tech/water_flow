import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { listJobs } from "../api/client";
import { jobKindLabel } from "../labels";
import { FINISHED_JOB_STATUSES, jobTimingLabel } from "../jobTiming";
import { ROUTES } from "../routes";
import type { JobRead } from "../types";

const navItems = [
  [ROUTES.dashboard, "Обзор"],
  [ROUTES.inputs, "Исходные данные"],
  [ROUTES.jobs, "Статус"],
  [ROUTES.tests, "Тесты"],
  [ROUTES.results, "Расчеты"],
  [ROUTES.visualization, "Графики"],
  [ROUTES.system, "Система"]
];

interface LayoutProps {
  path: string;
  onNavigate: (path: string) => void;
  onLogout: () => void;
  children: ReactNode;
}

function TaskProgressPanel({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [jobs, setJobs] = useState<JobRead[]>([]);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const next = await listJobs();
      setJobs(next);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "нет связи");
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => window.clearInterval(timer);
  }, []);

  const activeJob = jobs.find((job) => job.status === "running") ?? jobs.find((job) => job.status === "queued") ?? null;
  const progress = useMemo(() => {
    if (!jobs.length) {
      return 0;
    }
    const finished = jobs.filter((job) => FINISHED_JOB_STATUSES.has(job.status)).length;
    return Math.round((finished / jobs.length) * 100);
  }, [jobs]);
  const finishedCount = jobs.filter((job) => FINISHED_JOB_STATUSES.has(job.status)).length;

  return (
    <section
      className="task-progress"
      aria-label="Прогресс задач"
      role="button"
      tabIndex={0}
      onClick={() => onNavigate(ROUTES.jobs)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onNavigate(ROUTES.jobs);
        }
      }}
    >
      <div className="task-progress-title">
        <span>Задачи</span>
        <strong>{jobs.length ? `${finishedCount}/${jobs.length}` : "0/0"}</strong>
      </div>
      <div className="progress-track" aria-label="Общий прогресс задач">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      {activeJob ? (
        <div className="active-task">
          <span>{jobKindLabel(activeJob.kind)}</span>
          <small>{jobTimingLabel(activeJob, jobs)}</small>
          <div className={`progress-track active ${activeJob.status === "running" ? "indeterminate" : ""}`}>
            <div className="progress-fill" />
          </div>
        </div>
      ) : (
        <div className="active-task idle">
          <span>Активных задач нет</span>
          <small>{error || "ожидание запуска"}</small>
        </div>
      )}
    </section>
  );
}

export function Layout({ path, onNavigate, onLogout, children }: LayoutProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>Влагоперенос в почве</strong>
          <span>PFLOTRAN</span>
        </div>
        <nav>
          {navItems.map(([href, label]) => (
            <button
              type="button"
              key={href}
              className={path === href ? "nav-active" : ""}
              onClick={() => onNavigate(href)}
            >
              {label}
            </button>
          ))}
        </nav>
        <TaskProgressPanel onNavigate={onNavigate} />
        <button className="session-button" type="button" onClick={onLogout}>
          Сменить токен
        </button>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
