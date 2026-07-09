// ORION — NotFoundPage (404)
// Mounted as the `*` fallback route. Mission Control instrument panel. §11.6.

import { Link } from 'react-router-dom';
import Icon from '../components/common/Icon';
import './NotFoundPage.css';

export default function NotFoundPage() {
  return (
    <div className="notfound" id="notfound-page">
      <div className="panel panel--live notfound-card">
        <span className="mono-label notfound-eyebrow">
          <span className="live-dot" style={{ background: 'var(--fail)', boxShadow: '0 0 8px var(--fail)' }} />
          Signal Lost
        </span>
        <div className="notfound-code num">404</div>
        <p>No telemetry at this coordinate. The requested route does not exist.</p>
        <Link to="/" className="btn btn-primary">
          <Icon name="chevron-right" size={15} /> Return to Base
        </Link>
      </div>
    </div>
  );
}
