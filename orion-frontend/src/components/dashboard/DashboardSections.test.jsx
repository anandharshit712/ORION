// Dashboard section wiring tests.
//
// Per CLAUDE.md §9, the rule for frontend tests is to cover what fails
// *silently*. A wrong colour is visible the moment anyone opens the page; a
// section that renders an empty table on a 500 looks exactly like a section
// with no data, and someone will spend an afternoon on the backend.
//
// So: the three states are asserted for every section, the endpoint each one
// calls is pinned (the /api prefix split is a live footgun — four api.js
// methods once shipped pointed at 404s), and the sidebar's `ready` flags are
// checked against the sections that actually exist.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import RunsSection from './RunsSection';
import BatchesSection from './BatchesSection';
import ModelsSection from './ModelsSection';
import ScenariosSection from './ScenariosSection';
import CompareSection from './CompareSection';
import SearchSection from './SearchSection';
import SettingsSection from './SettingsSection';
import { api } from '../../services/api';

function renderSection(Component) {
  return render(
    <MemoryRouter>
      <Component />
    </MemoryRouter>,
  );
}

const SECTIONS = [
  { name: 'Runs', Component: RunsSection, method: 'getStoredRuns', empty: /no runs recorded/i },
  { name: 'Batches', Component: BatchesSection, method: 'getBatchJobs', empty: /no batch jobs/i },
  { name: 'Models', Component: ModelsSection, method: 'getModels', empty: /no submitted models/i },
  { name: 'Scenarios', Component: ScenariosSection, method: 'getScenarios', empty: /no scenarios registered/i },
  { name: 'Compare', Component: CompareSection, method: 'listComparisons', empty: /no comparisons yet/i },
  { name: 'Search', Component: SearchSection, method: 'listSearches', empty: /no searches yet/i },
];

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe.each(SECTIONS)('$name section', ({ Component, method, empty }) => {
  it('shows an empty state rather than a bare table when there is no data', async () => {
    vi.spyOn(api, method).mockResolvedValue([]);
    renderSection(Component);
    expect(await screen.findByText(empty)).toBeInTheDocument();
  });

  it('shows an error state, not an empty state, when the request fails', async () => {
    // The failure that matters: a 500 rendered as "no data" sends someone
    // debugging the backend for data that was never missing.
    vi.spyOn(api, method).mockRejectedValue(new Error('Internal Server Error'));
    renderSection(Component);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/internal server error/i)).toBeInTheDocument();
    expect(screen.queryByText(empty)).not.toBeInTheDocument();
  });

  it('shows a loading state before the request resolves', async () => {
    let release;
    vi.spyOn(api, method).mockReturnValue(new Promise((r) => { release = r; }));

    const { container } = renderSection(Component);
    expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();

    release([]);
    await waitFor(() => {
      expect(container.querySelector('[aria-busy="true"]')).toBeFalsy();
    });
  });
});

describe('Runs section', () => {
  // The *stored* run shape, from GET /results/runs. It has no `status` — a run
  // is in the database because it finished — and integer ids, which are the
  // ones replay takes. The section used to read the live registry, whose ids
  // are strings and which is empty after a restart, so a customer with a
  // finished batch was told they had no runs.
  const RUNS = [
    {
      id: 41,
      model_name: 'EmergencyBrake',
      scenario_id: 'scenarios/lon/LON-003_emergency_stop.yaml',
      master_seed: 42,
      duration: 12.4,
      termination_reason: 'completed',
      composite_score: 0.912,
      safety_score: 0.95,
      compliance_score: 0.9,
      stability_score: 0.88,
      reactivity_score: 0.87,
      collision_occurred: false,
    },
    {
      id: 42,
      model_name: 'Random',
      scenario_id: 'scenarios/basic/straight_road_empty.yaml',
      master_seed: 43,
      duration: 3.1,
      termination_reason: 'collision',
      composite_score: null,
      collision_occurred: true,
    },
  ];

  it('renders a dash, not 0.0, for a run that has no score', async () => {
    // A zero here reads as "scored badly" rather than "no score recorded".
    vi.spyOn(api, 'getStoredRuns').mockResolvedValue(RUNS);
    renderSection(RunsSection);

    await screen.findByText('91.2');
    const row = screen.getByText('Random').closest('tr');
    expect(row.textContent).toContain('—');
    expect(row.textContent).not.toContain('0.0');
  });

  it('filters to the runs that collided', async () => {
    // fireEvent rather than user-event: a click on a plain button needs no
    // pointer simulation, and user-event is not a dependency of this project.
    vi.spyOn(api, 'getStoredRuns').mockResolvedValue(RUNS);

    renderSection(RunsSection);
    await screen.findByText('EmergencyBrake');

    fireEvent.click(screen.getByRole('tab', { name: /collided/i }));

    expect(screen.queryByText('EmergencyBrake')).not.toBeInTheDocument();
    expect(screen.getByText('Random')).toBeInTheDocument();
  });

  it('a collision is a fail even without a composite score', async () => {
    // The verdict used to require status === 'completed', which a stored run
    // never has, so every row rendered no verdict at all.
    vi.spyOn(api, 'getStoredRuns').mockResolvedValue(RUNS);
    renderSection(RunsSection);

    const row = (await screen.findByText('Random')).closest('tr');
    expect(row.textContent.toLowerCase()).toContain('fail');
  });

  it('opens the replay, not the live viewer, for a stored run', async () => {
    // Live-run ids are strings from the in-memory registry; these are database
    // integers. Sending one to /simulation/:runId 404s.
    vi.spyOn(api, 'getStoredRuns').mockResolvedValue(RUNS);
    renderSection(RunsSection);

    const row = (await screen.findByText('EmergencyBrake')).closest('tr');
    expect(row.getAttribute('title')).toMatch(/replay/i);
  });
});

describe('Batches section', () => {
  it('does not poll once every batch has finished', async () => {
    // Polling a terminal row forever is how a dashboard quietly becomes a load
    // generator on the API.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const spy = vi.spyOn(api, 'getBatchJobs').mockResolvedValue([
      { id: 1, scenario_name: 's', model_name: 'm', num_runs: 10, status: 'completed', runs_completed: 10, runs_failed: 0 },
    ]);

    renderSection(BatchesSection);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));

    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('polls while a batch is still running', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const spy = vi.spyOn(api, 'getBatchJobs').mockResolvedValue([
      { id: 1, scenario_name: 's', model_name: 'm', num_runs: 10, status: 'running', runs_completed: 3, runs_failed: 0 },
    ]);

    renderSection(BatchesSection);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));

    await act(async () => { await vi.advanceTimersByTimeAsync(9000); });
    expect(spy.mock.calls.length).toBeGreaterThan(1);
  });
});

describe('Scenarios section', () => {
  it('keeps a scenario whose name breaks the ID convention', async () => {
    // Dropping it would hide a scenario that exists; "other" is worse filing
    // but not a disappearance.
    vi.spyOn(api, 'getScenarios').mockResolvedValue([
      { id: 1, name: 'LON-003 Emergency Stop', version: '1.0', duration: 20, num_traffic_objects: 1, content_hash: 'a'.repeat(64) },
      { id: 2, name: 'freeform scenario', version: '1.0', duration: 10, num_traffic_objects: 0, content_hash: 'b'.repeat(64) },
    ]);

    renderSection(ScenariosSection);

    expect(await screen.findByText('LON-003 Emergency Stop')).toBeInTheDocument();
    expect(screen.getByText('freeform scenario')).toBeInTheDocument();
    expect(screen.getByText('other')).toBeInTheDocument();
  });
});

describe('Sidebar wiring', () => {
  it('marks a nav item ready only when a section exists for it', async () => {
    // CLAUDE.md §9: flip `ready: true` in the same change that wires a section
    // up. If these drift, an enabled nav item lands on the ComingSoon panel and
    // reads as a fault rather than as unfinished work.
    const { NAV_ITEMS } = await import('../common/Sidebar');
    const { SECTIONS } = await import('../../pages/DashboardPage');

    for (const item of NAV_ITEMS) {
      if (item.key === 'overview') continue;
      expect(
        Boolean(SECTIONS[item.key]),
        `nav item "${item.key}" is ready=${item.ready} but SECTIONS[${item.key}] is ${SECTIONS[item.key]}`,
      ).toBe(item.ready);
    }
  });
});
