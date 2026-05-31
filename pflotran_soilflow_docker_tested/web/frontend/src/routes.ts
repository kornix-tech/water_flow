export const ROUTES = {
  dashboard: "/",
  inputs: "/ishodnye",
  jobs: "/status",
  tests: "/testy",
  results: "/raschety",
  visualization: "/grafiki",
  system: "/sistema"
} as const;

export type AppRoute = (typeof ROUTES)[keyof typeof ROUTES];

const LEGACY_ROUTES: Record<string, AppRoute> = {
  "/inputs": ROUTES.inputs,
  "/vvod": ROUTES.inputs,
  "/jobs": ROUTES.jobs,
  "/zadachi": ROUTES.jobs,
  "/tests": ROUTES.tests,
  "/results": ROUTES.results,
  "/rezultaty": ROUTES.results,
  "/visualization": ROUTES.visualization,
  "/system": ROUTES.system
};

export function normalizeRoute(path: string): AppRoute {
  const cleanPath = path === "" ? ROUTES.dashboard : path;
  return LEGACY_ROUTES[cleanPath] ?? (Object.values(ROUTES).includes(cleanPath as AppRoute) ? (cleanPath as AppRoute) : ROUTES.dashboard);
}
