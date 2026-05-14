// Tiny inline SVG sparkline. Used inside KPI cards to show trend at a glance.
// No dependency, ~30 lines. Recharts would be overkill for 30 data points.

export default function Sparkline({ data, width = 120, height = 32, color = '#4f7cff' }) {
  if (!data || data.length < 2) {
    return <div style={{ height, width, opacity: 0.3 }} className="muted">—</div>;
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  // Map each point to (x, y) in the viewBox.
  const stepX = width / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / range) * height;
    return [x, y];
  });

  const path = 'M ' + points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L ');

  // Last-point dot makes the "current value" position obvious.
  const [lastX, lastY] = points[points.length - 1];

  // Trend color: green if up, red if down, neutral if flat.
  const trend = data[data.length - 1] - data[0];
  const trendColor = trend > 0 ? '#1a7d3a' : trend < 0 ? '#d94f4f' : color;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
      <path d={path} fill="none" stroke={trendColor} strokeWidth={1.5} strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r={2.5} fill={trendColor} />
    </svg>
  );
}
