import type { ReactNode } from "react";

import type { Panel } from "../api";
import { errorMessage } from "../lib/format";

interface Props<T> {
  title: string;
  panel: Panel<T> | undefined;
  empty: string;
  note?: ReactNode;
  onRetry?: () => void;
  wide?: boolean;
  children: (data: T) => ReactNode;
}

/** One figure or table: loading, empty and error are each shown explicitly, never as zero. */
export function PanelBox<T>({ title, panel, empty, note, onRetry, wide, children }: Props<T>) {
  return (
    <section className={wide ? "panel panel-wide" : "panel"} aria-busy={panel === undefined}>
      <header className="panel-head">
        <h2>{title}</h2>
        {note ? <p className="panel-note">{note}</p> : null}
      </header>
      {panel === undefined ? (
        <p className="state state-loading">Loading…</p>
      ) : panel.status === "error" ? (
        <div className="state state-error" role="alert">
          <p>{errorMessage(panel.error)}</p>
          {onRetry ? (
            <button type="button" className="link-button" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      ) : panel.status === "empty" ? (
        <p className="state">{empty}</p>
      ) : (
        children(panel.data)
      )}
    </section>
  );
}
