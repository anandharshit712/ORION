// ORION — PlanCard
// Plan panel (ORION_UI_DESIGN.md §11.4): mono .num price, feature list, CTA .btn.
// .panel--live marks the current/featured plan. Presentational only.

import Icon from '../common/Icon';
import './PlanCard.css';

/**
 * PlanCard
 *
 * Props:
 *   name      string   — plan name (Chakra Petch title)
 *   price     number|string — monthly price (mono .num); pass string for 'Custom'
 *   period    string   — e.g. '/mo' (default)
 *   features  string[] — feature bullet list
 *   current   bool     — this is the org's active plan (renders .panel--live + badge)
 *   featured  bool     — visually highlight (instrument-frame emphasis)
 *   ctaLabel  string   — button text (default derived from current)
 *   onSelect  fn       — CTA click handler
 *   disabled  bool     — disable CTA
 */
export default function PlanCard({
  name,
  price,
  period = '/mo',
  features = [],
  current = false,
  featured = false,
  ctaLabel,
  onSelect,
  disabled = false,
}) {
  const showPrice = typeof price === 'number' ? `$${price.toLocaleString()}` : price;
  const label = ctaLabel ?? (current ? 'Current Plan' : 'Select Plan');

  return (
    <div className={`plan-card panel ${current ? 'panel--live' : ''} ${featured ? 'is-featured' : ''}`}>
      <div className="plan-head">
        <span className="mono-label">Plan</span>
        {current && <span className="chip chip-running">Active</span>}
      </div>
      <h3 className="plan-name">{name}</h3>
      <div className="plan-price">
        <span className="plan-amount num">{showPrice}</span>
        {typeof price === 'number' && <span className="plan-period num">{period}</span>}
      </div>

      <ul className="plan-features">
        {features.map((f, i) => (
          <li key={i}>
            <Icon name="check" size={14} className="plan-check" />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className={`btn ${current ? 'btn-ghost' : 'btn-primary'} plan-cta`}
        onClick={onSelect}
        disabled={disabled || current}
      >
        {label}
        {!current && <span className="arr">→</span>}
      </button>
    </div>
  );
}
