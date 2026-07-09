import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../services/api';
import Navbar from '../components/common/Navbar';
import Icon from '../components/common/Icon';
import '../components/auth/AuthForms.css';
import './ResetPasswordPage.css';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  if (!token) {
    return (
      <>
        <Navbar />
        <div className="auth-shell">
          <div className="auth-wrap rp-wrap">
            <div className="auth-head">
              <span className="sect-idx">02 /</span>
              <h1>Authentication · Reset</h1>
              <span className="meta">password recovery</span>
            </div>
            <div className="panel auth-card auth-card--error">
              <div className="mono-label eyebrow">ORION//AREP · LINK INVALID</div>
              <h2>Invalid link</h2>
              <div className="auth-alert auth-alert--fail" role="alert">
                <Icon name="warning" size={15} />
                <span>Invalid or missing reset link.</span>
              </div>
              <div className="auth-foot">
                <Link to="/login">← Back to Login</Link>
              </div>
            </div>
          </div>
        </div>
      </>
    );
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!newPassword || !confirmPassword) {
      setError('Both fields are required.');
      return;
    }
    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await api.resetPassword(token, newPassword);
      setSuccess(true);
    } catch (err) {
      setError(err.message || 'Reset failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Navbar />
      <div className="auth-shell">
        <div className="auth-wrap rp-wrap">
          <div className="auth-head">
            <span className="sect-idx">02 /</span>
            <h1>Authentication · Reset</h1>
            <span className="meta">password recovery</span>
          </div>

          <div className="panel panel--live auth-card">
            <div className="mono-label eyebrow">ORION//AREP · SECURE</div>
            <h2>Reset password</h2>

            {success ? (
              <div className="auth-success">
                <div className="auth-alert auth-alert--pass" role="status">
                  <Icon name="check" size={15} />
                  <span>Password updated successfully. You can now log in.</span>
                </div>
                <Link to="/login" className="btn btn-primary">
                  Go to Login <span className="arr">→</span>
                </Link>
              </div>
            ) : (
              <>
                {error && (
                  <div className="auth-alert auth-alert--fail" role="alert">
                    <Icon name="warning" size={15} />
                    <span>{error}</span>
                  </div>
                )}
                <form onSubmit={handleSubmit} className="auth-form">
                  <div className="field">
                    <label htmlFor="rp-new">New Password</label>
                    <input
                      type="password"
                      id="rp-new"
                      placeholder="••••••••••••"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="rp-confirm">Confirm Password</label>
                    <input
                      type="password"
                      id="rp-confirm"
                      placeholder="••••••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                    />
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={loading}>
                    {loading ? 'Updating…' : 'Reset Password'} <span className="arr">→</span>
                  </button>
                </form>
                <div className="auth-foot">
                  <Link to="/login">← Back to Login</Link>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
