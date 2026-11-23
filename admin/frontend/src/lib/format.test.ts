import { describe, expect, it } from "vitest";

import {
  busiestHour,
  errorMessage,
  formatCount,
  formatIst,
  formatMs,
  formatPercent,
  formatUsd,
  isStale,
  pivotDaily,
  relativeTime,
} from "./format";

const NOW = new Date("2026-11-23T12:00:00Z");

describe("numbers", () => {
  it("groups counts the Indian way", () => {
    expect(formatCount(1234567)).toBe("12,34,567");
    expect(formatCount(0)).toBe("0");
  });

  it("shows small LLM costs with enough precision to be useful", () => {
    expect(formatUsd(3.1234)).toBe("$3.12");
    expect(formatUsd(0.0042)).toBe("$0.0042");
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("formats durations and rates, with a dash for missing values", () => {
    expect(formatMs(310.4)).toBe("310 ms");
    expect(formatMs(9120)).toBe("9.1 s");
    expect(formatMs(null)).toBe("—");
    expect(formatPercent(0.004)).toBe("0.4%");
    expect(formatPercent(0.25)).toBe("25%");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("time", () => {
  it("shows timestamps in IST", () => {
    expect(formatIst("2026-11-23T10:35:00Z")).toBe("23 Nov, 16:05");
  });

  it("describes how long ago the last event was", () => {
    expect(relativeTime("2026-11-23T11:58:00Z", NOW)).toBe("2 min ago");
    expect(relativeTime("2026-11-22T10:00:00Z", NOW)).toBe("26 h ago");
    expect(relativeTime("2026-11-19T12:00:00Z", NOW)).toBe("4 days ago");
    expect(relativeTime(null, NOW)).toBe("No events in range");
  });

  it("flags apps silent for more than a day", () => {
    expect(isStale("2026-11-23T11:00:00Z", NOW)).toBe(false);
    expect(isStale("2026-11-22T11:00:00Z", NOW)).toBe(true);
    expect(isStale(null, NOW)).toBe(true);
  });
});

describe("charts", () => {
  it("pivots daily rows into one row per day with a column per app", () => {
    const { rows, apps } = pivotDaily([
      { day: "2026-11-21", app: "radar", requests: 10.4 },
      { day: "2026-11-21", app: "cc", requests: 2 },
      { day: "2026-11-22", app: "radar", requests: 5 },
    ]);

    expect(apps).toEqual(["radar", "cc"]);
    expect(rows).toEqual([
      { day: "2026-11-21", radar: 10, cc: 2 },
      { day: "2026-11-22", radar: 5, cc: 0 },
    ]);
  });

  it("finds the busiest weekday and hour", () => {
    expect(
      busiestHour([
        { weekday: 2, hour: 15, requests: 40 },
        { weekday: 5, hour: 9, requests: 12 },
      ]),
    ).toBe("Tue 15:00–16:00");
    expect(busiestHour([])).toBeNull();
  });
});

describe("panel errors", () => {
  it("explains each error code and what to do", () => {
    expect(errorMessage("posthog_timeout")).toMatch(/took too long/);
    expect(errorMessage("posthog_rate_limited")).toMatch(/limit/);
    expect(errorMessage("not_configured")).toMatch(/POSTHOG_PERSONAL_API_KEY/);
    expect(errorMessage("something_new")).toMatch(/PostHog/);
  });
});
