import { useCallback, useEffect, useState } from "react";

import { api, HttpError, type Status } from "./api";
import { AppPage } from "./pages/AppPage";
import { Overview } from "./pages/Overview";

const RANGES = [7, 30, 45, 90];
const ENVIRONMENTS = [
  { value: "production", label: "Production" },
  { value: "development", label: "Development" },
];

type Session = { kind: "loading" } | { kind: "setup"; status: Status } | { kind: "signed-out" } | { kind: "error" } | { kind: "in"; email: string; authDisabled: boolean };

function readLocation() {
  const url = new URL(window.location.href);
  const range = Number(url.searchParams.get("range"));
  const match = /^\/apps\/([a-z0-9-]+)\/?$/.exec(url.pathname);
  const env = url.searchParams.get("env");
  return {
    range: RANGES.includes(range) ? range : 30,
    env: ENVIRONMENTS.some((e) => e.value === env) ? env! : "production",
    app: match ? match[1]! : null,
    auth: url.searchParams.get("auth"),
  };
}

export function App() {
  const [session, setSession] = useState<Session>({ kind: "loading" });
  const [loc, setLoc] = useState(readLocation);

  const navigate = useCallback((path: string) => {
    window.history.pushState(null, "", path);
    setLoc(readLocation());
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    const onPop = () => setLoc(readLocation());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const status = await api.status();
        if (!status.configured) return setSession({ kind: "setup", status });
        const me = await api.me();
        setSession({ kind: "in", email: me.email, authDisabled: me.auth_disabled });
      } catch (e) {
        setSession(e instanceof HttpError && e.status === 401 ? { kind: "signed-out" } : { kind: "error" });
      }
    })();
  }, []);

  if (session.kind === "loading") return <main className="center muted">Loading…</main>;
  if (session.kind === "error")
    return (
      <main className="center">
        <div className="card">
          <h1>Monk-E admin</h1>
          <p>The admin server didn't answer. Reload the page in a moment.</p>
        </div>
      </main>
    );
  if (session.kind === "setup") return <Setup status={session.status} />;
  if (session.kind === "signed-out") return <SignIn outcome={loc.auth} />;

  const path = (range: number, env: string) =>
    `${loc.app ? `/apps/${loc.app}` : "/"}?range=${range}&env=${env}`;

  return (
    <>
      <header className="topbar">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/?range=${loc.range}&env=${loc.env}`);
          }}
        >
          Monk-E admin
        </a>
        <div className="range" role="radiogroup" aria-label="Date range">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              role="radio"
              aria-checked={loc.range === r}
              className={loc.range === r ? "range-option active" : "range-option"}
              onClick={() => navigate(path(r, loc.env))}
            >
              {r} days
            </button>
          ))}
        </div>
        <div className="range" role="radiogroup" aria-label="Environment">
          {ENVIRONMENTS.map((e) => (
            <button
              key={e.value}
              type="button"
              role="radio"
              aria-checked={loc.env === e.value}
              className={
                loc.env === e.value ? `range-option active${e.value === "development" ? " dev" : ""}` : "range-option"
              }
              onClick={() => navigate(path(loc.range, e.value))}
            >
              {e.label}
            </button>
          ))}
        </div>
        <div className="user">
          <span className="muted">{session.authDisabled ? "Sign-in off (local)" : session.email}</span>
          {!session.authDisabled ? (
            <button
              type="button"
              className="link-button"
              onClick={async () => {
                await api.logout();
                setSession({ kind: "signed-out" });
              }}
            >
              Sign out
            </button>
          ) : null}
        </div>
      </header>
      <main className="page">
        {loc.env === "development" ? (
          <p className="dev-banner" role="status">
            Showing development data: events sent from local machines with APP_ENV=development.
          </p>
        ) : null}
        {loc.app ? (
          <AppPage key={loc.app} name={loc.app} range={loc.range} env={loc.env} navigate={navigate} />
        ) : (
          <Overview range={loc.range} env={loc.env} navigate={navigate} />
        )}
      </main>
    </>
  );
}

function SignIn({ outcome }: { outcome: string | null }) {
  return (
    <main className="center">
      <div className="card">
        <h1>Monk-E admin</h1>
        <p>Usage, errors and LLM cost for every Monk-E app.</p>
        {outcome === "denied" ? (
          <p className="state-error" role="alert">
            That Google account isn't on the access list. Ask the tech team to add your email to ADMIN_EMAILS.
          </p>
        ) : outcome === "failed" ? (
          <p className="state-error" role="alert">
            Sign-in didn't complete. Try again.
          </p>
        ) : null}
        <a className="button button-primary" href="/api/auth/google/start">
          Sign in with Google
        </a>
      </div>
    </main>
  );
}

function Setup({ status }: { status: Status }) {
  return (
    <main className="center">
      <div className="card">
        <h1>Monk-E admin isn't set up yet</h1>
        <p>Set these environment variables on the admin service, then reload:</p>
        <ul className="missing">
          {status.missing.map((m) => (
            <li key={m}>
              <code>{m}</code>
            </li>
          ))}
        </ul>
        <p className="muted">See docs/SETUP_LINKS.md in the monke-observability repo for where each value comes from.</p>
      </div>
    </main>
  );
}
