// ORION — ScoreDistribution  [P2]
// Histogram of composite-score distribution (Recharts Bar), themed per §9.8 / §12.
// Bars --cyan, radius [2,2,0,0]. Data wiring tracked separately.

import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useTheme } from '../../theme/ThemeContext';
import './ScoreDistribution.css';

// Chart palette recomputed from CSS vars on theme change (§12).
function useChartPalette() {
  const { theme } = useTheme();
  return useMemo(() => {
    const v = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    return {
      cyan: v('--cyan'), grid: v('--border'), axis: v('--text-mute'),
      tooltipBg: v('--bg-elev'), border: v('--border'),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}

/**
 * ScoreDistribution — composite-score histogram.
 *
 * Props (optional):
 *   data    [{ range, count }]  — pre-binned counts; placeholder shown when absent
 *   title   string              — panel caption
 *   height  number              — chart height (px)
 */
export default function ScoreDistribution({
  data,
  title = 'Score Distribution',
  height = 220,
} = {}) {
  const palette = useChartPalette();
  const hasData = Array.isArray(data) && data.length > 0;

  const tooltipStyle = {
    background: palette.tooltipBg, border: `1px solid ${palette.border}`,
    borderRadius: 3, fontFamily: 'var(--ff-mono)', fontSize: 12,
  };
  const axisProps = { stroke: palette.axis, fontSize: 11, fontFamily: 'var(--ff-mono)' };

  return (
    <div className="panel score-dist">
      <h3 className="mono-label">{title}</h3>
      {hasData ? (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
            <XAxis dataKey="range" {...axisProps} />
            <YAxis allowDecimals={false} {...axisProps} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: palette.grid }} />
            <Bar dataKey="count" fill={palette.cyan} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="score-dist-empty" style={{ minHeight: height }}>
          <span className="mono-label">No distribution data</span>
          <p>Binned composite-score counts render here once runs are recorded.</p>
        </div>
      )}
    </div>
  );
}
