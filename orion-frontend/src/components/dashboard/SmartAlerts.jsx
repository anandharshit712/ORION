// ORION — SmartAlerts  [P2]
// Stack of inline alert banners (§9.11): 2px left accent border by severity,
// mono-label title + Saira body, optional warning glyph + dismiss control.
// Visual styling per Mission Control; data wiring tracked separately.

import Icon from '../common/Icon';
import './SmartAlerts.css';

const SEVERITIES = ['info', 'warn', 'error', 'success'];

/**
 * SmartAlerts — proactive insight / regression banners.
 *
 * Props (optional):
 *   alerts     [{ id?, severity, title, body? }] — placeholder when absent.
 *              severity ∈ info(cyan) | warn(amber) | error(fail) | success(pass)
 *   onDismiss  (id|index) => void  — close handler; close button shown when set
 */
export default function SmartAlerts({ alerts, onDismiss } = {}) {
  const hasData = Array.isArray(alerts) && alerts.length > 0;

  if (!hasData) {
    return (
      <div className="panel smart-alerts-empty">
        <span className="mono-label">No active alerts</span>
        <p>Regression warnings and suggestions surface here when detected.</p>
      </div>
    );
  }

  return (
    <div className="smart-alerts" role="status" aria-live="polite">
      {alerts.map((a, i) => {
        const severity = SEVERITIES.includes(a.severity) ? a.severity : 'info';
        const key = a.id ?? i;
        return (
          <div className={`smart-alert alert--${severity}`} key={key}>
            {(severity === 'warn' || severity === 'error') && (
              <span className="smart-alert-icon"><Icon name="warning" size={16} /></span>
            )}
            <div className="smart-alert-body">
              <span className="mono-label smart-alert-title">{a.title}</span>
              {a.body && <p>{a.body}</p>}
            </div>
            {onDismiss && (
              <button
                type="button"
                className="smart-alert-close"
                aria-label="Dismiss alert"
                onClick={() => onDismiss(a.id ?? i)}
              >
                <Icon name="close" size={14} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
