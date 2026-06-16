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
      <div className="overview-grid">
        <section className="panel">
          <h2>Архитектура решения</h2>
          <ul className="overview-list">
            <li>React/Vite SPA отвечает за русскоязычный интерфейс, ввод параметров, мониторинг задач, просмотр расчётов и графиков.</li>
            <li>FastAPI backend предоставляет REST API, авторизацию токеном, очередь задач, доступ к SQLite и безопасную выдачу файлов результатов.</li>
            <li>Python-адаптер формирует постановку PFLOTRAN из JSON-снимка расчёта, запускает solver и собирает диагностические файлы.</li>
            <li>PFLOTRAN/PETSc выполняют конечно-объёмный расчёт уравнения Ричардса; Plotly/Matplotlib строят интерактивные и статические графики.</li>
            <li>Docker Compose объединяет web-сервис, рабочую область `/workspace`, базу расчётов и папки результатов.</li>
          </ul>
        </section>
        <section className="panel">
          <h2>Модули и лицензии</h2>
          <ul className="overview-list">
            <li>PFLOTRAN — внешний FVM-решатель, заявленная лицензия LGPL.</li>
            <li>PETSc — численная библиотека и MPI-инфраструктура, BSD-подобная 2-clause лицензия.</li>
            <li>FastAPI, Uvicorn, Pydantic — backend API и валидация данных, открытые Python-лицензии экосистемы.</li>
            <li>NumPy, pandas, h5py, PyYAML — подготовка данных, диагностика и чтение/запись расчётных артефактов.</li>
            <li>React, Vite, TypeScript — frontend-сборка и интерфейс; Plotly и Matplotlib — визуализация результатов.</li>
            <li>Ubuntu/Docker packages поставляются из apt/npm/PyPI-репозиториев; перед коммерческим распространением нужен отдельный license review.</li>
          </ul>
        </section>
        <section className="panel">
          <h2>Этап разработки</h2>
          <dl className="kv overview-kv">
            <dt>Стадия</dt>
            <dd>инженерный прототип, подготовка к внутреннему релизу</dd>
            <dt>Готово</dt>
            <dd>web-интерфейс, база расчётов, запуск PFLOTRAN, аналитические тесты, графики и архивирование результатов</dd>
            <dt>Контроль качества</dt>
            <dd>контейнерный check, dry-run генерации, verification-suite и ручная проверка основных сценариев UI</dd>
            <dt>Ограничения</dt>
            <dd>лицензии сторонних компонентов и production-политики безопасности требуют финального юридического и эксплуатационного review</dd>
          </dl>
        </section>
      </div>
    </section>
  );
}
