import { useEffect, useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';
import { CardHeader } from './RetentionDashboard';

// User Behavior Profiler — the USP feature.
// Pick a user (or paste an ID) → get an AI-generated narrative + metrics + journey.

const PATTERN_BADGES = {
  power_user: { color: '#1a7d3a', bg: '#e6f7ed', label: 'Power user' },
  returning_visitor: { color: '#3055d8', bg: '#e6efff', label: 'Returning' },
  one_and_done: { color: '#b00', bg: '#fde8e8', label: 'One-and-done' },
  drifted_off: { color: '#a86d11', bg: '#fff5e0', label: 'Drifted off' },
  casual: { color: '#666', bg: '#eee', label: 'Casual' },
  no_data: { color: '#666', bg: '#eee', label: 'No data' },
};

export default function UserProfiler({ dateRange }) {
  const [userIdInput, setUserIdInput] = useState('');
  const [profile, setProfile] = useState(null);
  const [recentUsers, setRecentUsers] = useState(null);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  function loadRecent() {
    if (recentUsers) return;
    setLoadingRecent(true);
    api.recentUsers(dateRange.start, dateRange.end, 20)
      .then((r) => setRecentUsers(r.users))
      .catch(() => setRecentUsers([]))
      .finally(() => setLoadingRecent(false));
  }

  // Reset on date range change.
  useEffect(() => {
    setRecentUsers(null);
    setProfile(null);
    setUserIdInput('');
  }, [dateRange]);

  async function profileFor(uid) {
    if (!uid?.trim()) return;
    setBusy(true);
    setErr(null);
    setProfile(null);
    setPickerOpen(false);
    try {
      const r = await api.profileUser({
        user_id: uid.trim(),
        start_date: dateRange.start,
        end_date: dateRange.end,
      });
      setProfile(r);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <CardHeader title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          User Behavior Profile
          <span className="usp-badge">USP</span>
        </span>
      } />

      <div className="row" style={{ gap: 8, marginBottom: 8 }}>
        <input
          placeholder="Paste a user_pseudo_id, or pick one from recent users →"
          value={userIdInput}
          onChange={(e) => setUserIdInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && profileFor(userIdInput)}
          style={{
            flex: 1,
            fontFamily: 'ui-monospace, SFMono-Regular, monospace',
            fontSize: 13,
          }}
        />
        <button
          onClick={() => profileFor(userIdInput)}
          disabled={busy || !userIdInput.trim()}
        >
          {busy ? 'Profiling…' : 'Profile'}
        </button>
        <div style={{ position: 'relative' }}>
          <button
            className="secondary"
            onClick={() => { setPickerOpen(!pickerOpen); loadRecent(); }}
            style={{ fontSize: 12 }}
          >
            🔍 Recent users
          </button>
          {pickerOpen && (
            <div className="recent-users-dropdown">
              {loadingRecent && <div className="muted" style={{ padding: 12, fontSize: 13 }}>Loading…</div>}
              {recentUsers && recentUsers.length === 0 && (
                <div className="muted" style={{ padding: 12, fontSize: 13 }}>
                  No users found in this date range.
                </div>
              )}
              {recentUsers && recentUsers.length > 0 && (
                <div style={{ maxHeight: 320, overflow: 'auto' }}>
                  <div className="muted" style={{ padding: '8px 12px', fontSize: 11, borderBottom: '1px solid #eee' }}>
                    Top {recentUsers.length} users by event count
                  </div>
                  {recentUsers.map((u) => (
                    <div
                      key={u.user_id}
                      onClick={() => { setUserIdInput(u.user_id); profileFor(u.user_id); }}
                      className="recent-user-row"
                    >
                      <div className="recent-user-id">{u.user_id.slice(0, 24)}…</div>
                      <div className="muted" style={{ fontSize: 11 }}>
                        {u.event_count} events · {u.active_days} active days
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <ErrorBox error={err} />

      {busy && (
        <>
          <div className="skeleton-line" style={{ width: '70%' }} />
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line" style={{ width: '85%' }} />
        </>
      )}

      {!busy && !profile && !err && (
        <p className="muted">
          Pick any user and get an AI-generated story of what they did, when, and why their
          behavior matters — plus recommendations specific to their pattern.
        </p>
      )}

      {profile && <ProfileResult profile={profile} />}
    </div>
  );
}

function ProfileResult({ profile }) {
  const { metrics, pattern, narrative, narrative_source, journey_sample, journey_total_events, user_id } = profile;
  const badge = PATTERN_BADGES[pattern.label] || PATTERN_BADGES.casual;
  const [showJourney, setShowJourney] = useState(false);

  return (
    <div>
      {/* Header strip with user id + pattern badge */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '10px 12px', background: '#fafbfc',
        border: '1px solid #eee', borderRadius: 6, marginBottom: 12,
      }}>
        <div>
          <div className="muted" style={{ fontSize: 11 }}>USER</div>
          <div style={{
            fontFamily: 'ui-monospace, SFMono-Regular, monospace',
            fontSize: 13, marginTop: 2,
          }}>
            {user_id}
          </div>
        </div>
        <span className="pattern-pill" style={{ background: badge.bg, color: badge.color }}>
          {badge.label}
        </span>
      </div>

      {/* Metrics strip */}
      <div className="profile-metrics">
        <Metric label="Events" value={metrics.event_count.toLocaleString()} />
        <Metric label="Sessions" value={metrics.session_count} />
        <Metric label="Active days" value={metrics.active_days} />
        <Metric label="Lifespan" value={`${metrics.lifespan_days}d`} />
        <Metric label="Engagement" value={`${metrics.total_engagement_minutes}m`} />
        <Metric label="Country" value={metrics.country || '—'} />
      </div>

      {/* Narrative */}
      <div className="narrative-box">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span className="explanation-source-tag">
            {narrative_source === 'gemini' && '✨ Gemini narrative'}
            {narrative_source === 'anthropic' && '✨ Claude narrative'}
            {narrative_source === 'template' && 'Rule-based narrative'}
          </span>
        </div>
        <div className="narrative-content">
          {renderMarkdownishNarrative(narrative)}
        </div>
        {narrative_source === 'template' && (
          <div className="muted" style={{ fontSize: 10, marginTop: 8, fontStyle: 'italic' }}>
            Set GEMINI_API_KEY in .env for richer AI-generated narratives.
          </div>
        )}
      </div>

      {/* Top events */}
      {metrics.top_events.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', marginBottom: 6 }}>
            Most frequent actions
          </div>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            {metrics.top_events.map((e, i) => (
              <span key={i} className="event-chip">
                <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, monospace' }}>{e.event}</span>
                <span style={{ marginLeft: 4, color: '#888' }}>· {e.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Journey toggle */}
      {journey_sample.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <button
            className="secondary"
            onClick={() => setShowJourney(!showJourney)}
            style={{ fontSize: 12 }}
          >
            {showJourney ? '▾' : '▸'} Show journey
            ({journey_sample.length} of {journey_total_events} events shown)
          </button>
          {showJourney && (
            <div className="journey-list">
              {journey_sample.map((e, i) => (
                <div key={i} className="journey-row">
                  <div className="journey-time">
                    {e.event_time?.replace('T', ' ').slice(0, 19) || ''}
                  </div>
                  <div className="journey-event">{e.event_name}</div>
                  <div className="journey-context muted">
                    {e.screen_name || e.page_title || ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="profile-metric">
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2 }}>{value}</div>
    </div>
  );
}

// Tiny markdown-ish renderer for **bold** and \n. Keeps the dependency footprint zero.
function renderMarkdownishNarrative(text) {
  if (!text) return null;
  const lines = text.split('\n');
  return lines.map((line, i) => {
    // Render **bold** runs
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    const rendered = parts.map((p, j) => {
      if (p.startsWith('**') && p.endsWith('**')) {
        return <strong key={j}>{p.slice(2, -2)}</strong>;
      }
      return <span key={j}>{p}</span>;
    });
    if (line.trim().startsWith('-')) {
      return (
        <div key={i} style={{ marginLeft: 12, marginTop: 4, fontSize: 13 }}>
          • {rendered.slice(1)}
        </div>
      );
    }
    return (
      <div key={i} style={{ marginTop: line.trim() ? 6 : 0, fontSize: 13, lineHeight: 1.5 }}>
        {rendered}
      </div>
    );
  });
}
