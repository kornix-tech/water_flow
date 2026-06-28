export type JobStatus = "queued" | "running" | "success" | "failed" | "cancelled";

export interface HealthResponse {
  status: string;
  service: string;
}

export interface SystemInfo {
  soilflow_home: string;
  workspace: string;
  pflotran_exe: string;
  pflotran_exists: boolean;
  job_workers: number;
  auth_mode: string;
  frontend_available: boolean;
  api_docs_enabled: boolean;
  hsts_enabled: boolean;
  api_rate_limit_per_minute: number;
}

export interface JobRead {
  id: string;
  kind: string;
  status: JobStatus;
  command: string[];
  run_name: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  log_path: string;
  output_dir: string;
  error_message: string | null;
  calculation_id: number | null;
}

export interface JobCreated {
  job_id: string;
  status: JobStatus;
  run_name: string | null;
}

export interface RunInfo {
  run_name: string;
  path: string;
  has_test_status: boolean;
  has_suite_status: boolean;
  has_visualization: boolean;
  files: string[];
}

export interface TestSuiteResult {
  test_id: string;
  status: string;
  verification_level: string | null;
  output_dir: string | null;
  metrics: Record<string, string | number | boolean | null>;
}

export interface TestSuiteStatus {
  run_name: string;
  status: string;
  summary: Record<string, string | number>;
  results: TestSuiteResult[];
  source: string;
  files: string[];
}

export interface TestRunStatus {
  run_name: string;
  status: string;
  test_id: string | null;
  fields: Record<string, string | number | boolean>;
  messages: string[];
  diagnostics: Record<string, unknown>;
  source: string;
  files: string[];
}

export interface StatusSummaryMetric {
  label: string;
  value: string;
}

export interface StatusSummaryItem {
  kind: string;
  title: string;
  status: string;
  subtitle: string | null;
  metrics: StatusSummaryMetric[];
  source: string | null;
  files: string[];
  messages: string[];
}

export interface RunStatusOverview {
  run_name: string;
  items: StatusSummaryItem[];
}

export interface InputField {
  sheet: string;
  row: number;
  section: string | null;
  key: string;
  value: string | number | boolean | null;
  value_type: "text" | "number" | "boolean" | "date" | string;
  unit: string | null;
  description: string | null;
  pflotran: string | null;
  note: string | null;
}

export interface WeatherRow {
  row: number | null;
  date: string;
  precipitation_mm_day: number;
  irrigation_mm_day: number;
  epot_mm_day: number;
  tpot_mm_day: number;
  groundwater_depth_m: number | null;
  comment: string | null;
}

export interface InputTab {
  id: string;
  title: string;
  kind: "fields" | "weather" | string;
  description: string | null;
  fields: InputField[];
  weather: WeatherRow[];
}

export interface InputWorkbook {
  filename: string;
  updated_at: string | null;
  tabs: InputTab[];
  calculation_id: number | null;
  calculation_title: string | null;
  calculation_created_at: string | null;
  calculation_status: string | null;
}

export interface CalculationSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  run_name: string | null;
  job_id: string | null;
  status: string;
  result_dir: string | null;
  has_results: boolean;
}

export interface CalculationRead extends CalculationSummary {
  input: InputWorkbook;
}

export interface SoilCurvePoint {
  id?: number;
  table_id?: number;
  point_index: number;
  pressure_head_m: number | null;
  pressure_pa: number | null;
  water_content: number | null;
  saturation: number | null;
  relative_permeability: number | null;
  hydraulic_conductivity_m_s: number | null;
  comment: string | null;
}

export interface SoilCurveTable {
  id: number;
  calculation_id: number;
  curve_name: string;
  curve_kind: string;
  retention_model: string | null;
  conductivity_model: string | null;
  pressure_unit: string;
  saturation_unit: string;
  conductivity_unit: string | null;
  created_at: string;
  updated_at: string;
  comment: string | null;
  points: SoilCurvePoint[];
}

export interface SoilCurveTableCreate {
  curve_name: string;
  curve_kind: string;
  retention_model: string | null;
  conductivity_model: string | null;
  pressure_unit: string;
  saturation_unit: string;
  conductivity_unit: string | null;
  comment: string | null;
  points: SoilCurvePoint[];
}
