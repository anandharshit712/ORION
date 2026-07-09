import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import Icon from '../common/Icon';
import './AuthForms.css';

export default function LoginForm() {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showForgot, setShowForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotError, setForgotError] = useState('');
  const [forgotSuccess, setForgotSuccess] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleForgot = async (e) => {
    e.preventDefault();
    setForgotError('');
    setForgotLoading(true);
    try {
      await api.forgotPassword(forgotEmail);
    } catch (_) {
      // always show success to avoid email enumeration
    } finally {
      setForgotLoading(false);
      setForgotSuccess(true);
    }
  };

  const openForgot = () => {
    setShowForgot(true);
    setForgotEmail('');
    setForgotError('');
    setForgotSuccess(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(identifier, password);
      navigate('/dashboard');
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-wrap">
        <div className="auth-head">
          <span className="sect-idx">02 /</span>
          <h1>Authentication · Sign In</h1>
          <span className="meta">login · signup · reset share this frame</span>
        </div>

        <div className="auth-grid">
          {/* ── Left aside · access-control telemetry ── */}
          <aside className="panel auth-aside">
            <div>
              <div className="mono-label aside-label">ACCESS CONTROL</div>
              <h2>Operator console.</h2>
              <p className="aside-copy">
                JWT-scoped sessions, org-isolated runs, API keys for the SDK.
                The login, signup, and password-reset screens all inherit this
                instrument frame.
              </p>
            </div>
            <dl className="auth-telem">
              <div className="row"><span className="k">SESSION</span><span className="v">JWT · httpOnly</span></div>
              <div className="row"><span className="k">SCOPE</span><span className="v">org_id + role</span></div>
              <div className="row"><span className="k">RATE LIMIT</span><span className="v num">5 / min / IP</span></div>
              <div className="row"><span className="k">STATUS</span><span className="v">AWAITING AUTH</span></div>
            </dl>
          </aside>

          {/* ── Right card · sign-in form ── */}
          <div className="panel panel--live auth-card">
            <div className="mono-label eyebrow">ORION//AREP · SECURE</div>
            <h2>Sign in</h2>

            {error && (
              <div className="auth-alert auth-alert--fail" role="alert">
                <Icon name="warning" size={15} />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="auth-form" id="login-form">
              <div className="field">
                <label htmlFor="login-identifier">Email or Username</label>
                <input
                  type="text"
                  placeholder="operator@beamhash.com"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  id="login-identifier"
                />
              </div>
              <div className="field">
                <label htmlFor="login-password">Password</label>
                <div className="auth-input-wrap">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="field-input"
                    placeholder="••••••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    maxLength={72}
                    id="login-password"
                  />
                  <button
                    type="button"
                    className="auth-reveal"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true" focusable="false">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true" focusable="false">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              <div className="auth-row">
                <label className="auth-keep">
                  <input type="checkbox" /> Keep session
                </label>
                <button type="button" className="auth-link" onClick={openForgot}>
                  Forgot password?
                </button>
              </div>

              <button type="submit" className="btn btn-primary" disabled={loading} id="login-submit">
                {loading ? 'Authenticating…' : 'Authenticate'} <span className="arr">→</span>
              </button>
            </form>

            {showForgot && (
              <div className="forgot-panel">
                <div className="mono-label forgot-title">RESET · PASSWORD</div>
                {forgotSuccess ? (
                  <div className="auth-alert auth-alert--pass" role="status">
                    <Icon name="check" size={15} />
                    <span>If that email is registered, a reset link has been sent.</span>
                  </div>
                ) : (
                  <form onSubmit={handleForgot} className="auth-form">
                    {forgotError && (
                      <div className="auth-alert auth-alert--fail" role="alert">
                        <Icon name="warning" size={15} />
                        <span>{forgotError}</span>
                      </div>
                    )}
                    <div className="field">
                      <label htmlFor="forgot-email">Email address</label>
                      <input
                        type="email"
                        id="forgot-email"
                        placeholder="you@example.com"
                        value={forgotEmail}
                        onChange={(e) => setForgotEmail(e.target.value)}
                        required
                        autoFocus
                      />
                    </div>
                    <button type="submit" className="btn btn-primary" disabled={forgotLoading}>
                      {forgotLoading ? 'Sending…' : 'Send Reset Link'} <span className="arr">→</span>
                    </button>
                  </form>
                )}
                <p className="auth-foot">
                  <button type="button" className="auth-link" onClick={() => setShowForgot(false)}>
                    ← Back to login
                  </button>
                </p>
              </div>
            )}

            {!showForgot && (
              <div className="auth-foot">
                No account? <Link to="/signup">Request access →</Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
