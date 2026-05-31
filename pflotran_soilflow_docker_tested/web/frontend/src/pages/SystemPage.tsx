import React from "react";
import { useEffect, useState } from "react";
import { getSystemInfo } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { systemValueLabel } from "../labels";
import type { SystemInfo } from "../types";

const SYSTEM_LABELS: Record<string, string> = {
  soilflow_home: "Каталог приложения",
  workspace: "Рабочая область",
  pflotran_exe: "PFLOTRAN",
  pflotran_exists: "PFLOTRAN найден",
  job_workers: "Потоки заданий",
  auth_mode: "Авторизация",
  frontend_available: "Frontend собран",
  api_docs_enabled: "API-документация",
  hsts_enabled: "HSTS",
  api_rate_limit_per_minute: "Лимит API в минуту"
};

export function SystemPage() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getSystemInfo()
      .then((nextInfo) => {
        setInfo(nextInfo);
        setError("");
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Не удалось получить сведения о системе");
      });
  }, []);

  return (
    <section>
      <div className="page-title">
        <h1>Система</h1>
      </div>
      <ErrorNotice message={error} />
      <div className="panel">
        <dl className="kv">
          {info &&
            Object.entries(info).map(([key, value]) => {
              const label = systemValueLabel(key, value);
              return (
                <React.Fragment key={key}>
                  <dt>{SYSTEM_LABELS[key] ?? key}</dt>
                  <dd className={label.includes("/") ? "mono" : ""}>{label}</dd>
                </React.Fragment>
              );
            })}
        </dl>
      </div>
    </section>
  );
}
