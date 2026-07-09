// ORION — ModelsPage  [P1]
// Route: /dashboard/models
// List org models and upload new model via SDK or Docker.
// Visual restyle to "Mission Control" (ORION_UI_DESIGN.md §11.4). Data wiring
// is out of scope — the model list renders the §9.12 empty state until wired.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import ModelUploadForm from '../components/models/ModelUploadForm';
import Icon from '../components/common/Icon';
import './ModelsPage.css';

/**
 * ModelsPage — list org models + register a new model.
 */
export default function ModelsPage() {
  const { user } = useAuth();

  // Data wiring tracked separately — no fetch invented here.
  const models = [];

  return (
    <div className="models-page" id="models-page">
      <header className="models-head">
        <div>
          <h1>Models</h1>
          <div className="models-sub mono-label">
            {models.length} REGISTERED{user?.username ? ` · ORG=${user.username}` : ''}
          </div>
        </div>
      </header>

      <div className="models-layout">
        <section className="models-list-col">
          <div className="models-col-cap mono-label">Registered Models</div>
          {models.length === 0 ? (
            <div className="panel models-empty">
              <span className="mono-label">No models registered</span>
              <p>
                Upload a cloudpickle artefact or register a Docker image to evaluate
                it across the scenario library.
              </p>
            </div>
          ) : (
            <div className="models-grid">
              {/* ModelCard panels render here once wired */}
            </div>
          )}
        </section>

        <aside className="models-form-col">
          <div className="models-col-cap mono-label">
            <Icon name="upload" size={13} /> Register
          </div>
          <ModelUploadForm />
        </aside>
      </div>
    </div>
  );
}
