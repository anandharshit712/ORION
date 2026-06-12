import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../services/api';
import Navbar from '../components/common/Navbar';
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
        <div className="auth-container">
          <div className="auth-card glass-card">
            <div className="auth-header">
              <span className="brand-icon">◆</span>
              <h2>Invalid Link</h2>
              <p>This reset link is missing or malformed.</p>
            </div>
            <div className="auth-error">Invalid or missing reset link.</div>
            <p className="auth-footer-text">
              <Link to="/login">Back to Login</Link>
            </p>
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
      <div className="auth-container">
        <div className="auth-card glass-card">
          <div className="auth-header">
            <span className="brand-icon">◆</span>
            <h2>Reset Password</h2>
            <p>Enter your new password below</p>
          </div>

          {success ? (
            <div className="rp-success">
              <p>Password updated successfully. You can now log in.</p>
              <Link to="/login" className="btn btn-primary btn-lg rp-go-login">
                Go to Login
              </Link>
            </div>
          ) : (
            <>
              {error && <div className="auth-error">{error}</div>}
              <form onSubmit={handleSubmit} className="auth-form">
                <div className="form-group">
                  <label className="form-label">New Password</label>
                  <input
                    type="password"
                    className="input-field"
                    placeholder="••••••••"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Confirm Password</label>
                  <input
                    type="password"
                    className="input-field"
                    placeholder="••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </div>
                <button
                  type="submit"
                  className="btn btn-primary btn-lg auth-submit"
                  disabled={loading}
                >
                  {loading ? 'Updating…' : 'Reset Password'}
                </button>
              </form>
              <p className="auth-footer-text">
                <Link to="/login">Back to Login</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}
