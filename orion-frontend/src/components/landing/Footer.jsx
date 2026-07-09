import { Link } from 'react-router-dom';
import { BUILD_HASH } from '../../utils/constants';
import './Footer.css';

const columns = [
  {
    title: 'Platform',
    links: [
      { label: 'Features', href: '#features' },
      { label: 'Determinism', href: '#stats' },
      { label: 'Dashboard', to: '/dashboard' },
    ],
  },
  {
    title: 'Scenarios',
    links: [
      { label: 'LON · LAT · INT', href: '#features' },
      { label: 'VRU · EMG · MLT', href: '#features' },
    ],
  },
  {
    title: 'Account',
    links: [
      { label: 'Sign in', to: '/login' },
      { label: 'Start Evaluating', to: '/signup' },
    ],
  },
];

export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="footer" id="footer">
      <div className="footer-inner">
        <div className="footer-cols">
          <div className="footer-brand-col">
            <span className="footer-brand">
              <span className="footer-mark" aria-hidden="true" />
              ORION<b>//</b>AREP
            </span>
            <p className="footer-tagline">
              Robustness, measured. A test harness — not a simulator.
            </p>
          </div>

          {columns.map((col) => (
            <nav className="footer-col" key={col.title} aria-label={col.title}>
              <div className="footer-col-title mono-label">{col.title}</div>
              <ul>
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.to ? (
                      <Link to={l.to} className="footer-link">{l.label}</Link>
                    ) : (
                      <a href={l.href} className="footer-link">{l.label}</a>
                    )}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="footer-systemline">
          <span>ORION<b>//</b>AREP</span>
          <span className="footer-dot">·</span>
          <span>DETERMINISTIC dt=<span className="num">0.02s</span></span>
          <span className="footer-dot">·</span>
          <span>BUILD <span className="num">{BUILD_HASH}</span></span>
          <span className="footer-dot">·</span>
          <span>© <span className="num">{year}</span> BEAMHASH</span>
        </div>
      </div>
    </footer>
  );
}
