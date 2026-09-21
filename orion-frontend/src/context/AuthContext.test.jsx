// AuthContext tests (Phase 2).
//
// Since D-04 the page holds no token: the session is an httpOnly cookie it
// cannot read, so auth state is *derived* from GET /api/auth/me on mount. That
// makes the bootstrap load-bearing in a way a token in localStorage never was
// — if it stops running, every refresh logs the user out, and nothing throws.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';

import { AuthProvider, useAuth } from './AuthContext';
import { api } from '../services/api';

function Probe() {
  const { user, loading, isAuthenticated, isVerified } = useAuth();
  if (loading) return <span>loading</span>;
  return (
    <div>
      <span data-testid="auth">{String(isAuthenticated)}</span>
      <span data-testid="verified">{String(isVerified)}</span>
      <span data-testid="email">{user?.email ?? 'none'}</span>
    </div>
  );
}

const VERIFIED_USER = {
  id: 1, email: 'a@example.com', username: 'a', email_verified: true,
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('bootstrap', () => {
  it('asks the server who we are on mount', async () => {
    const getMe = vi.spyOn(api, 'getMe').mockResolvedValue(VERIFIED_USER);

    render(<AuthProvider><Probe /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('true'));
    expect(getMe).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('email')).toHaveTextContent('a@example.com');
  });

  it('treats a 401 as logged out rather than an error', async () => {
    // Every first-time visitor hits this path; it must not surface as a fault.
    vi.spyOn(api, 'getMe').mockRejectedValue(new Error('Invalid or expired token'));

    render(<AuthProvider><Probe /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('false'));
    expect(screen.getByTestId('email')).toHaveTextContent('none');
  });

  it('shows loading until the bootstrap settles', async () => {
    let release;
    vi.spyOn(api, 'getMe').mockReturnValue(new Promise((r) => { release = r; }));

    render(<AuthProvider><Probe /></AuthProvider>);
    expect(screen.getByText('loading')).toBeInTheDocument();

    await act(async () => { release(VERIFIED_USER); });
    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('true'));
  });
});

describe('verification state', () => {
  it('reports an unverified account as not verified', async () => {
    vi.spyOn(api, 'getMe').mockResolvedValue({ ...VERIFIED_USER, email_verified: false });

    render(<AuthProvider><Probe /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('true'));
    // Signed in, but gated out of runs, keys and uploads.
    expect(screen.getByTestId('verified')).toHaveTextContent('false');
  });

  it('is not verified when logged out', async () => {
    vi.spyOn(api, 'getMe').mockRejectedValue(new Error('401'));

    render(<AuthProvider><Probe /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId('verified')).toHaveTextContent('false'));
  });
});

describe('login and logout', () => {
  function LoginProbe() {
    const { login, logout, isAuthenticated } = useAuth();
    return (
      <div>
        <span data-testid="auth">{String(isAuthenticated)}</span>
        <button onClick={() => login('a@example.com', 'pw')}>in</button>
        <button onClick={() => logout()}>out</button>
      </div>
    );
  }

  it('re-reads the user after logging in rather than trusting the response body', async () => {
    // The login response carries a token for SDK clients. The browser ignores
    // it and reads the session back, because the cookie is what authenticates.
    vi.spyOn(api, 'getMe')
      .mockRejectedValueOnce(new Error('401'))
      .mockResolvedValue(VERIFIED_USER);
    const login = vi.spyOn(api, 'login').mockResolvedValue({ access_token: 'ignored' });

    render(<AuthProvider><LoginProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('false'));

    await act(async () => { screen.getByText('in').click(); });

    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('true'));
    expect(login).toHaveBeenCalledWith('a@example.com', 'pw');
  });

  it('asks the server to clear the cookie on logout', async () => {
    vi.spyOn(api, 'getMe').mockResolvedValue(VERIFIED_USER);
    const logout = vi.spyOn(api, 'logout').mockResolvedValue({ message: 'ok' });

    render(<AuthProvider><LoginProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('true'));

    await act(async () => { screen.getByText('out').click(); });

    // The page cannot delete an httpOnly cookie itself — that is the point.
    expect(logout).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('false'));
  });

  it('logs out locally even when the server call fails', async () => {
    vi.spyOn(api, 'getMe').mockResolvedValue(VERIFIED_USER);
    vi.spyOn(api, 'logout').mockRejectedValue(new Error('network down'));

    render(<AuthProvider><LoginProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('true'));

    await act(async () => { screen.getByText('out').click(); });

    await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('false'));
  });
});

describe('the contract with consumers', () => {
  it('exposes no token', async () => {
    // Components reading a raw token is the defect D-04 closed. If this comes
    // back, something has started keeping a credential in JavaScript again.
    let captured;
    function Capture() {
      captured = useAuth();
      return null;
    }
    vi.spyOn(api, 'getMe').mockResolvedValue(VERIFIED_USER);

    render(<AuthProvider><Capture /></AuthProvider>);
    await waitFor(() => expect(captured.loading).toBe(false));

    expect(captured).not.toHaveProperty('token');
    expect(Object.keys(captured).sort()).toEqual(
      ['isAuthenticated', 'isVerified', 'loading', 'login', 'logout', 'register', 'user'],
    );
  });

  it('throws a useful error outside the provider', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow('useAuth must be used within AuthProvider');
    quiet.mockRestore();
  });
});
