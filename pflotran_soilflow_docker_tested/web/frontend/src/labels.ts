const HEALTH_STATUS_LABELS: Record<string, string> = {
  ok: "работает"
};

const AUTH_MODE_LABELS: Record<string, string> = {
  none: "без токена",
  token: "по токену"
};

const JOB_KIND_LABELS: Record<string, string> = {
  demo: "демо",
  calculation: "расчёт",
  "custom-demo": "пользовательский расчёт",
  test: "тест",
  "test-suite": "набор тестов",
  visualization: "графики"
};

const JOB_STATUS_LABELS: Record<string, string> = {
  queued: "в очереди",
  running: "выполняется",
  success: "готово",
  failed: "ошибка",
  cancelled: "отменено"
};

export function healthStatusLabel(status: string | null | undefined): string {
  if (!status) {
    return "неизвестно";
  }
  return HEALTH_STATUS_LABELS[status] ?? "неизвестно";
}

export function authModeLabel(mode: string | null | undefined): string {
  if (!mode) {
    return "-";
  }
  return AUTH_MODE_LABELS[mode] ?? "другой режим";
}

export function jobKindLabel(kind: string): string {
  return JOB_KIND_LABELS[kind] ?? "другое";
}

export function jobStatusLabel(status: string): string {
  return JOB_STATUS_LABELS[status] ?? "неизвестно";
}

export function systemValueLabel(key: string, value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "да" : "нет";
  }
  if (key === "auth_mode") {
    return authModeLabel(String(value));
  }
  return String(value);
}
