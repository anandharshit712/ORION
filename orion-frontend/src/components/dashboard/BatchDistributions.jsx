// ORION — BatchDistributions
//
// The Phase 2.1 payload made visible: per-metric mean with its 95% interval,
// the collision rate with its Wilson interval, the composite histogram, and the
// seeds of the best and worst runs.
//
// The point of the whole feature is in one line of UI: a mean on its own
// invites more confidence than the run count supports. Every number here is
// shown with the sample behind it, and a batch too small for the interval to
// mean anything says so rather than rendering a tidy figure.

import { useMemo } from 'react';
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useTheme } from '../../theme/ThemeContext';
import { api } from '../../services/api';
import { useApiData } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import ScoreCard from './ScoreCard';
import DataStates from './DataStates';
import './BatchDistributions.css';

// Order matters: composite first because it is the headline, min_ttc last
// because it is on a different scale entirely.
const METRICS = [
  { key: 'composite', label: 'Composite', accent: 'amber' },
  { key: 'safety', label: 'Safety' },
  { key: 'compliance', label: 'Compliance' },
  { key: 'stability', label: 'Stability' },
  { key: 'reactivity', label: 'Reactivity' },
];

const pct = (x) => (typeof x === 'number' ? x * 100 : null);

export default function BatchDistributions({ batchId }) {
  const { theme } = useTheme();
  const { data, loading, error, refresh } = useApiData(
    () => api.getBatchResults(batchId),
    [batchId],
  );

  const palette = useMemo(() => {
    const v = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    return { cyan: v('--cyan'), grid: v('--border'), axis: v('--text-mute'), bg: v('--bg-elev') };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  const histogram = useMemo(
    () =>
      (data?.histogram || []).map((b) => ({
        range: `${Math.round(b.lower * 100)}–${Math.round(b.upper * 100)}`,
        count: b.count,
      })),
    [data],
  );

  return (
    <DataStates
      loading={loading}
      error={error}
      isEmpty={!data || data.scored_runs === 0}
      onRetry={refresh}
      loadingRows={2}
      loadingLabel="Loading distributions"
      emptyLabel="No scored runs yet"
      emptyHint="Distributions appear once the batch has runs to summarise."
    >
      {data && (
        <div className="batch-dist">
          <div className="batch-dist-head">
            <span className="mono-label">
              Score distributions · <span className="num">n={data.scored_runs}</span>
            </span>
            {data.low_confidence && (
              <span className="chip chip-running">small sample</span>
            )}
          </div>

          <div className="dist-cards">
            {METRICS.map(({ key, label, accent }) => {
              const d = data.distributions?.[key];
              if (!d) return null;
              return (
                <ScoreCard
                  key={key}
                  label={label}
                  value={pct(d.mean)}
                  ciLow={pct(d.ci_95_low)}
                  ciHigh={pct(d.ci_95_high)}
                  n={d.n}
                  accent={accent || 'cyan'}
                  live={key === 'composite'}
                  lowConfidence={data.low_confidence}
                />
              );
            })}
          </div>

          <div className="dist-row">
            {/* Collision rate is a proportion, so its interval is Wilson, not
                t-distribution — the normal approximation runs off the scale
                near zero, which is exactly where a good model sits. */}
            <div className="panel dist-collision">
              <span className="mono-label">Collision rate</span>
              <div className="dist-collision-val num">
                {(data.collision_rate * 100).toFixed(1)}<em>%</em>
              </div>
              <div className="dist-collision-ci num">
                95% CI [{(data.collision_rate_ci_95_low * 100).toFixed(1)} –{' '}
                {(data.collision_rate_ci_95_high * 100).toFixed(1)}]
              </div>
              <p className="dist-note">
                Zero collisions in {data.scored_runs} runs is not a zero collision
                probability. The upper bound is the claim that can be defended.
              </p>
            </div>

            <div className="panel dist-histogram">
              <span className="mono-label">Composite distribution</span>
              <ResponsiveContainer width="100%" height={168}>
                <BarChart data={histogram} margin={{ top: 12, right: 4, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
                  <XAxis
                    dataKey="range"
                    stroke={palette.axis}
                    fontSize={10}
                    fontFamily="var(--ff-mono)"
                    interval={1}
                  />
                  <YAxis
                    stroke={palette.axis}
                    fontSize={10}
                    fontFamily="var(--ff-mono)"
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: palette.bg,
                      border: `1px solid ${palette.grid}`,
                      borderRadius: 3,
                      fontFamily: 'var(--ff-mono)',
                      fontSize: 12,
                    }}
                    cursor={{ fill: palette.grid }}
                  />
                  <Bar dataKey="count" fill={palette.cyan} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Seeds, not row ids: these are the two runs worth re-running, and a
              seed is what makes that possible. */}
          <div className="spec-strip dist-seeds">
            <div>
              <span className="num">{data.worst_run_seed ?? '—'}</span>
              <span className="mono-label">worst run seed</span>
            </div>
            <div>
              <span className="num">{data.best_run_seed ?? '—'}</span>
              <span className="mono-label">best run seed</span>
            </div>
            <div>
              <span className="num">{data.master_seed}</span>
              <span className="mono-label">master seed</span>
            </div>
            <div className="dist-seeds-hint">
              <Icon name="refresh" size={12} />
              <span>Re-run a seed to reproduce that run exactly.</span>
            </div>
          </div>
        </div>
      )}
    </DataStates>
  );
}
