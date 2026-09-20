// ORION — VerifyEmailPage  [Phase 0.4 / D-04]
// Route: /verify-email?token=...  (public)
//
// This is where the link in the verification email lands. Without it the email
// pointed at a route that did not exist, so every verification attempt hit the
// 404 page — the backend flow was complete and unreachable.

import React, { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import './ResetPasswordPage.css';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [status, setStatus] = useState(token ? 'verifying' : 'missing');
  const [message, setMessage] = useState('');
  // React 18 StrictMode mounts effects twice in development. The token is
  // single-use, so a second call would always report "invalid or expired" and
  // make a successful verification look broken.
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || attempted.current) return;
    attempted.current = true;

    api.verifyEmail(token)
      .then((res) => {
        setStatus('verified');
        setMessage(res?.message || 'Email verified.');
      })
      .catch((err) => {
        setStatus('failed');
        setMessage(err.message || 'That link is no longer valid.');
      });
  }, [token]);

  return (
    <div className="auth-page">
      <div className="panel auth-card">
        <h1>Verify email</h1>

        {status === 'missing' && (
          <>
            <p className="auth-error">This link is missing its token.</p>
            <p>
              Open the link from the verification email directly, or request a new
              one from the login screen.
            </p>
          </>
        )}

        {status === 'verifying' && (
          <p className="mono-label">Verifying…</p>
        )}

        {status === 'verified' && (
          <>
            <p>{message}</p>
            <p>You can now start evaluation runs, create API keys and upload models.</p>
            <Link className="btn-primary" to="/login">Go to Login</Link>
          </>
        )}

        {status === 'failed' && (
          <>
            <p className="auth-error">{message}</p>
            <p>
              Verification links expire after 24 hours and can only be used once.
              Request a fresh one and try again.
            </p>
            <Link className="btn-ghost" to="/login">Back to Login</Link>
          </>
        )}
      </div>
    </div>
  );
}
