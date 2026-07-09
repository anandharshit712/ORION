// ORION — AlertBanner
// Inline alert / toast (ORION_UI_DESIGN.md §9.11): 2px left accent border colored
// by severity, --bg-panel surface, mono micro-label title + Saira body.
// Presentational only — no data wiring.

import Icon from './Icon';
import './AlertBanner.css';

const SEVERITIES = ['info', 'warn', 'error', 'success'];

/**
 * AlertBanner
 *
 * Props:
 *   severity   'info' | 'warn' | 'error' | 'success'  (default 'info')
 *   title      string  — mono micro-label (optional)
 *   children   node    — body copy (Saira)
 *   message    string  — body copy alternative to children
 *   onDismiss  fn      — when provided, renders a close button
 *   icon       bool    — show leading warning glyph (default true for warn/error)
 *   className  string
 */
export default function AlertBanner({
  severity = 'info',
  title,
  children,
  message,
  onDismiss,
  icon,
  className = '',
}) {
  const sev = SEVERITIES.includes(severity) ? severity : 'info';
  const showIcon = icon ?? (sev === 'warn' || sev === 'error');
  const body = children ?? message;

  return (
    <div className={`alert-banner alert-${sev} ${className}`} role="status" aria-live="polite">
      {showIcon && (
        <span className="alert-lead" aria-hidden="true">
          <Icon name="warning" size={16} />
        </span>
      )}
      <div className="alert-body">
        {title && <div className="alert-title mono-label">{title}</div>}
        {body && <div className="alert-text">{body}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          className="alert-dismiss"
          onClick={onDismiss}
          aria-label="Dismiss alert"
        >
          <Icon name="close" size={14} />
        </button>
      )}
    </div>
  );
}
