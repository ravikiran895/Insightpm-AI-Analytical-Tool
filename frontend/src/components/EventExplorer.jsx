import { useEffect, useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';
import { CardHeader } from './RetentionDashboard';
import SqlPreviewModal from './SqlPreviewModal';

export default function EventExplorer({ dateRange, cohort }) {
  const [events, setEvents] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showSql, setShowSql] = useState(false);

  function load() {
    setLoading(true);
    setErr(null);
    const hasCohort = cohort && cohort.length > 0;
    const promise = hasCohort
      ? api.eventsWithCohort({ start_date: dateRange.start, end_date: dateRange.end, cohort })
      : api.events(dateRange.start, dateRange.end, 25);
    promise.then((d) => setEvents(d.events)).catch(setErr).finally(() => setLoading(false));
  }

  useEffect(load, [dateRange, cohort]); // eslint-disable-line

  const maxUsers = events && events.length ? Math.max(...events.map((e) => e.unique_users)) : 1;

  return (
    <div className="card">
      <CardHeader title="Top events" cohortCount={cohort?.length || 0} onViewSql={() => setShowSql(true)} />
      {showSql && (
        <SqlPreviewModal
          kind="top_events"
          request={{ start_date: dateRange.start, end_date: dateRange.end, limit: 25 }}
          onClose={() => setShowSql(false)}
        />
      )}
      <ErrorBox error={err} onRetry={load} />
      {loading && (<><div className="skeleton-line" /><div className="skeleton-line" /><div className="skeleton-line" /></>)}
      {!loading && !err && events && events.length === 0 && (
        <div className="empty-state">
          <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
          <div style={{ fontWeight: 500 }}>No events</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
            {cohort && cohort.length > 0
              ? "Your cohort filter matched zero users in this date range."
              : "Try widening the date range or check your Firebase export."}
          </div>
        </div>
      )}
      {!loading && !err && events && events.length > 0 && (
        <table className="event-table">
          <thead>
            <tr>
              <th style={{ width: '38%' }}>Event</th>
              <th>Unique users</th>
              <th style={{ textAlign: 'right' }}>Total count</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => {
              const widthPct = (e.unique_users / maxUsers) * 100;
              return (
                <tr key={e.event_name}>
                  <td style={{ fontFamily: 'ui-monospace, SFMono-Regular, monospace', fontSize: 13 }}>
                    {e.event_name}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ flex: 1, height: 8, background: '#eef0f5', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', width: `${widthPct}%`, background: '#4f7cff',
                          opacity: 0.6 + 0.4 * (widthPct / 100),
                        }} />
                      </div>
                      <span style={{ minWidth: 60, textAlign: 'right', fontSize: 13 }}>
                        {e.unique_users.toLocaleString()}
                      </span>
                    </div>
                  </td>
                  <td style={{ textAlign: 'right', fontSize: 13, color: '#666' }}>
                    {e.event_count.toLocaleString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
