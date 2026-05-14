import { useEffect, useState } from 'react';
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';
import Sparkline from './Sparkline';
import SqlPreviewModal from './SqlPreviewModal';

const SERIES_COLORS = ['#4f7cff', '#e6a23c', '#1a7d3a', '#d94f4f', '#8a5cf0', '#0ea5b8', '#f06292'];

export default function RetentionDashboard({ dateRange, cohort, fields }) {
  const [data, setData] = useState(null);
  const [breakdownResult, setBreakdownResult] = useState(null);
  const [breakdownField, setBreakdownField] = useState('');
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showSql, setShowSql] = useState(false);

  function load() {
    setLoading(true); setErr(null);
    setBreakdownResult(null); // reload base view clears breakdown
    const hasCohort = cohort && cohort.length > 0;
    const promise = hasCohort
      ? api.retentionWithCohort({ start_date: dateRange.start, end_date: dateRange.end, cohort })
      : api.retention(dateRange.start, dateRange.end);
    promise.then(setData).catch(setErr).finally(() => setLoading(false));
  }

  useEffect(load, [dateRange, cohort]); // eslint-disable-line

  async function runBreakdown() {
    if (!breakdownField) return;
    setLoading(true); setErr(null);
    try {
      const [field_type, ...rest] = breakdownField.split(':');
      const field = rest.join(':');
      const r = await api.retentionBreakdown({
        start_date: dateRange.start, end_date: dateRange.end,
        breakdown_field: field, field_type,
        base_cohort: cohort && cohort.length > 0 ? cohort : null,
        top_n: 5,
      });
      setBreakdownResult(r);
    } catch (e) { setErr(e); } finally { setLoading(false); }
  }

  const breakdownFieldOptions = fields
    ? [...fields.columns, ...fields.user_properties.slice(0, 10)]
    : [];

  return (
    <div className="card">
      <CardHeader title="Retention" cohortCount={cohort?.length || 0} onViewSql={() => setShowSql(true)} />
      {showSql && (
        <SqlPreviewModal
          kind="retention"
          request={{ start_date: dateRange.start, end_date: dateRange.end }}
          onClose={() => setShowSql(false)}
        />
      )}

      {/* Breakdown control */}
      <div className="row" style={{
        marginBottom: 12, padding: '6px 10px',
        background: '#fafbfc', borderRadius: 6, border: '1px solid #eee',
        gap: 8, alignItems: 'center',
      }}>
        <span style={{ fontSize: 12, color: '#666' }}>Break down by:</span>
        <select
          value={breakdownField}
          onChange={(e) => setBreakdownField(e.target.value)}
          style={{ fontSize: 12, padding: '4px 6px', flex: 1, maxWidth: 240 }}
        >
          <option value="">— pick a field —</option>
          {breakdownFieldOptions.map((c) => (
            <option key={c.field} value={`${c.field_type}:${c.field}`}>
              {c.label || c.field}
            </option>
          ))}
        </select>
        <button onClick={runBreakdown} disabled={loading || !breakdownField} style={{ fontSize: 12 }}>
          Compare
        </button>
        {breakdownResult && (
          <button className="secondary" onClick={load} style={{ fontSize: 12 }}>
            ← Show single
          </button>
        )}
      </div>

      {breakdownResult ? (
        <RetentionBreakdownView result={breakdownResult} />
      ) : (
        <RetentionBody data={data} err={err} loading={loading} onRetry={load} />
      )}
    </div>
  );
}

function RetentionBreakdownView({ result }) {
  if (result.series.length === 0) {
    return <p className="muted">No values found for this breakdown field in the selected range.</p>;
  }

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        Splitting by <code style={{ background: '#fff5e0', padding: '1px 4px', borderRadius: 3 }}>
          {result.breakdown_field}
        </code> · top {result.series.length} values
      </div>
      <table className="breakdown-table">
        <thead>
          <tr>
            <th>Segment</th>
            <th>Users</th>
            <th>D1</th>
            <th>D7</th>
            <th>D30</th>
          </tr>
        </thead>
        <tbody>
          {result.series.map((s, i) => (
            <tr key={i}>
              <td>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 10, height: 10, background: SERIES_COLORS[i % SERIES_COLORS.length], borderRadius: 2 }} />
                  <strong>{s.series_label}</strong>
                </span>
              </td>
              <td>{s.total_users.toLocaleString()}</td>
              <td>{(s.d1_rate * 100).toFixed(1)}%</td>
              <td>{(s.d7_rate * 100).toFixed(1)}%</td>
              <td>{(s.d30_rate * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RetentionBody({ data, err, loading, onRetry }) {
  if (err) return <ErrorBox error={err} onRetry={onRetry} />;
  if (loading || !data) {
    return (
      <>
        <div className="kpis">
          <div className="kpi"><div className="skeleton-line" /></div>
          <div className="kpi"><div className="skeleton-line" /></div>
          <div className="kpi"><div className="skeleton-line" /></div>
        </div>
        <div className="skeleton-block" style={{ height: 200 }} />
      </>
    );
  }

  const h = data.headline;
  const cohorts = data.cohorts;

  if (!cohorts || cohorts.length === 0) {
    return (
      <div className="empty-state">
        <div style={{ fontSize: 32, marginBottom: 8 }}>📅</div>
        <div style={{ fontWeight: 500, marginBottom: 4 }}>No retention data</div>
        <div className="muted" style={{ fontSize: 13, maxWidth: 460, textAlign: 'center' }}>
          Either the dataset is too new, the cohort filter matched zero users, or the date range is empty.
        </div>
      </div>
    );
  }

  const today = new Date();
  const earliest = new Date(cohorts[0].cohort_date);
  const daysSpan = Math.floor((today - earliest) / (1000 * 60 * 60 * 24));
  const d1Ready = daysSpan >= 1, d7Ready = daysSpan >= 7, d30Ready = daysSpan >= 30;

  const d1Spark = cohorts.map((c) => +(c.d1_rate * 100).toFixed(1));
  const d7Spark = cohorts.map((c) => +(c.d7_rate * 100).toFixed(1));
  const d30Spark = cohorts.map((c) => +(c.d30_rate * 100).toFixed(1));

  const chartData = cohorts.map((c) => ({
    date: c.cohort_date.slice(5),
    D1: +(c.d1_rate * 100).toFixed(1),
    D7: +(c.d7_rate * 100).toFixed(1),
    D30: +(c.d30_rate * 100).toFixed(1),
  }));

  // Headline rates (d1_avg / d7_avg / d30_avg) are already in 0-1 range.
  // Multiply by 100 for display. Don't divide by total_users -- that's
  // the v0.9.1 bugfix.
  const fmtRate = (rate) => (rate ? `${(rate * 100).toFixed(1)}%` : '—');

  return (
    <>
      <div className="kpis">
        <KpiTile label="Day 1 retention" value={d1Ready ? fmtRate(h.d1_avg) : '—'}
                 spark={d1Spark} notReady={!d1Ready}
                 tooltipText={d1Ready ? null : 'Need 1+ day past cohort'} />
        <KpiTile label="Day 7 retention" value={d7Ready ? fmtRate(h.d7_avg) : '—'}
                 spark={d7Spark} notReady={!d7Ready}
                 tooltipText={d7Ready ? null : 'Need 7+ days past earliest cohort'} />
        <KpiTile label="Day 30 retention" value={d30Ready ? fmtRate(h.d30_avg) : '—'}
                 spark={d30Spark} notReady={!d30Ready}
                 tooltipText={d30Ready ? null : 'Need 30+ days past earliest cohort'} />
      </div>
      <div style={{ height: 260 }}>
        <ResponsiveContainer>
          <LineChart data={chartData}>
            <CartesianGrid stroke="#eee" />
            <XAxis dataKey="date" fontSize={12} />
            <YAxis unit="%" fontSize={12} />
            <Tooltip />
            <Line type="monotone" dataKey="D1" stroke="#4f7cff" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="D7" stroke="#e6a23c" dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="D30" stroke="#d94f4f" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

function KpiTile({ label, value, spark, notReady, tooltipText }) {
  return (
    <div className="kpi" title={tooltipText || ''}>
      <div className="label">{label}</div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 8, marginTop: 4 }}>
        <div className="value" style={{ color: notReady ? '#aaa' : undefined }}>{value}</div>
        {!notReady && spark && spark.length >= 2 && <Sparkline data={spark} />}
      </div>
      {notReady && tooltipText && (
        <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>{tooltipText}</div>
      )}
    </div>
  );
}

export function CardHeader({ title, onViewSql, cohortCount }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
      <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
        {title}
        {cohortCount > 0 && (
          <span className="cohort-applied-pill" title={`Filtered by ${cohortCount} cohort filter(s)`}>
            cohort: {cohortCount}
          </span>
        )}
      </h2>
      {onViewSql && (
        <button className="secondary" onClick={onViewSql}
                style={{ fontSize: 11, padding: '3px 8px', color: '#666' }}
                title="See the SQL query that produced this">
          {'< / >'} View SQL
        </button>
      )}
    </div>
  );
}
