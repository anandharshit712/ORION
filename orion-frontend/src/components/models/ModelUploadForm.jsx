// ORION — ModelUploadForm
// Instrument-frame card (ORION_UI_DESIGN.md §11.4): multipart upload + Docker
// register, segmented control to switch modes, .field inputs. Visual-only:
// optional onSubmit prop receives the assembled payload; no api.js wiring here.

import { useState } from 'react';
import Icon from '../common/Icon';
import './ModelUploadForm.css';

const MODES = [
  { key: 'upload', label: 'SDK Upload', icon: 'upload' },
  { key: 'docker', label: 'Docker Image', icon: 'models' },
];

/**
 * ModelUploadForm
 *
 * Props:
 *   onSubmit  fn(payload) — invoked with { mode, name, file? , image?, command? }
 *   submitting bool       — disable controls while a parent request is in flight
 *   error      string     — error message rendered in §9.12 error style
 */
export default function ModelUploadForm({ onSubmit, submitting = false, error }) {
  const [mode, setMode] = useState('upload');
  const [name, setName] = useState('');
  const [file, setFile] = useState(null);
  const [image, setImage] = useState('');
  const [command, setCommand] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (typeof onSubmit !== 'function') return;
    onSubmit(
      mode === 'upload'
        ? { mode, name, file }
        : { mode, name, image, command }
    );
  };

  return (
    <form className="model-upload panel panel--live" onSubmit={handleSubmit} noValidate>
      <div className="model-upload-head">
        <span className="mono-label">Register Model</span>
        <span className="model-upload-sub">Cloudpickle artefact or container image</span>
      </div>

      <div className="model-upload-tabs" role="tablist" aria-label="Registration method">
        {MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            role="tab"
            aria-selected={mode === m.key}
            className={`mu-tab ${mode === m.key ? 'active' : ''}`}
            onClick={() => setMode(m.key)}
            disabled={submitting}
          >
            <Icon name={m.icon} size={14} /> {m.label}
          </button>
        ))}
      </div>

      <div className="model-upload-body">
        <label className="field">
          <span>Model Name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-planner-v2"
            disabled={submitting}
          />
        </label>

        {mode === 'upload' ? (
          <label className="field">
            <span>Artefact (.pkl)</span>
            <input
              type="file"
              accept=".pkl,.cloudpkl"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              disabled={submitting}
            />
          </label>
        ) : (
          <>
            <label className="field">
              <span>Image Reference</span>
              <input
                type="text"
                value={image}
                onChange={(e) => setImage(e.target.value)}
                placeholder="registry.example.com/model:tag"
                disabled={submitting}
              />
            </label>
            <label className="field">
              <span>Entry Command</span>
              <input
                type="text"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="python -m model.serve"
                disabled={submitting}
              />
            </label>
          </>
        )}
      </div>

      {error && (
        <div className="model-upload-error">
          <span className="mono-label"><Icon name="warning" size={13} /> Error</span>
          <span>{error}</span>
        </div>
      )}

      <button type="submit" className="btn btn-primary model-upload-submit" disabled={submitting}>
        {submitting ? 'Registering…' : <><Icon name={mode === 'upload' ? 'upload' : 'models'} size={15} /> Register</>}
      </button>
    </form>
  );
}
