// ORION — ErrorBoundary
// App-level guard: render faults show a themed instrument panel, never a white screen.
// See ORION_UI_DESIGN.md §9.12 / §11.6.

import { Component } from 'react';
import Icon from './Icon';
import './ErrorBoundary.css';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface in console for diagnosis; no external logging wired here.
    // eslint-disable-next-line no-console
    console.error('ORION ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="errboundary">
          <div className="panel errboundary-card">
            <span className="mono-label errboundary-eyebrow">
              <Icon name="warning" size={14} /> System Fault
            </span>
            <div className="errboundary-code num">500</div>
            <p>An unexpected error interrupted the interface.</p>
            <pre className="errboundary-detail num">
              {String(this.state.error?.message || this.state.error)}
            </pre>
            <div className="errboundary-actions">
              <button className="btn btn-primary" onClick={() => window.location.reload()}>
                <Icon name="refresh" size={14} /> Reload
              </button>
              <a className="btn btn-ghost" href="/">Home</a>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
