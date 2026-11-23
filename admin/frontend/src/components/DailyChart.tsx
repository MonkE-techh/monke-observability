import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { DailyRow } from "../api";
import { formatCount, pivotDaily } from "../lib/format";

// Okabe–Ito: distinguishable with common colour-vision deficiencies.
export const APP_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#7F7F7F"];

const shortDay = (day: string) =>
  new Date(`${day}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export function DailyChart({ rows }: { rows: DailyRow[] }) {
  const { rows: data, apps } = pivotDaily(rows);
  return (
    <div className="chart" role="img" aria-label={`Requests per day for ${apps.join(", ")}`}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--line)" />
          <XAxis dataKey="day" tickFormatter={shortDay} tick={{ fontSize: 12, fill: "var(--muted)" }} tickLine={false} />
          <YAxis
            tickFormatter={(v: number) => formatCount(v)}
            tick={{ fontSize: 12, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={false}
            width={56}
          />
          <Tooltip
            formatter={(v) => formatCount(Number(v))}
            labelFormatter={(l) => shortDay(String(l))}
            contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 6 }}
          />
          {apps.length > 1 ? <Legend iconType="square" wrapperStyle={{ fontSize: 12 }} /> : null}
          {apps.map((app, i) => (
            <Bar key={app} dataKey={app} stackId="apps" fill={APP_COLORS[i % APP_COLORS.length]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
