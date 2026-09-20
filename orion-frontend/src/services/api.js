const BASE = '/api';

// Methods that change state and therefore need the CSRF token (RFC 9110).
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Read the readable half of the double-submit CSRF pair (Phase 0.4, D-04).
 *
 * The session JWT lives in an httpOnly cookie we deliberately cannot read. This
 * companion cookie is readable on purpose: echoing it back in a header is what
 * proves the request came from our own page. A cross-site page can make the
 * browser send the cookies, but cannot read them to build this header.
 */
function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)orion_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function request(endpoint, options = {}) {
  const { ...fetchOpts } = options;
  const method = (fetchOpts.method || 'GET').toUpperCase();

  const headers = { 'Content-Type': 'application/json' };
  if (UNSAFE_METHODS.has(method)) {
    const csrf = csrfToken();
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }

  const res = await fetch(`${BASE}${endpoint}`, {
    ...fetchOpts,
    headers,
    // Send the session cookie. Without this the browser omits it and every
    // authenticated call 401s — the API is same-origin through the Vite proxy
    // in dev and through the reverse proxy in production, but fetch still needs
    // telling.
    credentials: 'include',
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Auth. No method takes a token any more: the browser is authenticated by the
  // httpOnly cookie the backend sets at login, which JavaScript cannot read.
  // SDK and script clients still use Authorization: Bearer — see CLAUDE.md §8.
  register: (email, username, password, fullName) =>
    request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, username, password, full_name: fullName }),
    }),

  login: (identifier, password) =>
    request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    }),

  logout: () => request('/auth/logout', { method: 'POST' }),

  getMe: () => request('/auth/me'),

  forgotPassword: (email) =>
    request('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token, newPassword) =>
    request('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  verifyEmail: (token) =>
    request('/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),

  resendVerification: (email) =>
    request('/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  // Scenarios
  getScenarios: () => request('/scenarios/'),

  // Runs / Results
  getRuns: (limit = 50) => request(`/runs/?limit=${limit}`),

  getRunDetail: (runId) => request(`/runs/${runId}`),

  getBatchJobs: () => request('/jobs/'),

  // Evaluate
  evaluateSingle: (scenarioName, modelName, seed) =>
    request('/evaluate/single', {
      method: 'POST',
      body: JSON.stringify({
        scenario_name: scenarioName,
        model_name: modelName,
        master_seed: seed,
      }),
    }),

  // Health
  getHealth: () => request('/health'),

  // Live runs (P1.1)
  startRun: (scenarioPath, modelName, masterSeed = 42, tickInterval = 0.02) =>
    request('/runs/', {
      method: 'POST',
      body: JSON.stringify({
        scenario_path: scenarioPath,
        model_name: modelName,
        master_seed: masterSeed,
        tick_interval: tickInterval,
      }),
    }),

  listLiveRuns: () => request('/runs/'),

  getLiveRun: (runId) => request(`/runs/${runId}`),

  // Single-use, 60-second credential for the run's WebSocket (D-04). The
  // session JWT must never appear in a socket URL — URLs reach access logs,
  // proxy logs and browser history.
  createWsTicket: (runId) =>
    request(`/runs/${runId}/ws-ticket`, { method: 'POST' }),

  cancelLiveRun: (runId) => request(`/runs/${runId}`, { method: 'DELETE' }),
};
