import { formatIst } from "../lib/format";

export function PageActions({
  data,
  loading,
  onRefresh,
}: {
  data: { generated_at: string; refresh_throttled: boolean } | undefined;
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="page-actions">
      <span className="muted" aria-live="polite">
        {loading
          ? "Updating…"
          : data?.refresh_throttled
            ? "Refreshed less than a minute ago; showing the saved figures."
            : data
              ? `Figures from ${formatIst(data.generated_at)} IST, kept for 5 minutes`
              : null}
      </span>
      <button type="button" className="button" onClick={onRefresh} disabled={loading}>
        Refresh
      </button>
    </div>
  );
}

export function LoadFailure({ failure, onRetry }: { failure: number | "network"; onRetry: () => void }) {
  const message =
    failure === 401
      ? "Your session has ended. Sign in again."
      : failure === 404
        ? "There is no app with that name."
        : failure === "network"
          ? "The admin server didn't answer. Check your connection and try again."
          : `The admin server returned an error (HTTP ${failure}).`;
  return (
    <div className="notice" role="alert">
      <p>{message}</p>
      {failure === 401 ? (
        <a className="button" href="/api/auth/google/start">
          Sign in with Google
        </a>
      ) : failure !== 404 ? (
        <button type="button" className="button" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}
