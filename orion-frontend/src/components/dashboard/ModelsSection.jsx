// ORION — ModelsSection
//
// Model panels (docs/UI_DESIGN.md §11.4) over GET /api/models/, the customer
// model registry from P1.2. Renders the existing presentational ModelCard
// rather than a second card implementation.
//
// Two things the API shape makes non-obvious:
//   - submission_type is "cloudpickle" or "docker"; ModelCard speaks
//     builtin/uploaded/docker, so the two are mapped here rather than widening
//     the card's vocabulary.
//   - a model row carries `status` and `error`. A model that failed to register
//     still lists, because a customer whose upload broke needs to see it said
//     so — hiding it would look like the upload silently vanished.

import { useMemo, useState } from 'react';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import ModelCard from '../models/ModelCard';
import DataStates from './DataStates';
import './ModelsSection.css';

/** Registry submission_type → the vocabulary ModelCard renders. */
const CARD_TYPE = {
  cloudpickle: 'uploaded',
  pickle: 'uploaded',
  upload: 'uploaded',
  docker: 'docker',
  builtin: 'builtin',
};

const BUILTIN_MODELS = ['EmergencyBrake', 'ConstantAction', 'SimpleLaneKeep', 'Random'];

function bytes(n) {
  if (typeof n !== 'number' || n <= 0) return null;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ModelsSection() {
  const [selected, setSelected] = useState(null);
  const { data, loading, error, refresh } = useApiData(() => api.getModels(), []);
  const models = useMemo(() => asList(data, 'models'), [data]);

  const detail = useMemo(
    () => models.find((m) => m.id === selected) || null,
    [models, selected],
  );

  return (
    <section className="models-section">
      <div className="section-bar">
        <span className="mono-label">
          Submitted models · /api/models <span className="num">{models.length}</span>
        </span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={refresh} disabled={loading}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      <DataStates
        loading={loading}
        error={error}
        isEmpty={models.length === 0}
        onRetry={refresh}
        loadingRows={3}
        loadingLabel="Loading models"
        emptyLabel="No submitted models"
        emptyHint="Upload a model with the orion CLI or register a Docker image. The built-in models below are always available."
      >
        <div className="model-grid">
          {models.map((m) => (
            <ModelCard
              key={m.id}
              name={`${m.name}@${m.version}`}
              type={CARD_TYPE[m.submission_type] || 'docker'}
              id={m.id}
              createdAt={m.created_at}
              onSelect={() => setSelected(m.id === selected ? null : m.id)}
            />
          ))}
        </div>
      </DataStates>

      {detail && (
        <div className="panel model-detail">
          <div className="model-detail-head">
            <span className="mono-label">{detail.name}@{detail.version}</span>
            <span className={`chip ${detail.status === 'ready' ? 'chip-done' : 'chip-queued'}`}>
              {detail.status}
            </span>
          </div>
          <dl className="model-detail-grid">
            <div><dt className="mono-label">ID</dt><dd className="num">{detail.id}</dd></div>
            <div><dt className="mono-label">Type</dt><dd className="num">{detail.submission_type}</dd></div>
            {bytes(detail.size_bytes) && (
              <div><dt className="mono-label">Size</dt><dd className="num">{bytes(detail.size_bytes)}</dd></div>
            )}
            {detail.content_hash && (
              <div className="is-wide">
                <dt className="mono-label">SHA-256</dt>
                <dd className="num model-hash" title={detail.content_hash}>{detail.content_hash}</dd>
              </div>
            )}
          </dl>
          {detail.error && (
            <div className="model-detail-error">
              <Icon name="warning" size={13} /> {detail.error}
            </div>
          )}
        </div>
      )}

      <div className="panel builtin-panel">
        <div className="mono-label">Built-in models</div>
        <p className="builtin-hint">
          Always available to every org, no upload required. Referenced by name in
          <code> POST /api/runs/</code>.
        </p>
        <div className="builtin-list">
          {BUILTIN_MODELS.map((name) => (
            <span key={name} className="chip chip-done">{name}</span>
          ))}
        </div>
      </div>
    </section>
  );
}
