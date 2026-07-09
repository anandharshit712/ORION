// ORION — RegressionChart  [P2]
// Composite score over model versions / runs (Recharts line on grid), themed §9.8/§12.
// Composite line amber, baseline/threshold cyan, regression points marked --fail.
// Data wiring tracked separately.

import { useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { useTheme } from '../../theme/ThemeContext';
import './RegressionChart.css';

// Chart palette recomputed from CSS vars on theme change (§12).
function useChartPalette() {
  const { theme } = useTheme();
  return useMemo(() => {
    const v = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    return {
      amber: v('--amber'), cyan: v('--cyan'), fail: v('--fail'),
      grid: v('--border'), axis: v('--text-mute'),
      tooltipBg: v('--bg-elev'), border: v('--border'),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}

/**
 * RegressionChart — composite trend with regression markers.
 *
 * Props (optional):
 *   data       [{ x, composite, regression? }] — series; placeholder when absent
 *   threshold  number  — horizontal pass threshold (cyan dashed reference line)
 *   xKey       string  — x-axis data key (default 'x')
 *   title      string  — panel caption
 *   height     number  — chart height (px)
 */
export default function RegressionChart({
  data,
  threshold,
  xKey = 'x',
  title = 'Regression History',
  height = 240,
} = {}) {
  const palette = useChartPalette();
  const hasData = Array.isArray(data) && data.length > 0;

  const tooltipStyle = {
    background: palette.tooltipBg, border: `1px solid ${palette.border}`,
    borderRadius: 3, fontFamily: 'var(--ff-mono)', fontSize: 12,
  };
  const axisProps = { stroke: palette.axis, fontSize: 11, fontFamily: 'var(--ff-mono)' };

  // Square markers; regression points painted --fail, normal points hidden.
  const renderDot = (props) => {
    const { cx, cy, payload, index } = props;
    if (cx == null || cy == null) return null;
    if (!payload?.regression) return null;
    return (
      <rect
        key={`reg-${index}`}
        x={cx - 3} y={cy - 3} width={6} height={6}
        fill={palette.fail} stroke={palette.fail}
      />
    );
  };

  return (
    <div className="panel regression-chart">
      <h3 className="mono-label">
        {title}
        <span className="legend">
          <b className="a">Composite</b>
          <b className="f">Regression</b>
        </span>
      </h3>
      {hasData ? (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
            <XAxis dataKey={xKey} {...axisProps} />
            <YAxis domain={[0, 100]} {...axisProps} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: palette.axis }} />
            {typeof threshold === 'number' && (
              <ReferenceLine
                y={threshold}
                stroke={palette.cyan}
                strokeDasharray="4 4"
                strokeWidth={1.5}
              />
            )}
            <Line
              type="monotone"
              dataKey="composite"
              stroke={palette.amber}
              strokeWidth={2}
              dot={renderDot}
              activeDot={{ r: 4, fill: palette.amber, stroke: palette.amber }}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="regression-empty" style={{ minHeight: height }}>
          <span className="mono-label">No regression data</span>
          <p>Composite score across model versions renders here once a baseline exists.</p>
        </div>
      )}
    </div>
  );
}
