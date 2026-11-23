import type { Panel, Tiles } from "../api";
import { errorMessage, formatCount, formatMs, formatPercent, formatUsd } from "../lib/format";

interface Props {
  panel: Panel<Tiles> | undefined;
  range: number;
  llmHistoryDays: number;
  empty: string;
}

export function TileStrip({ panel, range, llmHistoryDays, empty }: Props) {
  if (panel === undefined) return <p className="strip strip-state">Loading…</p>;
  if (panel.status === "error")
    return (
      <p className="strip strip-state state-error" role="alert">
        {errorMessage(panel.error)}
      </p>
    );
  if (panel.status === "empty") return <p className="strip strip-state">{empty}</p>;

  const t = panel.data;
  const llmLimited = range > llmHistoryDays;
  const figures = [
    { label: "API requests", value: formatCount(t.requests) },
    {
      label: "Server errors (5xx)",
      value: formatPercent(t.error_rate),
      detail: `${formatCount(t.errors_5xx)} requests`,
      alarm: (t.error_rate ?? 0) >= 0.01,
    },
    { label: "Average response", value: formatMs(t.avg_ms), detail: `slowest ${formatMs(t.slowest_ms)}` },
    { label: "Visitors", value: formatCount(t.visitors) },
    {
      label: "LLM cost",
      value: formatUsd(t.llm_cost_usd),
      detail: llmLimited ? `${formatCount(t.llm_calls)} calls, last ${llmHistoryDays} days only` : `${formatCount(t.llm_calls)} calls`,
    },
  ];

  return (
    <dl className="strip">
      {figures.map((f) => (
        <div key={f.label} className={f.alarm ? "figure figure-alarm" : "figure"}>
          <dt>{f.label}</dt>
          <dd>
            <span className="figure-value">{f.value}</span>
            {f.detail ? <span className="figure-detail">{f.detail}</span> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}
