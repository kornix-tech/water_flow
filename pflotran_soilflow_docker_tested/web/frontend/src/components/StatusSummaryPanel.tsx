import { ErrorNotice } from "./ErrorNotice";
import type { StatusSummaryItem } from "../types";

const STATUS_LABELS: Record<string, string> = {
  PASS: "пройдено",
  PASS_WITH_WARNINGS: "пройдено с предупреждениями",
  PASS_WITH_SKIPS: "пройдено с пропусками",
  FAIL: "ошибка",
  DRY_RUN: "сухой запуск",
  GENERATED: "сгенерировано",
  GENERATED_ONLY: "только файлы",
  READY: "готово",
  UNKNOWN: "неизвестно",
  queued: "в очереди",
  running: "выполняется",
  success: "готово",
  failed: "ошибка",
  cancelled: "отменено"
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function StatusSummaryPanel({
  title,
  items,
  error,
  emptyText = "Сводка состояния пока недоступна."
}: {
  title: string;
  items: StatusSummaryItem[];
  error?: string;
  emptyText?: string;
}) {
  if (error) {
    return <ErrorNotice message={error} />;
  }
  if (!items.length) {
    return <p className="muted">{emptyText}</p>;
  }
  return (
    <section className="status-summary-panel">
      <h3>{title}</h3>
      <div className="status-card-grid">
        {items.map((item) => (
          <article className="status-card" key={`${item.kind}-${item.title}`}>
            <div className="status-card-header">
              <div>
                <h4>{item.title}</h4>
                {item.subtitle && <p>{item.subtitle}</p>}
              </div>
              <span className={`status-pill status-pill-${item.status.toLowerCase().replace(/_/g, "-")}`}>{statusLabel(item.status)}</span>
            </div>
            {item.metrics.length > 0 && (
              <div className="status-card-metrics">
                {item.metrics.map((metric) => (
                  <div key={`${item.kind}-${metric.label}`}>
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </div>
                ))}
              </div>
            )}
            {(item.source || item.files.length > 0 || item.messages.length > 0) && (
              <div className="status-card-footer">
                {item.source && <span className="mono">{item.source}</span>}
                {item.files.length > 0 && <span>{item.files.length} файл.</span>}
                {item.messages.map((message) => (
                  <span key={message}>{message}</span>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
