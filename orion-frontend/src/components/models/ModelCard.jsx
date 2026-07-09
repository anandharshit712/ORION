// ORION — ModelCard
// Model panel (ORION_UI_DESIGN.md §11.4): name, type chip (built-in/uploaded/docker),
// mono id, created date in .num. Presentational only — no data wiring.

import Icon from '../common/Icon';
import './ModelCard.css';

const TYPE_CHIP = {
  builtin: 'chip-done',
  'built-in': 'chip-done',
  uploaded: 'chip-running',
  docker: 'chip-queued',
};

const TYPE_LABEL = {
  builtin: 'BUILT-IN',
  'built-in': 'BUILT-IN',
  uploaded: 'UPLOADED',
  docker: 'DOCKER',
};

function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toISOString().slice(0, 10);
}

/**
 * ModelCard
 *
 * Props:
 *   name        string — model name
 *   type        'builtin' | 'uploaded' | 'docker'
 *   id          string — model id / UUID (mono)
 *   createdAt   string | Date — creation timestamp (.num date)
 *   composite   number — last-run composite score (optional, .num)
 *   onSelect    fn     — card click handler (optional)
 */
export default function ModelCard({ name, type = 'builtin', id, createdAt, composite, onSelect }) {
  const chipClass = TYPE_CHIP[type] || 'chip-queued';
  const chipLabel = TYPE_LABEL[type] || String(type).toUpperCase();
  const interactive = typeof onSelect === 'function';

  return (
    <div
      className={`model-card panel ${interactive ? 'is-clickable' : ''}`}
      onClick={interactive ? onSelect : undefined}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === 'Enter') onSelect(); } : undefined}
    >
      <div className="model-card-head">
        <span className="model-mark" aria-hidden="true">
          <Icon name="models" size={18} />
        </span>
        <span className={`chip ${chipClass}`}>{chipLabel}</span>
      </div>

      <h3 className="model-name">{name || 'Untitled Model'}</h3>
      <div className="model-id num" title={id}>{id || '—'}</div>

      <div className="model-meta">
        <div className="model-meta-cell">
          <span className="mono-label">Created</span>
          <span className="num">{fmtDate(createdAt)}</span>
        </div>
        {typeof composite === 'number' && (
          <div className="model-meta-cell">
            <span className="mono-label">Composite</span>
            <span className="num model-score">{composite.toFixed(1)}</span>
          </div>
        )}
      </div>
    </div>
  );
}
