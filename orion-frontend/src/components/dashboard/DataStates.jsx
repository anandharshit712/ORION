// ORION — DataStates
//
// The loading / empty / error trio docs/UI_DESIGN.md §9.12 makes mandatory for
// every data view. Kept in one place so a section cannot ship with two of the
// three: the one that gets skipped is always the error state, and an empty
// table rendered on a 500 reads as "no data" rather than "the request failed".
//
// Loading is skeleton blocks matching the final layout, not a spinner (§9.12).

import Icon from '../common/Icon';
import './DataStates.css';

/** Skeleton rows shaped like the table or grid that will replace them. */
export function LoadingState({ rows = 5, label = 'Loading' }) {
  return (
    <div className="data-state data-state--loading" aria-busy="true" aria-live="polite">
      <span className="mono-label">{label}…</span>
      <div className="skeleton-stack">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="skeleton skeleton-row" />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({ label, hint, action }) {
  return (
    <div className="data-state data-state--empty">
      <span className="mono-label">{label}</span>
      {hint && <p className="data-state-hint">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="data-state data-state--error" role="alert">
      <span className="mono-label">
        <Icon name="warning" size={14} /> Error
      </span>
      <p className="data-state-hint">{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
          <Icon name="refresh" size={14} /> Retry
        </button>
      )}
    </div>
  );
}

/**
 * Render the right state, or the children when there is data.
 *
 * Takes `isEmpty` rather than inspecting `data` itself, because "empty" differs
 * per section — an empty array, a zero count, a missing field.
 */
export default function DataStates({
  loading,
  error,
  isEmpty,
  onRetry,
  loadingRows,
  loadingLabel,
  emptyLabel,
  emptyHint,
  emptyAction,
  children,
}) {
  if (loading) return <LoadingState rows={loadingRows} label={loadingLabel} />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (isEmpty) return <EmptyState label={emptyLabel} hint={emptyHint} action={emptyAction} />;
  return children;
}
