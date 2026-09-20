import { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../services/api';

const AuthContext = createContext(null);

/**
 * Session state for the browser app (Phase 0.4, D-04).
 *
 * The JWT is no longer here, and no longer in localStorage. It lives in an
 * httpOnly cookie the backend sets at login, which JavaScript cannot read — so
 * a script injected into the page cannot walk off with a 24-hour credential.
 *
 * That means the client has no way to inspect its own session, so auth state is
 * derived instead: call GET /api/auth/me on mount, and whether it succeeds is
 * the answer. A page refresh keeps the user logged in because the cookie
 * survives it.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    // A 401 here is the normal "not logged in" case, not an error worth
    // surfacing — every first-time visitor hits it.
    api.getMe()
      .then((me) => { if (!cancelled) setUser(me); })
      .catch(() => { if (!cancelled) setUser(null); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, []);

  const login = async (identifier, password) => {
    // Sets the session and CSRF cookies; the token in the response body is for
    // SDK clients and is deliberately ignored here.
    await api.login(identifier, password);
    const me = await api.getMe();
    setUser(me);
    return me;
  };

  const register = async (email, username, password, fullName) => {
    return api.register(email, username, password, fullName);
  };

  const logout = async () => {
    // The server has to clear the cookie — the page cannot, which is the point
    // of httpOnly. Local state is dropped either way, so a failed request still
    // logs the user out of this tab.
    try {
      await api.logout();
    } catch {
      // Network failure or an already-expired session: nothing to recover.
    }
    setUser(null);
  };

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    isAuthenticated: user !== null,
    // Signup no longer auto-activates an address (D-04). Pages gate the
    // actions that need a verified account on this.
    isVerified: Boolean(user?.email_verified),
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
