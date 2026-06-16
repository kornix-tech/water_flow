import type {
  CalculationRead,
  CalculationSummary,
  HealthResponse,
  InputWorkbook,
  JobCreated,
  JobRead,
  RunInfo,
  SoilCurveTable,
  SoilCurveTableCreate,
  SystemInfo
} from "../types";

const API_BASE = "/api";
const TOKEN_KEY = "soilflow_api_token";

export class AuthRequiredError extends Error {
  constructor(message = "Требуется API-токен") {
    super(message);
    this.name = "AuthRequiredError";
  }
}

export function getApiToken(): string {
  return window.sessionStorage.getItem(TOKEN_KEY) ?? "";
}

export function setApiToken(token: string): void {
  const normalized = token.trim();
  if (normalized) {
    window.sessionStorage.setItem(TOKEN_KEY, normalized);
    document.cookie = `${TOKEN_KEY}=${encodeURIComponent(normalized)}; Path=/api/visualization; SameSite=Strict`;
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
    document.cookie = `${TOKEN_KEY}=; Path=/api/visualization; SameSite=Strict; Max-Age=0`;
  }
}

export function clearApiToken(): void {
  window.sessionStorage.removeItem(TOKEN_KEY);
  document.cookie = `${TOKEN_KEY}=; Path=/api/visualization; SameSite=Strict; Max-Age=0`;
}

function authHeaders(): Record<string, string> {
  const token = getApiToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function notifyAuthRequired(): void {
  window.dispatchEvent(new CustomEvent("soilflow-auth-required"));
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  const token = getApiToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401) {
    notifyAuthRequired();
    throw new AuthRequiredError();
  }
  if (!response.ok) {
    const text = await response.text();
    let message = text || `Ошибка HTTP ${response.status}`;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      message = parsed.detail || message;
    } catch {
      // Ответ не обязан быть JSON: для FileResponse или proxy-ошибок оставляем текст как есть.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

async function downloadApiFile(path: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (response.status === 401) {
    notifyAuthRequired();
    throw new AuthRequiredError();
  }
  if (!response.ok) {
    throw new Error(`Не удалось скачать файл: HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function visualizationHtmlUrl(runName: string, version?: number): string {
  const suffix = version ? `?v=${version}` : "";
  return `${API_BASE}/visualization/${encodeURIComponent(runName)}/html${suffix}`;
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function getSystemInfo(): Promise<SystemInfo> {
  return request<SystemInfo>("/system/info");
}

export async function getInputWorkbook(): Promise<InputWorkbook> {
  return request<InputWorkbook>("/inputs/workbook");
}

export async function saveInputWorkbook(workbook: InputWorkbook): Promise<InputWorkbook> {
  return request<InputWorkbook>("/inputs/workbook", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workbook)
  });
}

export async function resetInputWorkbook(): Promise<InputWorkbook> {
  return request<InputWorkbook>("/inputs/reset", { method: "POST" });
}

export async function listCalculations(query = ""): Promise<CalculationSummary[]> {
  const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  return request<CalculationSummary[]>(`/calculations${suffix}`);
}

export async function getCalculation(calculationId: number): Promise<CalculationRead> {
  return request<CalculationRead>(`/calculations/${calculationId}`);
}

export async function runCalculation(calculationId: number): Promise<JobCreated> {
  return request<JobCreated>(`/calculations/${calculationId}/run`, { method: "POST" });
}

export async function deleteCalculation(calculationId: number): Promise<void> {
  await request<{ status: string }>(`/calculations/${calculationId}`, { method: "DELETE" });
}

export async function listSoilCurves(calculationId: number): Promise<SoilCurveTable[]> {
  return request<SoilCurveTable[]>(`/soil-curves/calculations/${calculationId}`);
}

export async function createSoilCurve(calculationId: number, payload: SoilCurveTableCreate): Promise<SoilCurveTable> {
  return request<SoilCurveTable>(`/soil-curves/calculations/${calculationId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function deleteSoilCurve(tableId: number): Promise<void> {
  await request<{ status: string }>(`/soil-curves/${tableId}`, { method: "DELETE" });
}

export async function listJobs(): Promise<JobRead[]> {
  return request<JobRead[]>("/jobs");
}

export async function getJob(jobId: string): Promise<JobRead> {
  return request<JobRead>(`/jobs/${jobId}`);
}

export async function getJobLog(jobId: string): Promise<string> {
  return request<string>(`/jobs/${jobId}/log`);
}

export async function cancelJob(jobId: string): Promise<JobRead> {
  return request<JobRead>(`/jobs/${jobId}/cancel`, { method: "POST" });
}

export async function runDemo(): Promise<JobCreated> {
  return request<JobCreated>("/jobs/run-demo", { method: "POST" });
}

export async function runTestSuite(): Promise<JobCreated> {
  return request<JobCreated>("/jobs/run-test-suite", { method: "POST" });
}

export async function runTest(testName: string): Promise<JobCreated> {
  return request<JobCreated>(`/jobs/run-test/${testName}`, { method: "POST" });
}

export async function runVisualization(runName: string): Promise<JobCreated> {
  return request<JobCreated>(`/jobs/run-visualization/${runName}`, { method: "POST" });
}

export async function listRuns(): Promise<RunInfo[]> {
  return request<RunInfo[]>("/results/runs");
}

export async function getRunFiles(runName: string): Promise<string[]> {
  return request<string[]>(`/results/runs/${runName}/plots`);
}

export function downloadRunZip(runName: string): Promise<void> {
  return downloadApiFile(`/files/download-zip/${encodeURIComponent(runName)}`, `${runName}.zip`);
}

export function downloadRunFile(runName: string, filePath: string): Promise<void> {
  const encodedPath = filePath.split("/").map(encodeURIComponent).join("/");
  const parts = filePath.split("/").filter(Boolean);
  const filename = parts.length ? parts[parts.length - 1] : "soilflow-result";
  return downloadApiFile(`/results/runs/${encodeURIComponent(runName)}/file/${encodedPath}`, filename);
}
