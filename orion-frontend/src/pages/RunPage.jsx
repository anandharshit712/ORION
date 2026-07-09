// ORION — RunPage  [stub, deferred Phase 2.5 deterministic replay]
// Route: /dashboard/runs/:id — single run detail (scores, event log, replay link).
// Visual placeholder in the Mission Control language; data wiring out of scope.

import { Link } from 'react-router-dom';
import Icon from '../components/common/Icon';
import './RunPage.css';

export default function RunPage() {
  return (
    <div className="runpage" id="run-page">
      <div className="panel runpage-card">
        <span className="mono-label">Run Detail · deferred</span>
        <h1>Deterministic Replay</h1>
        <p>
          Per-run scores, event log, and frame-accurate replay surface here once the
          replay engine (frame-hash determinism, Phase 2.5) lands. The visual language
          is ready; data wiring is tracked separately.
        </p>
        <Link to="/dashboard" className="btn btn-ghost btn-sm">
          <Icon name="chevron-right" size={14} className="flip" /> Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
