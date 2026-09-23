// Confidence-interval display tests (Phase 2.1).
//
// Acceptance criterion: the dashboard shows the interval on the score cards.
// The silent failure this guards against is the whole reason 2.1 exists — a
// mean rendered alone looks more certain than the run count justifies, and
// nobody notices, because a number with no interval still looks like a number.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import ScoreCard from './ScoreCard';
import BatchDistributions from './BatchDistributions';
import { ThemeProvider } from '../../theme/ThemeContext';
import { api } from '../../services/api';

function dist(mean, low, high, n = 50) {
  return {
    mean,
    std: 0.1,
    ci_95_low: low,
    ci_95_high: high,
    percentile_5: low,
    percentile_25: mean,
    percentile_75: mean,
    percentile_95: high,
    minimum: low,
    maximum: high,
    n,
  };
}

const RESULTS = {
  batch_id: 1,
  status: 'completed',
  scenario_name: 'LON-003 Emergency Stop',
  model_name: 'EmergencyBrake',
  num_runs: 50,
  scored_runs: 50,
  master_seed: 42,
  distributions: {
    composite: dist(0.8912, 0.8712, 0.9112),
    safety: dist(0.95, 0.93, 0.97),
    compliance: dist(0.88, 0.86, 0.9),
    stability: dist(0.82, 0.8, 0.84),
    reactivity: dist(0.9, 0.88, 0.92),
    min_ttc: dist(4.2, 4.0, 4.4),
  },
  collision_rate: 0.02,
  collision_rate_ci_95_low: 0.0035,
  collision_rate_ci_95_high: 0.1044,
  worst_run_seed: 57,
  best_run_seed: 43,
  histogram: [{ lower: 0.8, upper: 0.9, count: 50 }],
  low_confidence: false,
};

function renderDist(overrides = {}) {
  vi.spyOn(api, 'getBatchResults').mockResolvedValue({ ...RESULTS, ...overrides });
  return render(
    <ThemeProvider>
      <BatchDistributions batchId={1} />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('ScoreCard interval', () => {
  it('shows the interval half-width and the sample size', () => {
    render(<ScoreCard label="Safety" value={73.0} ciLow={69.0} ciHigh={77.0} n={100} />);

    expect(screen.getByText(/±4\.0/)).toBeInTheDocument();
    expect(screen.getByText(/95% CI · n=100/)).toBeInTheDocument();
  });

  it('shows no interval when none was supplied', () => {
    // A card with no interval must not invent one, and must still render the
    // mean rather than blanking out.
    render(<ScoreCard label="Safety" value={73.0} />);

    expect(screen.getByText('73.0')).toBeInTheDocument();
    expect(screen.queryByText(/95% CI/)).not.toBeInTheDocument();
  });

  it('warns in words when the sample is too small', () => {
    // A wide bar is easy to overlook; a confident-looking mean is not.
    render(
      <ScoreCard label="Safety" value={73.0} ciLow={40} ciHigh={106} n={3} lowConfidence />,
    );
    expect(screen.getByRole('note')).toHaveTextContent(/small sample/i);
  });

  it('does not render an interval when the bounds are degenerate', () => {
    // n=1 collapses the interval to the mean. Drawing a zero-width band would
    // read as a precisely-known value, which is the opposite of the truth.
    render(<ScoreCard label="Safety" value={80} ciLow={80} ciHigh={80} n={1} />);
    expect(screen.queryByText(/95% CI/)).not.toBeInTheDocument();
  });
});

describe('BatchDistributions', () => {
  it('shows an interval on every score card', async () => {
    renderDist();
    // Composite: mean 89.12, interval 87.12–91.12, so half-width 1.0.
    expect(await screen.findByText('89.1')).toBeInTheDocument();
    expect(screen.getAllByText(/95% CI · n=50/).length).toBe(5);
  });

  it('shows the collision rate with its Wilson bound', async () => {
    // Zero-ish collision rates are exactly where a symmetric interval would
    // run below zero, so the bound is the number that can be defended.
    renderDist();
    const panel = (await screen.findByText('Collision rate')).closest('.dist-collision');
    expect(within(panel).getByText(/2\.0/)).toBeInTheDocument();
    expect(within(panel).getByText(/95% CI \[0\.4 – 10\.4\]/)).toBeInTheDocument();
  });

  it('names the worst and best run by seed', async () => {
    // A row id cannot be re-run; a seed can, which is the only reason to name
    // the worst run at all.
    renderDist();
    expect(await screen.findByText('57')).toBeInTheDocument();
    expect(screen.getByText('43')).toBeInTheDocument();
    expect(screen.getByText(/re-run a seed/i)).toBeInTheDocument();
  });

  it('flags a small batch rather than presenting it as settled', async () => {
    // Flagged twice on purpose: once as a chip on the batch, once per score
    // card. A caveat only at the top is easy to scroll past.
    renderDist({ scored_runs: 3, low_confidence: true });

    const warnings = await screen.findAllByText(/small sample/i);
    expect(warnings.length).toBeGreaterThan(1);
    expect(screen.getAllByRole('note').length).toBe(5);
  });

  it('shows an empty state for a batch with no scored runs', async () => {
    // Zeros here would read as a model that failed everything.
    renderDist({ scored_runs: 0, distributions: {} });
    expect(await screen.findByText(/no scored runs yet/i)).toBeInTheDocument();
  });

  it('shows an error state, not an empty one, when the request fails', async () => {
    vi.spyOn(api, 'getBatchResults').mockRejectedValue(new Error('Boom'));
    render(
      <ThemeProvider>
        <BatchDistributions batchId={1} />
      </ThemeProvider>,
    );

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText(/no scored runs yet/i)).not.toBeInTheDocument();
  });
});
