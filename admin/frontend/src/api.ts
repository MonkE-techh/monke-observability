export type Panel<T> = { status: "ok"; data: T } | { status: "empty" } | { status: "error"; error: string };

export interface Tiles {
  requests: number;
  errors_5xx: number;
  error_rate: number | null;
  avg_ms: number | null;
  slowest_ms: number | null;
  visitors: number;
  llm_calls: number;
  llm_cost_usd: number;
}

export interface AppRow {
  app: string;
  registered: boolean;
  requests: number;
  errors_5xx: number;
  avg_ms: number | null;
  slowest_ms: number | null;
  visitors: number;
  llm_cost_usd: number;
  last_event: string | null;
  uses_llm: boolean;
}

export interface RouteRow {
  route: string;
  requests: number;
  errors_5xx: number;
  avg_ms: number | null;
  slowest_ms: number | null;
}

export interface ErrorRow {
  timestamp: string;
  method: string;
  route: string;
  status_code: number;
  error_type: string | null;
  user_id: string | null;
}

export interface LlmModelRow {
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  errors: number;
}

export interface LlmSourceRow {
  source: string;
  calls: number;
  cost_usd: number;
}

export interface LlmUserRow {
  user_id: string;
  calls: number;
  cost_usd: number;
}

export interface VisitorRow {
  value: string;
  visitors: number;
}

export interface DailyRow {
  day: string;
  app: string;
  requests: number;
}

export interface HeatRow {
  weekday: number;
  hour: number;
  requests: number;
}

interface Envelope<P> {
  range: number;
  environment: string;
  generated_at: string;
  llm_history_days: number;
  refresh_throttled: boolean;
  panels: P;
}

export type Overview = Envelope<{
  tiles: Panel<Tiles>;
  daily: Panel<DailyRow[]>;
  heatmap: Panel<HeatRow[]>;
  apps: Panel<AppRow[]>;
}>;

export type AppDetail = Envelope<{
  tiles: Panel<Tiles>;
  daily: Panel<DailyRow[]>;
  heatmap: Panel<HeatRow[]>;
  routes: Panel<RouteRow[]>;
  errors: Panel<ErrorRow[]>;
  llm_models: Panel<LlmModelRow[]>;
  llm_sources: Panel<LlmSourceRow[]>;
  llm_users: Panel<LlmUserRow[]>;
  visitors: Panel<{ country: VisitorRow[]; device: VisitorRow[]; browser: VisitorRow[] }>;
}> & { app: string; registered: boolean; uses_llm: boolean };

export interface Meta {
  apps: Array<{ name: string; uses_llm: boolean; status: string }>;
  ranges: number[];
  posthog_url: string;
}

export interface Status {
  configured: boolean;
  missing: string[];
}

export class HttpError extends Error {
  constructor(public status: number) {
    super(`HTTP ${status}`);
  }
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } });
  if (!response.ok) throw new HttpError(response.status);
  return (await response.json()) as T;
}

export const api = {
  status: () => get<Status>("/api/status"),
  me: () => get<{ email: string; auth_disabled: boolean }>("/api/auth/me"),
  meta: () => get<Meta>("/api/meta"),
  overview: (range: number, env: string, refresh = false) =>
    get<Overview>(`/api/overview?range=${range}&env=${env}&refresh=${refresh}`),
  app: (name: string, range: number, env: string, refresh = false) =>
    get<AppDetail>(`/api/apps/${encodeURIComponent(name)}?range=${range}&env=${env}&refresh=${refresh}`),
  logout: () => fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }),
};
