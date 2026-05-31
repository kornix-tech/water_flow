import { useEffect, useState } from "react";
import { getHealth, getSystemInfo, runDemo, runTestSuite } from "../api/client";
import { ErrorNotice } from "../components/ErrorNotice";
import { authModeLabel, healthStatusLabel } from "../labels";
import { ROUTES } from "../routes";
import type { HealthResponse, SystemInfo } from "../types";

interface DashboardPageProps {
  onNavigate: (path: string) => void;
  onJobCreated: () => void;
}

export function DashboardPage({ onNavigate, onJobCreated }: DashboardPageProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getHealth(), getSystemInfo()])
      .then(([nextHealth, nextSystem]) => {
        setHealth(nextHealth);
        setSystem(nextSystem);
        setError("");
      })
      .catch((caught) => {
        setHealth(null);
        setSystem(null);
        setError(caught instanceof Error ? caught.message : "Не удалось получить статус системы");
      });
  }, []);

  async function startDemo() {
    try {
      await runDemo();
      onJobCreated();
      onNavigate(ROUTES.jobs);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось запустить демо");
    }
  }

  async function startSuite() {
    try {
      await runTestSuite();
      onJobCreated();
      onNavigate(ROUTES.jobs);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось запустить набор тестов");
    }
  }

  return (
    <section>
      <div className="page-title">
        <h1>Обзор</h1>
        <span className="muted">состояние системы и быстрый запуск</span>
      </div>
      <ErrorNotice message={error} />
      <div className="grid two">
        <div className="panel">
          <h2>Сервер</h2>
          <dl className="kv">
            <dt>Статус</dt>
            <dd>{healthStatusLabel(health?.status)}</dd>
            <dt>Сервис</dt>
            <dd>{health?.service ?? "-"}</dd>
            <dt>Авторизация</dt>
            <dd>{authModeLabel(system?.auth_mode)}</dd>
          </dl>
        </div>
        <div className="panel">
          <h2>PFLOTRAN</h2>
          <dl className="kv">
            <dt>Исполняемый файл</dt>
            <dd>{system?.pflotran_exists ? "найден" : "не найден"}</dd>
            <dt>Рабочие потоки</dt>
            <dd>{system?.job_workers ?? "-"}</dd>
            <dt>Рабочая область</dt>
            <dd className="mono">{system?.workspace ?? "-"}</dd>
          </dl>
        </div>
      </div>
      <div className="toolbar">
        <button className="primary" type="button" onClick={startDemo}>
          Запустить демо
        </button>
        <button className="primary" type="button" onClick={startSuite}>
          Запустить все тесты
        </button>
        <button type="button" onClick={() => onNavigate(ROUTES.results)}>
          Открыть расчеты
        </button>
        <button type="button" onClick={() => onNavigate(ROUTES.visualization)}>
          Открыть графики
        </button>
      </div>
    </section>
  );
}
