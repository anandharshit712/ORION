const BASE = '/api';

async function request(endpoint, options = {}) {
  const { token, ...fetchOpts } = options;

  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(`${BASE}${endpoint}`, {
    ...fetchOpts,
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Auth
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

  getMe: (token) =>
    request('/auth/me', { token }),

  // Scenarios
  getScenarios: (token) =>
    request('/scenarios/', { token }),

  // Runs / Results
  getRuns: (token, limit = 50) =>
    request(`/runs/?limit=${limit}`, { token }),

  getRunDetail: (token, runId) =>
    request(`/runs/${runId}`, { token }),

  getBatchJobs: (token) =>
    request('/jobs/', { token }),

  // Evaluate
  evaluateSingle: (token, scenarioName, modelName, seed) =>
    request('/evaluate/single', {
      method: 'POST',
      token,
      body: JSON.stringify({
        scenario_name: scenarioName,
        model_name: modelName,
        master_seed: seed,
      }),
    }),

  // Health
  getHealth: () => request('/health'),

  // Live runs (P1.1)
  startRun: (token, scenarioPath, modelName, masterSeed = 42, tickInterval = 0.02) =>
    request('/runs/', {
      method: 'POST',
      token,
      body: JSON.stringify({
        scenario_path: scenarioPath,
        model_name: modelName,
        master_seed: masterSeed,
        tick_interval: tickInterval,
      }),
    }),

  listLiveRuns: (token) => request('/runs/', { token }),

  getLiveRun: (token, runId) => request(`/runs/${runId}`, { token }),

  cancelLiveRun: (token, runId) =>
    request(`/runs/${runId}`, { method: 'DELETE', token }),
};
