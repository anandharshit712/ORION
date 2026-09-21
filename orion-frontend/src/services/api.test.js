// API client tests (Phase 2 — the frontend had no tests at all).
//
// This file is the whole surface between the app and the backend, and the two
// things it must get right fail silently when broken:
//
//   - credentials: 'include'. Drop it and every authenticated call 401s, which
//     looks like an auth bug rather than a fetch option.
//   - the CSRF header on writes. Drop it and every write 403s; keep sending it
//     on reads and nothing breaks, so nothing catches the asymmetry either.
//
// Both regressed silently once already: every method used to be prefixed with
// /api even though only the auth and live-run routers are mounted there, so
// four of them pointed at 404s and nobody noticed because their pages are not
// wired up yet.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from './api';

function mockFetch(response = {}, { status = 200, ok = true } = {}) {
  const spy = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => response,
  });
  global.fetch = spy;
  return spy;
}

function lastCall(spy) {
  const [url, options] = spy.mock.calls[spy.mock.calls.length - 1];
  return { url, options };
}

beforeEach(() => {
  mockFetch();
});

describe('request plumbing', () => {
  it('sends the session cookie on every call', async () => {
    const spy = mockFetch();
    await api.getMe();
    expect(lastCall(spy).options.credentials).toBe('include');
  });

  it('sends the cookie on writes too', async () => {
    const spy = mockFetch();
    await api.logout();
    expect(lastCall(spy).options.credentials).toBe('include');
  });

  it('throws the API detail rather than a generic message', async () => {
    mockFetch({ detail: 'Email address not verified.' }, { ok: false, status: 403 });
    await expect(api.getRuns()).rejects.toThrow('Email address not verified.');
  });

  it('falls back to the status text when there is no JSON body', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => { throw new Error('not json'); },
    });
    await expect(api.getRuns()).rejects.toThrow('Internal Server Error');
  });

  it('returns null for 204 rather than trying to parse a body', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => { throw new Error('no body'); },
    });
    await expect(api.cancelLiveRun('run-1')).resolves.toBeNull();
  });
});

describe('CSRF (D-04)', () => {
  it('echoes the readable csrf cookie on a write', async () => {
    document.cookie = 'orion_csrf=token-abc123';
    const spy = mockFetch();

    await api.startRun('scenarios/x.yaml', 'EmergencyBrake');

    expect(lastCall(spy).options.headers['X-CSRF-Token']).toBe('token-abc123');
  });

  it('does not send the header on reads', async () => {
    document.cookie = 'orion_csrf=token-abc123';
    const spy = mockFetch();

    await api.getRuns();

    expect(lastCall(spy).options.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('sends it on DELETE as well as POST', async () => {
    document.cookie = 'orion_csrf=token-abc123';
    const spy = mockFetch();

    await api.cancelLiveRun('run-1');

    expect(lastCall(spy).options.headers['X-CSRF-Token']).toBe('token-abc123');
  });

  it('omits the header when there is no cookie rather than sending empty', async () => {
    const spy = mockFetch();
    await api.logout();
    expect(lastCall(spy).options.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('picks its own cookie out of several', async () => {
    document.cookie = 'orion-theme=dark';
    document.cookie = 'orion_csrf=the-right-one';
    document.cookie = 'other=value';
    const spy = mockFetch();

    await api.logout();

    expect(lastCall(spy).options.headers['X-CSRF-Token']).toBe('the-right-one');
  });
});

describe('route prefixes', () => {
  // Only the auth and live-run routers are mounted under /api. Everything else
  // is at the root. Getting this wrong is quiet: the dev server answers with
  // index.html and the call fails as a JSON parse error, not a 404.
  const cases = [
    ['getMe', () => api.getMe(), '/api/auth/me'],
    ['logout', () => api.logout(), '/api/auth/logout'],
    ['getRuns', () => api.getRuns(10), '/api/runs/?limit=10'],
    ['createWsTicket', () => api.createWsTicket('r1'), '/api/runs/r1/ws-ticket'],
    ['getPlans', () => api.getPlans(), '/api/billing/plans'],
    ['getScenarios', () => api.getScenarios(), '/scenarios/'],
    ['getBatchJobs', () => api.getBatchJobs(), '/jobs/'],
    ['getHealth', () => api.getHealth(), '/health'],
  ];

  it.each(cases)('%s hits %s', async (_name, call, expected) => {
    const spy = mockFetch();
    await call();
    expect(lastCall(spy).url).toBe(expected);
  });

  it('never double-prefixes a root-mounted route', async () => {
    const spy = mockFetch();
    await api.getScenarios();
    expect(lastCall(spy).url).not.toContain('/api/scenarios');
  });
});

describe('method signatures', () => {
  // These lost their token argument when the session moved to a cookie. A
  // caller still passing one would silently send the token as the limit.
  it('getRuns takes a limit, not a token', async () => {
    const spy = mockFetch();
    await api.getRuns(25);
    expect(lastCall(spy).url).toBe('/api/runs/?limit=25');
  });

  it('startRun takes the scenario path first', async () => {
    const spy = mockFetch();
    await api.startRun('scenarios/basic/x.yaml', 'EmergencyBrake', 7, 0.05);
    const body = JSON.parse(lastCall(spy).options.body);
    expect(body).toEqual({
      scenario_path: 'scenarios/basic/x.yaml',
      model_name: 'EmergencyBrake',
      master_seed: 7,
      tick_interval: 0.05,
    });
  });

  it('createCheckout sends the plan and both redirect urls', async () => {
    const spy = mockFetch();
    await api.createCheckout('starter', 'https://x/ok', 'https://x/no');
    expect(JSON.parse(lastCall(spy).options.body)).toEqual({
      plan: 'starter',
      success_url: 'https://x/ok',
      cancel_url: 'https://x/no',
    });
  });
});
