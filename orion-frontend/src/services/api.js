// Only the auth and live-run routers are mounted under /api. The scenario,
// job, result, evaluate and health routers are mounted at the root — see
// CLAUDE.md section 8. Prefixing everything with /api pointed getScenarios,
// getBatchJobs, getHealth and evaluateSingle at 404s; they went unnoticed
// because those dashboard sections are not wired up yet, so nothing called
// them. Each method below names its own full path.
const API = '/api';

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

async function request(path, options = {}) {
  const { ...fetchOpts } = options;
  const method = (fetchOpts.method || 'GET').toUpperCase();

  const headers = { 'Content-Type': 'application/json' };
  if (UNSAFE_METHODS.has(method)) {
    const csrf = csrfToken();
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }

  const res = await fetch(path, {
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
    request(`${API}/auth/register`, {
      method: 'POST',
      body: JSON.stringify({ email, username, password, full_name: fullName }),
    }),

  login: (identifier, password) =>
    request(`${API}/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ identifier, password }),
    }),

  logout: () => request(`${API}/auth/logout`, { method: 'POST' }),

  getMe: () => request(`${API}/auth/me`),

  forgotPassword: (email) =>
    request(`${API}/auth/forgot-password`, {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token, newPassword) =>
    request(`${API}/auth/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  verifyEmail: (token) =>
    request(`${API}/auth/verify-email`, {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),

  resendVerification: (email) =>
    request(`${API}/auth/resend-verification`, {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  // Scenarios
  getScenarios: () => request('/scenarios/'),

  // Runs / Results
  getRuns: (limit = 50) => request(`${API}/runs/?limit=${limit}`),

  getRunDetail: (runId) => request(`${API}/runs/${runId}`),

  getBatchJobs: () => request('/jobs/'),

  // Live progress for one batch: counts by state plus the aggregate so far.
  // Distinct from getBatchJobs, which lists the job rows.
  getBatchStatus: (batchId) => request(`${API}/runs/batch/${batchId}/status`),

  // Full score distributions for a finished batch (Phase 2.1): per-metric mean,
  // 95% interval, percentiles, the collision-rate Wilson interval, the best and
  // worst seeds, and a pre-binned composite histogram.
  getBatchResults: (batchId) => request(`${API}/runs/batch/${batchId}/results`),

  // Customer models (P1.2). Mounted under /api, unlike /models/ at the root
  // which is the built-in model catalogue.
  getModels: () => request(`${API}/models/`),

  getModelDetail: (modelId) => request(`${API}/models/${modelId}`),

  deleteModel: (modelId) => request(`${API}/models/${modelId}`, { method: 'DELETE' }),

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

  // Billing (Phase 1.4). Plan allocations come from the backend so the two
  // sides cannot drift — this page previously advertised credit numbers that
  // did not match what an account actually received.
  getPlans: () => request(`${API}/billing/plans`),

  getBillingUsage: () => request(`${API}/billing/usage`),

  createCheckout: (plan, successUrl, cancelUrl) =>
    request(`${API}/billing/checkout`, {
      method: 'POST',
      body: JSON.stringify({ plan, success_url: successUrl, cancel_url: cancelUrl }),
    }),

  openBillingPortal: (returnUrl) =>
    request(`${API}/billing/portal?return_url=${encodeURIComponent(returnUrl)}`),

  // Health
  getHealth: () => request('/health'),

  // Live runs (P1.1)
  startRun: (scenarioPath, modelName, masterSeed = 42, tickInterval = 0.02) =>
    request(`${API}/runs/`, {
      method: 'POST',
      body: JSON.stringify({
        scenario_path: scenarioPath,
        model_name: modelName,
        master_seed: masterSeed,
        tick_interval: tickInterval,
      }),
    }),

  listLiveRuns: () => request(`${API}/runs/`),

  getLiveRun: (runId) => request(`${API}/runs/${runId}`),

  // Single-use, 60-second credential for the run's WebSocket (D-04). The
  // session JWT must never appear in a socket URL — URLs reach access logs,
  // proxy logs and browser history.
  createWsTicket: (runId) =>
    request(`${API}/runs/${runId}/ws-ticket`, { method: 'POST' }),

  cancelLiveRun: (runId) => request(`${API}/runs/${runId}`, { method: 'DELETE' }),
};
