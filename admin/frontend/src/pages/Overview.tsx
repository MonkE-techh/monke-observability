import { api, type AppRow } from "../api";
import { DailyChart } from "../components/DailyChart";
import { type Column, DataTable } from "../components/DataTable";
import { Heatmap } from "../components/Heatmap";
import { PanelBox } from "../components/PanelBox";
import { TileStrip } from "../components/TileStrip";
import { formatCount, formatIst, formatMs, formatPercent, formatUsd, isStale, relativeTime } from "../lib/format";
import { useData } from "../useData";
import { LoadFailure, PageActions } from "./shared";

export function Overview({ range, env, navigate }: { range: number; env: string; navigate: (path: string) => void }) {
  const { data, failure, loading, reload, refresh } = useData((r) => api.overview(range, env, r), `overview:${env}:${range}`);
  if (failure) return <LoadFailure failure={failure} onRetry={reload} />;
  const p = data?.panels;

  const columns: Column<AppRow>[] = [
    {
      label: "App",
      render: (r) => (
        <a
          href={`/apps/${r.app}?range=${range}&env=${env}`}
          onClick={(e) => {
            e.preventDefault();
            navigate(`/apps/${r.app}?range=${range}&env=${env}`);
          }}
        >
          {r.app}
          {!r.registered ? <span className="tag">not in apps.yaml</span> : null}
        </a>
      ),
    },
    { label: "Requests", numeric: true, render: (r) => formatCount(r.requests) },
    { label: "5xx", numeric: true, render: (r) => (r.requests ? formatPercent(r.errors_5xx / r.requests) : "—") },
    { label: "Avg", numeric: true, render: (r) => formatMs(r.avg_ms) },
    { label: "Slowest", numeric: true, render: (r) => formatMs(r.slowest_ms) },
    { label: "Visitors", numeric: true, render: (r) => formatCount(r.visitors) },
    { label: "LLM cost", numeric: true, render: (r) => (r.uses_llm || r.llm_cost_usd ? formatUsd(r.llm_cost_usd) : "—") },
    {
      label: "Last event",
      render: (r) => (
        <span className={isStale(r.last_event) ? "stale" : undefined} title={r.last_event ? formatIst(r.last_event) : undefined}>
          {isStale(r.last_event) ? "⚠ " : ""}
          {relativeTime(r.last_event)}
        </span>
      ),
    },
  ];

  return (
    <>
      <div className="page-title">
        <h1>All apps</h1>
        <PageActions data={data} loading={loading} onRefresh={refresh} />
      </div>
      <TileStrip
        panel={p?.tiles}
        range={range}
        llmHistoryDays={data?.llm_history_days ?? 30}
        empty={`No ${env} events from any app in the last ${range} days. Check that the apps have POSTHOG_PROJECT_TOKEN set.`}
      />
      <div className="grid">
        <PanelBox title="Requests per day" panel={p?.daily} empty="No API requests in this range." onRetry={refresh} wide>
          {(rows) => <DailyChart rows={rows} />}
        </PanelBox>
        <PanelBox title="Peak hours" panel={p?.heatmap} empty="No API requests in this range." onRetry={refresh}>
          {(rows) => <Heatmap rows={rows} />}
        </PanelBox>
      </div>
      <PanelBox
        title="Apps"
        panel={p?.apps}
        empty="No apps are registered in apps.yaml yet."
        note="An app with no event for over a day is flagged ⚠: its tracking may be broken."
        onRetry={refresh}
      >
        {(rows) => <DataTable rows={rows} columns={columns} rowKey={(r) => r.app} />}
      </PanelBox>
    </>
  );
}
