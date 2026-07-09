import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Icon from '../common/Icon';
import './AuthForms.css';

export default function SignupForm() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const { register, login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await register(email, username, password, fullName);
      await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      setError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-wrap">
        <div className="auth-head">
          <span className="sect-idx">02 /</span>
          <h1>Authentication · Request Access</h1>
          <span className="meta">login · signup · reset share this frame</span>
        </div>

        <div className="auth-grid">
          {/* ── Left aside · access-control telemetry ── */}
          <aside className="panel auth-aside">
            <div>
              <div className="mono-label aside-label">ACCESS CONTROL</div>
              <h2>Provision an operator.</h2>
              <p className="aside-copy">
                Each account is scoped to an organisation with isolated runs and
                credits. Provision once, then drive evaluations from the dashboard
                or the SDK.
              </p>
            </div>
            <dl className="auth-telem">
              <div className="row"><span className="k">SESSION</span><span className="v">JWT · httpOnly</span></div>
              <div className="row"><span className="k">SCOPE</span><span className="v">org_id + role</span></div>
              <div className="row"><span className="k">PASSWORD</span><span className="v num">6–72 chars</span></div>
              <div className="row"><span className="k">STATUS</span><span className="v">AWAITING SIGNUP</span></div>
            </dl>
          </aside>

          {/* ── Right card · signup form ── */}
          <div className="panel panel--live auth-card">
            <div className="mono-label eyebrow">ORION//AREP · ENROLL</div>
            <h2>Create account</h2>

            {error && (
              <div className="auth-alert auth-alert--fail" role="alert">
                <Icon name="warning" size={15} />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="auth-form" id="signup-form">
              <div className="field">
                <label htmlFor="signup-fullname">Full Name</label>
                <input
                  type="text"
                  placeholder="Jane Operator"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  id="signup-fullname"
                />
              </div>
              <div className="field">
                <label htmlFor="signup-username">Username</label>
                <input
                  type="text"
                  placeholder="janeop"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  id="signup-username"
                />
              </div>
              <div className="field">
                <label htmlFor="signup-email">Email</label>
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  id="signup-email"
                />
              </div>
              <div className="field">
                <label htmlFor="signup-password">Password</label>
                <div className="auth-input-wrap">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="field-input"
                    placeholder="Min 6, Max 72 chars"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={6}
                    maxLength={72}
                    id="signup-password"
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
              <p className="auth-hint">MUST BE 6–72 CHARACTERS.</p>

              <button type="submit" className="btn btn-primary" disabled={loading} id="signup-submit">
                {loading ? 'Provisioning…' : 'Create Account'} <span className="arr">→</span>
              </button>
            </form>

            <div className="auth-foot">
              Already have an account? <Link to="/login">Sign in →</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
