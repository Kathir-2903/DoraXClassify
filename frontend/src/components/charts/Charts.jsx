import { memo } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { ChartTooltip, Legend } from './ChartCard';

const AXIS = { stroke: 'var(--chart-axis)', tick: { fill: 'var(--chart-muted)', fontSize: 11 }, tickLine: false };
export const SERIES = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)'];

/** Multi-series line chart with crosshair tooltip and legend (daily counts overlap
 * too often at zero for end-of-line labels to stay legible). */
function TimeSeriesChartBase({ data, series, xKey = 'date', xFormatter, height = 240 }) {
  return (
    <div className="chart-wrap">
      <Legend items={series.map((s, i) => ({ label: s.label, color: s.color || SERIES[i] }))} />
      <ResponsiveContainer width="100%" height={height - 34}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={28} />
          <YAxis {...AXIS} axisLine={false} allowDecimals={false} width={44} />
          <Tooltip content={<ChartTooltip labelFormatter={xFormatter} />} cursor={{ stroke: 'var(--chart-axis)', strokeDasharray: '3 3' }} />
          {series.map((s, i) => (
            <Line
              key={s.key}
              type="linear"
              dataKey={s.key}
              name={s.label}
              stroke={s.color || SERIES[i]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }}
              isAnimationActive={false}
            >
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
export const TimeSeriesChart = memo(TimeSeriesChartBase);

/** Donut with a surface-coloured gap between segments and the total in the centre. */
function DonutChartBase({ data, colors, height = 240, centerLabel = 'Total' }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const visible = data.filter((d) => d.value > 0);
  return (
    <div className="donut-layout">
      <div style={{ position: 'relative', width: '100%', maxWidth: 220, height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Tooltip content={<ChartTooltip />} />
            <Pie data={visible} dataKey="value" nameKey="name" innerRadius="64%" outerRadius="92%" paddingAngle={visible.length > 1 ? 1.5 : 0}
                 stroke="var(--surface)" strokeWidth={2} isAnimationActive={false}>
              {visible.map((d) => (
                <Cell key={d.name} fill={colors[d.name]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <strong className="tabular">{total}</strong>
          <span>{centerLabel}</span>
        </div>
      </div>
      <Legend items={data.map((d) => ({ label: d.name, color: colors[d.name], value: d.value }))} />
    </div>
  );
}
export const DonutChart = memo(DonutChartBase);

/** Single-series bar chart. `colors` may map category → colour for ordinal scales. */
function SimpleBarChartBase({ data, xKey, yKey, name, color = 'var(--series-1)', colors, height = 240, horizontal = false, valueFormatter }) {
  const fmt = valueFormatter || ((v) => v);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'}
                margin={horizontal ? { top: 4, right: 44, left: 8, bottom: 0 } : { top: 20, right: 8, left: -18, bottom: 0 }}
                barCategoryGap={horizontal ? '28%' : '32%'}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...AXIS} allowDecimals={false} hide />
            <YAxis type="category" dataKey={xKey} {...AXIS} axisLine={false} width={132} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...AXIS} interval={0} />
            <YAxis {...AXIS} axisLine={false} allowDecimals={false} width={44} />
          </>
        )}
        <Tooltip content={<ChartTooltip valueFormatter={fmt} />} cursor={{ fill: 'var(--surface-3)', opacity: 0.6 }} />
        <Bar dataKey={yKey} name={name} fill={color} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={horizontal ? 18 : 44}
             isAnimationActive={false}>
          {colors && data.map((d) => <Cell key={d[xKey]} fill={colors[d[xKey]] || color} />)}
          <LabelList dataKey={yKey} position={horizontal ? 'right' : 'top'} fontSize={11} fill="var(--text-2)" formatter={fmt} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
export const SimpleBarChart = memo(SimpleBarChartBase);

export const STATUS_COLORS = {
  Scheduled: 'var(--series-1)',
  Completed: 'var(--status-good)',
  'No Show': 'var(--status-serious)',
  Processing: 'var(--status-warning)',
  Failed: 'var(--status-critical)',
};

// Ordinal (High → Low) steps from the single blue ramp; Unknown stays neutral gray.
export const LEVEL_COLORS = {
  High: 'var(--seq-600)',
  Medium: 'var(--seq-450)',
  Low: 'var(--seq-300)',
  Unknown: '#c3c2b7',
};
