import type { HeatRow } from "../api";
import { busiestHour, formatCount, WEEKDAYS } from "../lib/format";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

/** Weekday × hour (IST). Shade is relative to the busiest hour in the range. */
export function Heatmap({ rows }: { rows: HeatRow[] }) {
  const grid = new Map(rows.map((r) => [`${r.weekday}:${r.hour}`, r.requests]));
  const max = Math.max(1, ...rows.map((r) => r.requests));
  const peak = busiestHour(rows);

  return (
    <div className="heatmap-wrap">
      <p className="heatmap-peak">
        Busiest: <strong>{peak ?? "no traffic"}</strong> <span className="muted">IST</span>
      </p>
      <div className="heatmap" role="table" aria-label="Requests by weekday and hour, IST">
        <div role="row" className="heatmap-row">
          <span role="columnheader" className="heatmap-corner" />
          {HOURS.map((h) => (
            <span key={h} role="columnheader" className="heatmap-hour">
              {h % 3 === 0 ? h : ""}
            </span>
          ))}
        </div>
        {WEEKDAYS.map((day, d) => (
          <div key={day} role="row" className="heatmap-row">
            <span role="rowheader" className="heatmap-day">
              {day}
            </span>
            {HOURS.map((h) => {
              const n = grid.get(`${d + 1}:${h}`) ?? 0;
              const label = `${day} ${String(h).padStart(2, "0")}:00 — ${formatCount(n)} requests`;
              return (
                <span
                  key={h}
                  role="cell"
                  className="heatmap-cell"
                  title={label}
                  aria-label={label}
                  style={{ background: n === 0 ? "var(--heat-0)" : heat(n / max) }}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function heat(share: number): string {
  // Five steps of the accent, so equal-looking cells really are similar.
  const step = Math.min(4, Math.floor(share * 5));
  return `var(--heat-${step + 1})`;
}
