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

export function normalizeRoute(path: string): AppRoute {
  const cleanPath = path === "" ? ROUTES.dashboard : path;
  return Object.values(ROUTES).includes(cleanPath as AppRoute) ? (cleanPath as AppRoute) : ROUTES.dashboard;
}
