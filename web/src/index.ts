/**
 * Browser analytics setup shared by Monk-E apps.
 *
 *   import posthog from "posthog-js";
 *   import { initAnalytics } from "@monke/observability-web";
 *
 *   export const analytics = initAnalytics(posthog, {
 *     appName: "creator-curation",
 *     token: import.meta.env.VITE_POSTHOG_PROJECT_TOKEN,   // public phc_ key
 *     environment: import.meta.env.MODE,
 *     apiHosts: [new URL(import.meta.env.VITE_API_URL).hostname],
 *   });
 *   // after sign-in:  analytics.identify(user.id)
 *   // on sign-out:    analytics.reset()
 *
 * The app's API must allow the X-POSTHOG-DISTINCT-ID and X-POSTHOG-SESSION-ID request headers in CORS.
 */

export const DEFAULT_API_HOST = "https://eu.i.posthog.com";

/** The subset of posthog-js this package uses (lets apps pass the real instance and tests pass a fake). */
export interface PostHogLike {
  init(token: string, config: Record<string, unknown>): unknown;
  register(properties: Record<string, unknown>): void;
  identify(distinctId: string, properties?: Record<string, unknown>): void;
  reset(): void;
}

export interface AnalyticsConfig {
  /** kebab-case, identical to the backend's APP_NAME. */
  appName: string;
  /** Public project token (phc_...). Without it nothing is sent. */
  token: string | undefined | null;
  environment?: string;
  /** PostHog ingestion host; defaults to the EU region. */
  apiHost?: string;
  /** The app's own API hosts (URLs or hostnames) that should receive tracing headers. */
  apiHosts?: string[];
  /** Extra posthog-js options, e.g. { disable_session_recording: true }. */
  options?: Record<string, unknown>;
}

export interface Analytics {
  readonly enabled: boolean;
  /** Link this browser to the signed-in user, using the same `app:id` as the backend. */
  identify(userId: string | number, personProperties?: Record<string, unknown>): void;
  /** Forget the user on sign-out; app tagging is kept. */
  reset(): void;
}

const APP_NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function namespacedUserId(appName: string, userId: string | number | null | undefined): string | null {
  if (userId === null || userId === undefined) return null;
  const raw = String(userId).trim();
  if (!raw) return null;
  const prefix = `${appName}:`;
  return raw.startsWith(prefix) ? raw : prefix + raw;
}

/**
 * Stable opaque id for apps that know users only by email: first 16 hex chars of sha256(trimmed, lower-case).
 * Same value as the Python package's `pseudonymous_id`. Needs a secure context (https or localhost).
 */
export async function pseudonymousId(value: string | null | undefined): Promise<string | null> {
  const normalised = (value ?? "").trim().toLowerCase();
  if (!normalised) return null;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(normalised));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
}

/** tracing_headers matches bare hostnames: no protocol, port or path. */
export function toHostname(value: string): string {
  const trimmed = value.trim();
  try {
    return new URL(trimmed.includes("://") ? trimmed : `http://${trimmed}`).hostname;
  } catch {
    return trimmed;
  }
}

const disabled: Analytics = { enabled: false, identify() {}, reset() {} };

export function initAnalytics(posthog: PostHogLike, config: AnalyticsConfig): Analytics {
  const { appName } = config;
  if (!APP_NAME.test(appName)) {
    throw new Error(`app name "${appName}" must be kebab-case, e.g. "creator-curation"`);
  }
  if (!config.token) return disabled;

  const tags = { app_name: appName, environment: config.environment || "production" };
  posthog.init(config.token, {
    api_host: config.apiHost || DEFAULT_API_HOST,
    person_profiles: "identified_only",
    capture_pageview: "history_change",
    // Uncaught errors and unhandled promise rejections go to PostHog Error Tracking (not console.error calls).
    capture_exceptions: true,
    tracing_headers: (config.apiHosts ?? []).map(toHostname),
    ...config.options,
  });
  posthog.register(tags);

  return {
    enabled: true,
    identify(userId, personProperties) {
      const id = namespacedUserId(appName, userId);
      if (id) posthog.identify(id, personProperties);
    },
    reset() {
      posthog.reset();
      posthog.register(tags);
    },
  };
}
