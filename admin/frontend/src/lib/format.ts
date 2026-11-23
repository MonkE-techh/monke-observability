const count = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const DASH = "—";

export function formatCount(n: number | null | undefined): string {
  return n === null || n === undefined ? DASH : count.format(Math.round(n));
}

export function formatUsd(n: number | null | undefined): string {
  if (n === null || n === undefined) return DASH;
  if (n > 0 && n < 0.01) return `$${n.toPrecision(2)}`;
  return `$${n.toFixed(2)}`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return DASH;
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function formatPercent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return DASH;
  const pct = rate * 100;
  return `${pct >= 10 ? Math.round(pct) : Number(pct.toFixed(1))}%`;
}

const istParts = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** "23 Nov, 16:05" in IST. */
export function formatIst(iso: string): string {
  const parts = Object.fromEntries(istParts.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${parts.day} ${parts.month}, ${parts.hour}:${parts.minute}`;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "No events in range";
  const ago = now.getTime() - new Date(iso).getTime();
  if (ago < MINUTE) return "just now";
  if (ago < HOUR) return `${Math.floor(ago / MINUTE)} min ago`;
  if (ago < 2 * DAY) return `${Math.floor(ago / HOUR)} h ago`;
  return `${Math.floor(ago / DAY)} days ago`;
}

export function isStale(iso: string | null | undefined, now: Date = new Date()): boolean {
  return !iso || now.getTime() - new Date(iso).getTime() > DAY;
}

export interface DailyRow {
  day: string;
  app: string;
  requests: number;
}

export function pivotDaily(rows: DailyRow[]): { rows: Array<Record<string, string | number>>; apps: string[] } {
  const apps: string[] = [];
  const byDay = new Map<string, Record<string, string | number>>();
  for (const r of rows) {
    if (!apps.includes(r.app)) apps.push(r.app);
    const day = String(r.day).slice(0, 10);
    const row = byDay.get(day) ?? { day };
    row[r.app] = Math.round(Number(r.requests) || 0);
    byDay.set(day, row);
  }
  const out = [...byDay.values()].sort((a, b) => String(a.day).localeCompare(String(b.day)));
  for (const row of out) for (const app of apps) row[app] ??= 0;
  return { rows: out, apps };
}

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export interface HeatCell {
  weekday: number; // 1 = Monday … 7 = Sunday (ClickHouse toDayOfWeek)
  hour: number;
  requests: number;
}

export function busiestHour(cells: HeatCell[]): string | null {
  const top = cells.reduce<HeatCell | null>((best, c) => (!best || c.requests > best.requests ? c : best), null);
  if (!top || top.requests <= 0) return null;
  const h = (n: number) => `${String(n % 24).padStart(2, "0")}:00`;
  return `${WEEKDAYS[top.weekday - 1]} ${h(top.hour)}–${h(top.hour + 1)}`;
}

const ERRORS: Record<string, string> = {
  posthog_timeout: "PostHog took too long to answer. Try Refresh in a minute.",
  posthog_rate_limited: "PostHog's query limit was reached. Figures will load again within the hour.",
  posthog_unavailable: "PostHog didn't answer this query. Try Refresh; if it keeps failing, check PostHog's status.",
  not_configured: "PostHog isn't connected: set POSTHOG_PERSONAL_API_KEY and POSTHOG_PROJECT_ID on the admin service.",
};

export function errorMessage(code: string): string {
  return ERRORS[code] ?? "This figure couldn't be loaded from PostHog. Try Refresh.";
}
