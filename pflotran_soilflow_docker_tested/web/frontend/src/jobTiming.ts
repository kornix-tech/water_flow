import type { JobRead } from "./types";

export const FINISHED_JOB_STATUSES = new Set(["success", "failed", "cancelled"]);

function timestampMs(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours} ч ${minutes} мин`;
  }
  if (minutes > 0) {
    return `${minutes} мин ${seconds} с`;
  }
  return `${seconds} с`;
}

function median(values: number[]): number | null {
  if (!values.length) {
    return null;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2) {
    return sorted[middle];
  }
  return (sorted[middle - 1] + sorted[middle]) / 2;
}

function completedDurationMs(job: JobRead): number | null {
  const startedAt = timestampMs(job.started_at ?? job.created_at);
  const finishedAt = timestampMs(job.finished_at);
  if (startedAt === null || finishedAt === null || finishedAt <= startedAt) {
    return null;
  }
  return finishedAt - startedAt;
}

export function estimateRemainingMs(job: JobRead, jobs: JobRead[], now = Date.now()): number | null {
  if (FINISHED_JOB_STATUSES.has(job.status)) {
    return 0;
  }
  if (job.status !== "running") {
    return null;
  }
  const startedAt = timestampMs(job.started_at ?? job.created_at);
  if (startedAt === null) {
    return null;
  }
  const sameKindDurations = jobs
    .filter((candidate) => candidate.kind === job.kind && candidate.status === "success")
    .map(completedDurationMs)
    .filter((value): value is number => value !== null);
  const expectedDuration = median(sameKindDurations);
  if (expectedDuration === null) {
    return null;
  }
  return Math.max(0, expectedDuration - (now - startedAt));
}

export function jobTimingLabel(job: JobRead, jobs: JobRead[], now = Date.now()): string {
  if (job.status === "success") {
    return "задача выполнена";
  }
  if (job.status === "failed") {
    return "завершена с ошибкой";
  }
  if (job.status === "cancelled") {
    return "задача отменена";
  }
  if (job.status === "queued") {
    return "ожидает запуска";
  }
  const remainingMs = estimateRemainingMs(job, jobs, now);
  if (remainingMs === null) {
    return "оценка пока недоступна";
  }
  if (remainingMs <= 1000) {
    return "завершение ожидается скоро";
  }
  return `осталось примерно ${formatDuration(remainingMs)}`;
}
