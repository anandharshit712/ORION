// ORION — OrgContext  [Phase 1]
// Provides org-level state: plan, run_credits, org name.
// Separate from AuthContext (which owns user identity) so that
// org state can be refreshed independently after each run.

import React, { createContext, useContext, useState, useCallback } from 'react';
import api from '../services/api';
import { useAuth } from './AuthContext';

const OrgContext = createContext(null);

/**
 * OrgProvider — wraps the app and provides org state to all children.
 * Must be placed inside AuthProvider.
 */
export function OrgProvider({ children }) {
  const { token } = useAuth();
  const [org, setOrg] = useState(null);           // { name, slug, plan, run_credits }
  const [loading, setLoading] = useState(false);

  const refreshOrg = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      // TODO [P1]: Call api.getOrgStatus(token) → GET /api/orgs/me
      // TODO [P1]: setOrg(data)
    } catch (err) {
      console.error('Failed to load org:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  return (
    <OrgContext.Provider value={{ org, loading, refreshOrg }}>
      {children}
    </OrgContext.Provider>
  );
}

/**
 * useOrg — consume org context in any component.
 *
 * Returns: { org, loading, refreshOrg }
 *   org.plan        — "free" | "starter" | "pro" | "enterprise"
 *   org.run_credits — remaining credits (integer)
 *   refreshOrg()    — re-fetch org state from API
 */
export function useOrg() {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error('useOrg must be used inside OrgProvider');
  return ctx;
}
