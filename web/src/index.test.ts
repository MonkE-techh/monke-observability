import { describe, expect, it } from "vitest";

import { initAnalytics, type PostHogLike, pseudonymousId } from "./index";

class FakePostHog implements PostHogLike {
  initCalls: Array<{ token: string; config: Record<string, unknown> }> = [];
  registered: Record<string, unknown> = {};
  identified: Array<{ id: string; props?: Record<string, unknown> }> = [];
  resets = 0;

  init(token: string, config: Record<string, unknown>) {
    this.initCalls.push({ token, config });
  }
  register(props: Record<string, unknown>) {
    this.registered = { ...this.registered, ...props };
  }
  identify(id: string, props?: Record<string, unknown>) {
    this.identified.push({ id, props });
  }
  reset() {
    this.resets += 1;
    this.registered = {};
  }
}

const base = { appName: "creator-curation", token: "phc_test", apiHosts: ["monke-creator-api.onrender.com"] };

describe("initAnalytics", () => {
  it("initialises PostHog in the EU region with tracing headers for the app's API", () => {
    const ph = new FakePostHog();

    initAnalytics(ph, base);

    expect(ph.initCalls).toHaveLength(1);
    const { token, config } = ph.initCalls[0]!;
    expect(token).toBe("phc_test");
    expect(config.api_host).toBe("https://eu.i.posthog.com");
    expect(config.tracing_headers).toEqual(["monke-creator-api.onrender.com"]);
    expect(config.capture_pageview).toBe("history_change");
    expect(config.person_profiles).toBe("identified_only");
  });

  it("sends uncaught browser errors to Error Tracking", () => {
    const ph = new FakePostHog();

    initAnalytics(ph, base);

    expect(ph.initCalls[0]!.config.capture_exceptions).toBe(true);
  });

  it("tags every event with app_name and environment", () => {
    const ph = new FakePostHog();

    initAnalytics(ph, { ...base, environment: "staging" });

    expect(ph.registered).toEqual({ app_name: "creator-curation", environment: "staging" });
  });

  it("reduces API URLs to bare hostnames, which is what tracing_headers matches", () => {
    const ph = new FakePostHog();

    initAnalytics(ph, { ...base, apiHosts: ["https://api.example.com/v1", "http://localhost:8000", "127.0.0.1"] });

    expect(ph.initCalls[0]!.config.tracing_headers).toEqual(["api.example.com", "localhost", "127.0.0.1"]);
  });

  it("does nothing and returns a no-op handle when no token is configured", () => {
    const ph = new FakePostHog();

    const analytics = initAnalytics(ph, { ...base, token: undefined });
    analytics.identify(1);
    analytics.reset();

    expect(analytics.enabled).toBe(false);
    expect(ph.initCalls).toHaveLength(0);
    expect(ph.identified).toHaveLength(0);
    expect(ph.resets).toBe(0);
  });

  it("rejects app names that are not kebab-case", () => {
    expect(() => initAnalytics(new FakePostHog(), { ...base, appName: "Creator Curation" })).toThrow(/kebab-case/);
  });
});

describe("identity", () => {
  it("identifies with the same app-namespaced id the backend uses", () => {
    const ph = new FakePostHog();
    const analytics = initAnalytics(ph, base);

    analytics.identify(42, { role: "admin" });

    expect(ph.identified).toEqual([{ id: "creator-curation:42", props: { role: "admin" } }]);
  });

  it("does not double-prefix an id that is already namespaced", () => {
    const ph = new FakePostHog();
    initAnalytics(ph, base).identify("creator-curation:42");

    expect(ph.identified[0]!.id).toBe("creator-curation:42");
  });

  it("ignores empty user ids", () => {
    const ph = new FakePostHog();
    initAnalytics(ph, base).identify("");

    expect(ph.identified).toHaveLength(0);
  });

  it("keeps app tagging after logout resets the PostHog identity", () => {
    const ph = new FakePostHog();
    const analytics = initAnalytics(ph, base);

    analytics.reset();

    expect(ph.resets).toBe(1);
    expect(ph.registered).toEqual({ app_name: "creator-curation", environment: "production" });
  });
});

describe("pseudonymousId", () => {
  it("matches the Python package's hash of the normalised value", async () => {
    // sha256("person@example.com")[:16], same vector as python/tests/test_core.py
    expect(await pseudonymousId("person@example.com")).toBe("542d240129883c01");
    expect(await pseudonymousId("  Person@Example.com ")).toBe("542d240129883c01");
    expect(await pseudonymousId("")).toBeNull();
  });
});
