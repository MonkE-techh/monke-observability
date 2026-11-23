import { api, type ErrorRow, type LlmModelRow, type LlmSourceRow, type LlmUserRow, type RouteRow, type VisitorRow } from "../api";
import { DailyChart } from "../components/DailyChart";
import { type Column, DataTable } from "../components/DataTable";
import { Heatmap } from "../components/Heatmap";
import { PanelBox } from "../components/PanelBox";
import { TileStrip } from "../components/TileStrip";
import { formatCount, formatIst, formatMs, formatPercent, formatUsd } from "../lib/format";
import { useData } from "../useData";
import { LoadFailure, PageActions } from "./shared";

const routeColumns: Column<RouteRow>[] = [
  { label: "Route", render: (r) => <code>{r.route}</code> },
  { label: "Requests", numeric: true, render: (r) => formatCount(r.requests) },
  { label: "5xx", numeric: true, render: (r) => (r.requests ? formatPercent(r.errors_5xx / r.requests) : "—") },
  { label: "Avg", numeric: true, render: (r) => formatMs(r.avg_ms) },
  { label: "Slowest", numeric: true, render: (r) => formatMs(r.slowest_ms) },
];

const errorColumns: Column<ErrorRow>[] = [
  { label: "Time (IST)", render: (r) => formatIst(r.timestamp) },
  { label: "Request", render: (r) => <code>{`${r.method} ${r.route}`}</code> },
  { label: "Status", numeric: true, render: (r) => r.status_code },
  { label: "Error", render: (r) => r.error_type ?? "—" },
  { label: "User", render: (r) => r.user_id ?? "anonymous" },
];

const modelColumns: Column<LlmModelRow>[] = [
  { label: "Model", render: (r) => <code>{r.model}</code> },
  { label: "Calls", numeric: true, render: (r) => formatCount(r.calls) },
  { label: "Input tokens", numeric: true, render: (r) => formatCount(r.input_tokens) },
  { label: "Output tokens", numeric: true, render: (r) => formatCount(r.output_tokens) },
  { label: "Cost", numeric: true, render: (r) => formatUsd(r.cost_usd) },
  { label: "Failed", numeric: true, render: (r) => formatCount(r.errors) },
];

const sourceColumns: Column<LlmSourceRow>[] = [
  { label: "Job or route", render: (r) => <code>{r.source}</code> },
  { label: "Calls", numeric: true, render: (r) => formatCount(r.calls) },
  { label: "Cost", numeric: true, render: (r) => formatUsd(r.cost_usd) },
];

const userColumns: Column<LlmUserRow>[] = [
  { label: "User", render: (r) => <code>{r.user_id}</code> },
  { label: "Calls", numeric: true, render: (r) => formatCount(r.calls) },
  { label: "Cost", numeric: true, render: (r) => formatUsd(r.cost_usd) },
];

const visitorColumns = (label: string): Column<VisitorRow>[] => [
  { label, render: (r) => r.value },
  { label: "Visitors", numeric: true, render: (r) => formatCount(r.visitors) },
];

export function AppPage({
  name,
  range,
  env,
  navigate,
}: {
  name: string;
  range: number;
  env: string;
  navigate: (path: string) => void;
}) {
  const { data, failure, loading, reload, refresh } = useData((r) => api.app(name, range, env, r), `app:${name}:${env}:${range}`);
  if (failure) return <LoadFailure failure={failure} onRetry={reload} />;
  const p = data?.panels;
  const llmNote =
    data && range > data.llm_history_days ? `PostHog keeps LLM events ${data.llm_history_days} days, so this covers the last ${data.llm_history_days} days.` : undefined;
  const noLlm = data && !data.uses_llm ? "This app isn't marked as using an LLM in apps.yaml." : "No LLM calls recorded in this range.";

  return (
    <>
      <p className="crumb">
        <a
          href={`/?range=${range}&env=${env}`}
          onClick={(e) => {
            e.preventDefault();
            navigate(`/?range=${range}&env=${env}`);
          }}
        >
          All apps
        </a>
      </p>
      <div className="page-title">
        <h1>
          {name}
          {data && !data.registered ? <span className="tag">not in apps.yaml</span> : null}
        </h1>
        <PageActions data={data} loading={loading} onRefresh={refresh} />
      </div>
      <TileStrip
        panel={p?.tiles}
        range={range}
        llmHistoryDays={data?.llm_history_days ?? 30}
        empty={`No ${env} events from ${name} in the last ${range} days. If it should have traffic, check its APP_NAME and POSTHOG_PROJECT_TOKEN on Render.`}
      />
      <div className="grid">
        <PanelBox title="Requests per day" panel={p?.daily} empty="No API requests in this range." onRetry={refresh} wide>
          {(rows) => <DailyChart rows={rows} />}
        </PanelBox>
        <PanelBox title="Peak hours" panel={p?.heatmap} empty="No API requests in this range." onRetry={refresh}>
          {(rows) => <Heatmap rows={rows} />}
        </PanelBox>
      </div>
      <PanelBox title="Busiest routes" panel={p?.routes} empty="No API requests in this range." onRetry={refresh}>
        {(rows) => <DataTable rows={rows} columns={routeColumns} rowKey={(r) => r.route} />}
      </PanelBox>
      <PanelBox
        title="Recent server errors"
        panel={p?.errors}
        empty="No server errors (5xx) in this range."
        note="The last 50 requests that ended in a 5xx."
        onRetry={refresh}
      >
        {(rows) => <DataTable rows={rows} columns={errorColumns} rowKey={(r, i) => `${r.timestamp}-${i}`} />}
      </PanelBox>
      <div className="grid grid-even">
        <PanelBox title="LLM cost by model" panel={p?.llm_models} empty={noLlm} note={llmNote} onRetry={refresh}>
          {(rows) => <DataTable rows={rows} columns={modelColumns} rowKey={(r) => r.model} />}
        </PanelBox>
        <PanelBox title="LLM cost by job or route" panel={p?.llm_sources} empty={noLlm} note={llmNote} onRetry={refresh}>
          {(rows) => <DataTable rows={rows} columns={sourceColumns} rowKey={(r) => r.source} />}
        </PanelBox>
      </div>
      <PanelBox
        title="Users with the highest LLM cost"
        panel={p?.llm_users}
        empty="No LLM calls linked to a signed-in user in this range."
        note={llmNote}
        onRetry={refresh}
      >
        {(rows) => <DataTable rows={rows} columns={userColumns} rowKey={(r) => r.user_id} />}
      </PanelBox>
      <PanelBox
        title="Visitors"
        panel={p?.visitors}
        empty="No page views in this range. The browser package may not be installed in this app's frontend yet."
        onRetry={refresh}
      >
        {(v) => (
          <div className="grid grid-three">
            <DataTable rows={v.country} columns={visitorColumns("Country")} rowKey={(r) => r.value} />
            <DataTable rows={v.device} columns={visitorColumns("Device")} rowKey={(r) => r.value} />
            <DataTable rows={v.browser} columns={visitorColumns("Browser")} rowKey={(r) => r.value} />
          </div>
        )}
      </PanelBox>
    </>
  );
}
