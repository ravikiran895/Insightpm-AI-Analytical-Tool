import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';

/**
 * Dashboard overview component — KPI tiles + Top Events widget.
 *
 * Renders at the TOP of the Dashboard tab, above NLQBox and InsightsPanel.
 * Fetches all KPIs in one POST to /dashboard/kpis (single round-trip).
 *
 * Compare-to-previous-period is a togglable button at top-right. When ON
 * (default), each KPI tile shows a delta arrow + percentage / pp change.
 *
 * Sparkline is rendered only under the Active Users KPI (per scope).
 */
export default function DashboardOverview({ dateRange, cohort }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [compare, setCompare] = useState(true);

  // Abort token so stale requests don't overwrite fresh data
  // (e.g. user changes date range twice quickly)
  const abortRef = useRef({ aborted: false });

  useEffect(() => {
    if (!dateRange?.start || !dateRange?.end) return;
    abortRef.current = { aborted: false };
    const token = abortRef.current;
    setLoading(true);
    setErr(null);
    api.dashboardKpis({
      start_date: dateRange.start,
      end_date: dateRange.end,
      cohort: cohort && cohort.length > 0 ? cohort : null,
      compare,
    })
      .then((r) => { if (!token.aborted) setData(r); })
      .catch((e) => { if (!token.aborted) setErr(e); })
      .finally(() => { if (!token.aborted) setLoading(false); });
    return () => { token.aborted = true; };
  }, [dateRange?.start, dateRange?.end, cohort, compare]);

  return (
    <div className="dash-overview">
      {/* Header row: section label + compare toggle */}
      <div className="dash-overview-head">
        <span className="dash-overview-label">Overview</span>
        <button
          className={`dash-compare-toggle ${compare ? 'on' : 'off'}`}
          onClick={() => setCompare(!compare)}
          title={compare ? 'Hide comparison to previous period' : 'Show comparison to previous period'}
        >
          {compare ? '✓ ' : ''}Compare vs prev period
        </button>
      </div>

      <ErrorBox error={err} />

      {/* Loading skeleton — same layout as final so the height is stable */}
      {loading && !data && <KpiSkeletons />}

      {data && (
        <>
          <div className="kpi-grid-v2">
            <KpiTile
              label="Active Users"
              value={data.current?.active_users}
              delta={compare ? data.deltas?.active_users : null}
              sparkline={data.current?.sparkline}
              format="number"
            />
            <KpiTile
              label="Total Events"
              value={data.current?.total_events}
              delta={compare ? data.deltas?.total_events : null}
              format="compact"
            />
            <KpiTile
              label="D7 Retention"
              value={data.current?.d7_rate}
              delta={compare ? data.deltas?.d7_rate : null}
              format="rate"
              subtext={
                data.current?.total_cohorted != null
                  ? `${(data.current.d7_retained || 0).toLocaleString()} of ${data.current.total_cohorted.toLocaleString()} cohorted users`
                  : null
              }
            />
            <KpiTile
              label="Top Event"
              value={data.current?.top_events?.[0]?.event_count}
              format="compact"
              subtext={data.current?.top_events?.[0]?.event_name || '—'}
            />
          </div>

          {data.current?.top_events && data.current.top_events.length > 0 && (
            <TopEventsCard events={data.current.top_events} />
          )}
        </>
      )}
    </div>
  );
}

// ============================================================
// Sub-components
// ============================================================

function KpiTile({ label, value, delta, sparkline, subtext, format }) {
  return (
    <div className="kpi-v2">
      <div className="kpi-v2-label">{label}</div>
      <div className="kpi-v2-value">{formatValue(value, format)}</div>
      {delta ? (
        <DeltaIndicator delta={delta} />
      ) : (
        // Reserve vertical space so tiles don't shift when compare toggles
        <div className="kpi-v2-delta-spacer" />
      )}
      {subtext && <div className="kpi-v2-subtext">{subtext}</div>}
      {sparkline && sparkline.length > 0 && (
        <KpiSparkline series={sparkline} />
      )}
    </div>
  );
}

function DeltaIndicator({ delta }) {
  if (!delta) return null;
  const { direction, pct, pp, unit, absolute } = delta;

  // D7 deltas are in pp (percentage points), others are pct (%)
  const isPp = unit === 'pp';
  const displayValue = isPp ? pp : pct;

  if (displayValue == null) {
    // Special case: previous=0, current>0 — show "new" rather than ∞%
    return (
      <div className={`kpi-v2-delta delta-${direction}`}>
        <span className="delta-arrow">↑</span>
        <span>new (no baseline)</span>
      </div>
    );
  }

  const arrow = direction === 'up' ? '↑' : direction === 'down' ? '↓' : '→';
  const sign = displayValue > 0 ? '+' : '';
  const absDisplay = Math.abs(displayValue);
  const suffix = isPp ? 'pp' : '%';

  return (
    <div className={`kpi-v2-delta delta-${direction}`}>
      <span className="delta-arrow">{arrow}</span>
      <span>{sign}{absDisplay}{suffix} vs prev{isPp ? '' : ' period'}</span>
    </div>
  );
}

function KpiSparkline({ series }) {
  if (!series || series.length < 2) return null;
  const w = 100, h = 28;
  const values = series.map((p) => p.value || 0);
  const max = Math.max(...values, 1);
  const stepX = w / Math.max(values.length - 1, 1);

  const points = values
    .map((v, i) => `${(i * stepX).toFixed(1)},${(h - (v / max) * (h - 2)).toFixed(1)}`)
    .join(' ');
  const areaPath = `M0,${h} L${points.replace(/ /g, ' L')} L${w},${h} Z`;

  return (
    <div className="kpi-v2-spark">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: '100%', height: 28 }}>
        <defs>
          <linearGradient id="dashSparkG" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--blue)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--blue)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#dashSparkG)" />
        <polyline points={points} fill="none" stroke="var(--blue)" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

function TopEventsCard({ events }) {
  const max = Math.max(...events.map((e) => e.event_count || 0), 1);
  return (
    <div className="card dash-top-events">
      <div className="dash-top-events-head">
        <span className="card-title-v2">Top Events</span>
      </div>
      <div className="dash-top-events-body">
        {events.map((e, i) => (
          <div className="bar-row" key={i}>
            <div className="bar-label">{e.event_name}</div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{ width: `${((e.event_count || 0) / max * 100).toFixed(1)}%` }}
              />
            </div>
            <div className="bar-val">{formatCompact(e.event_count)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function KpiSkeletons() {
  return (
    <div className="kpi-grid-v2">
      {[1, 2, 3, 4].map((i) => (
        <div className="kpi-v2" key={i}>
          <div className="skeleton-line" style={{ width: '60%' }} />
          <div className="skeleton-line" style={{ width: '40%', height: 28 }} />
          <div className="skeleton-line" style={{ width: '50%' }} />
        </div>
      ))}
    </div>
  );
}

// ============================================================
// Formatting helpers
// ============================================================

function formatValue(v, format) {
  if (v == null) return '—';
  switch (format) {
    case 'rate':
      return `${(v * 100).toFixed(1)}%`;
    case 'compact':
      return formatCompact(v);
    case 'number':
    default:
      return Number(v).toLocaleString();
  }
}

function formatCompact(n) {
  if (n == null) return '—';
  const num = Number(n);
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(num >= 10_000 ? 0 : 1)}K`;
  return num.toLocaleString();
}
