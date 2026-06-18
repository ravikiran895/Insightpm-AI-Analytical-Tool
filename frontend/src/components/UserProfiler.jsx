import { useEffect, useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';
import LoadingOverlay from './LoadingOverlay';
import { CardHeader } from './RetentionDashboard';

// User Behavior Profiler — the USP feature.
// Pick a user (or paste an ID) → get an AI-generated narrative + metrics + journey.

const PATTERN_LABELS = {
  power_user: 'Power user',
  returning_visitor: 'Returning visitor',
  one_and_done: 'One-and-done',
  drifted_off: 'Drifted off',
  casual: 'Casual user',
  no_data: 'Insufficient data',
};

const PATTERN_DESCRIPTIONS = {
  power_user: 'High frequency, strong engagement, multiple sessions across many days.',
  returning_visitor: 'Comes back periodically — moderate frequency, focused activity per visit.',
  one_and_done: 'Single session and disappeared — likely friction or wrong audience.',
  drifted_off: 'Strong start, declining engagement — early churn signal.',
  casual: 'Light usage with no strong pattern emerging.',
  no_data: 'Not enough events in the date range to classify behavior.',
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
            fontFamily: 'var(--font-mono)',
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
              {recentUsers && recentUsers.filter((u) => u && u.user_id).length === 0 && (
                <div className="muted" style={{ padding: 12, fontSize: 13 }}>
                  No users found in this date range.
                </div>
              )}
              {recentUsers && recentUsers.filter((u) => u && u.user_id).length > 0 && (
                <div style={{ maxHeight: 320, overflow: 'auto' }}>
                  <div className="muted" style={{ padding: '8px 12px', fontSize: 11, borderBottom: '1px solid var(--border)' }}>
                    Top {recentUsers.filter((u) => u && u.user_id).length} users by event count
                  </div>
                  {recentUsers.filter((u) => u && u.user_id).map((u) => (
                    <div
                      key={u.user_id}
                      onClick={() => { setUserIdInput(u.user_id); profileFor(u.user_id); }}
                      className="recent-user-row"
                    >
                      <div className="recent-user-id">{String(u.user_id).slice(0, 24)}…</div>
                      <div className="muted" style={{ fontSize: 11 }}>
                        {u.event_count ?? 0} events · {u.active_days ?? 0} active days
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

      {!busy && !profile && !err && (
        <p className="muted">
          Pick any user and get an AI-generated story of what they did, when, and why their
          behavior matters — plus recommendations specific to their pattern.
        </p>
      )}

      {profile && <ProfileResult profile={profile} />}

      <LoadingOverlay
        busy={busy}
        title="Building user behavior profile"
        desc="Fetching this user's full event journey, then asking AI to write their story."
        steps={[
          { name: 'Fetch event journey from BigQuery', duration: 800 },
          { name: 'Compute aggregate metrics + top events', duration: 600 },
          { name: 'Classify behavior pattern', duration: 500 },
          { name: 'AI synthesis (story + recommendations)', duration: 1400 },
        ]}
      />
    </div>
  );
}

function ProfileResult({ profile }) {
  const { metrics, pattern, narrative, narrative_source, journey_sample, journey_total_events, user_id } = profile;
  const [showJourney, setShowJourney] = useState(false);

  const patternLabel = PATTERN_LABELS[pattern?.label] || 'User behavior';
  const patternDesc = PATTERN_DESCRIPTIONS[pattern?.label] || '';

  // Parse narrative into structured Story / Pattern / Recommendations if available.
  // Falls back gracefully to flat rendering if the LLM didn't structure it.
  const parsed = parseNarrative(narrative);

  // Defensive: backend should always provide these, but check anyway.
  const safeUserId = user_id || '—';
  const safeMetrics = metrics || {};
  const safeTopEvents = Array.isArray(safeMetrics.top_events) ? safeMetrics.top_events : [];
  const safeJourney = Array.isArray(journey_sample) ? journey_sample : [];

  return (
    <div className="dossier">
      {/* Hero — gradient background, avatar, pattern as headline */}
      <div className="dossier-hero">
        <div className="dossier-avatar">{initialsFor(safeUserId)}</div>
        <div className="dossier-hero-text">
          <div className="dossier-uid">{safeUserId}</div>
          <div className="dossier-headline">{patternLabel}</div>
          {patternDesc && <div className="dossier-sub">{patternDesc}</div>}
        </div>
        {narrative_source && (
          <span className="ai-badge dossier-source-badge">
            {narrative_source === 'gemini' && '✨ Gemini'}
            {narrative_source === 'anthropic' && '✨ Claude'}
            {narrative_source === 'template' && 'Rule-based'}
          </span>
        )}
      </div>

      {/* Metrics strip */}
      <div className="profile-metrics dossier-metrics">
        <Metric label="Events" value={(safeMetrics.event_count ?? 0).toLocaleString()} />
        <Metric label="Sessions" value={safeMetrics.session_count ?? 0} />
        <Metric label="Active days" value={safeMetrics.active_days ?? 0} />
        <Metric label="Lifespan" value={`${safeMetrics.lifespan_days ?? 0}d`} />
        <Metric label="Engagement" value={`${safeMetrics.total_engagement_minutes ?? 0}m`} />
        <Metric label="Country" value={safeMetrics.country || '—'} />
      </div>

      {/* Structured narrative cards (Story / Pattern / Recommendations) */}
      {parsed.isStructured ? (
        <div className="narrative-stack">
          {parsed.story && (
            <NarrativeSection label="Story" tone="story">
              {renderInlineMarkdown(parsed.story)}
            </NarrativeSection>
          )}
          {parsed.pattern && (
            <NarrativeSection label="Pattern" tone="pattern">
              {renderInlineMarkdown(parsed.pattern)}
            </NarrativeSection>
          )}
          {parsed.recommendations && (
            <NarrativeSection label="Recommendations" tone="recs">
              {renderRecommendationList(parsed.recommendations)}
            </NarrativeSection>
          )}
        </div>
      ) : (
        // Fallback: unstructured narrative — render in the legacy flat box,
        // styled with our new tokens but using the old class names so it
        // looks consistent with everything else.
        <div className="narrative-box" style={{ marginTop: 12 }}>
          <div className="narrative-content">
            {renderMarkdownishNarrative(narrative)}
          </div>
          {narrative_source === 'template' && (
            <div className="muted" style={{ fontSize: 10, marginTop: 8, fontStyle: 'italic' }}>
              Set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env for richer AI-generated narratives.
            </div>
          )}
        </div>
      )}

      {/* Focus profile — horizontal bars derived from event mix */}
      {safeTopEvents.length > 0 && (
        <div className="focus-card">
          <div className="dossier-section-label">Focus profile</div>
          <FocusBars topEvents={safeTopEvents} />
        </div>
      )}

      {/* Top events list */}
      {safeTopEvents.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="dossier-section-label" style={{ marginBottom: 6 }}>Most frequent actions</div>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            {safeTopEvents.map((e, i) => (
              <span key={i} className="event-chip">
                <span>{e.event}</span>
                <span style={{ marginLeft: 4, color: 'var(--text-3)' }}>· {e.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Journey toggle (preserved from v0.9.2) */}
      {safeJourney.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <button
            className="secondary"
            onClick={() => setShowJourney(!showJourney)}
            style={{ fontSize: 12 }}
          >
            {showJourney ? '▾' : '▸'} Show journey
            ({safeJourney.length} of {journey_total_events ?? safeJourney.length} events shown)
          </button>
          {showJourney && (
            <div className="journey-list">
              {safeJourney.map((e, i) => (
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

function NarrativeSection({ label, tone, children }) {
  return (
    <div className={`narrative-card narrative-${tone}`}>
      <div className="narrative-card-label">{label}</div>
      <div className="narrative-card-body">{children}</div>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="profile-metric">
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 500, marginTop: 2, fontFamily: 'var(--font-mono)' }}>{value}</div>
    </div>
  );
}

// Compute initials from a user_pseudo_id — typically a long string, so we take
// the first two non-trivial characters. Falls back to "?" for safety.
function initialsFor(uid) {
  if (!uid || typeof uid !== 'string') return '?';
  const clean = uid.replace(/[^a-zA-Z0-9]/g, '');
  if (clean.length === 0) return '?';
  return clean.slice(0, 2).toUpperCase();
}

// Heuristic to assign user events to focus buckets. Mirrors the bucketing
// logic in the demo: monetization, engagement, exploration, social.
function FocusBars({ topEvents }) {
  const buckets = {
    Monetization: ['purchase', 'iap', 'subscription', 'buy', 'payment', 'store_view', 'cart'],
    Engagement: ['mission', 'level', 'achievement', 'play', 'session', 'game_start', 'complete'],
    Exploration: ['screen_view', 'page_view', 'view_item', 'browse', 'search', 'tab_select'],
    Social: ['share', 'invite', 'friend', 'chat', 'message', 'comment', 'like'],
  };

  const totals = { Monetization: 0, Engagement: 0, Exploration: 0, Social: 0 };
  const totalEvents = topEvents.reduce((s, e) => s + (e.count || 0), 0);

  for (const e of topEvents) {
    const name = (e.event || '').toLowerCase();
    for (const [bucket, keywords] of Object.entries(buckets)) {
      if (keywords.some((k) => name.includes(k))) {
        totals[bucket] += e.count || 0;
        break; // only count each event once
      }
    }
  }

  // Normalize to percentages of the categorized total (not raw total — many events fall in no bucket).
  const categorized = Object.values(totals).reduce((s, v) => s + v, 0);
  const base = categorized > 0 ? categorized : totalEvents;
  const rows = Object.entries(totals)
    .map(([k, v]) => ({ label: k, pct: base > 0 ? Math.round((v / base) * 100) : 0 }))
    .sort((a, b) => b.pct - a.pct);

  // If nothing categorized at all, don't render misleading zeros.
  if (rows.every((r) => r.pct === 0)) {
    return <div className="muted" style={{ fontSize: 12 }}>Not enough categorized events to compute focus.</div>;
  }

  return (
    <div className="focus-bars">
      {rows.map((r) => (
        <div className="focus-bar-row" key={r.label}>
          <div className="focus-bar-label">{r.label}</div>
          <div className="focus-bar-track">
            <div className="focus-bar-fill" style={{ width: `${r.pct}%` }} />
          </div>
          <div className="focus-bar-pct">{r.pct}%</div>
        </div>
      ))}
    </div>
  );
}

// Parse the LLM-generated narrative into Story / Pattern / Recommendations
// sections. The backend prompts ask the model to use these headers, but it
// doesn't always comply — when it doesn't, we fall back to flat rendering.
function parseNarrative(text) {
  if (!text || typeof text !== 'string') {
    return { isStructured: false, story: null, pattern: null, recommendations: null };
  }

  const storyMatch = text.match(/\*\*Story\*\*[:\s]*([\s\S]*?)(?=\*\*Pattern\*\*|\*\*Recommendations?\*\*|$)/i);
  const patternMatch = text.match(/\*\*Pattern\*\*[:\s]*([\s\S]*?)(?=\*\*Recommendations?\*\*|\*\*Story\*\*|$)/i);
  const recMatch = text.match(/\*\*Recommendations?\*\*[:\s]*([\s\S]*?)$/i);

  const story = storyMatch?.[1]?.trim() || null;
  const pattern = patternMatch?.[1]?.trim() || null;
  const recommendations = recMatch?.[1]?.trim() || null;

  return {
    isStructured: !!(story || pattern || recommendations),
    story,
    pattern,
    recommendations,
  };
}

// Render inline markdown (**bold** only) — used inside narrative cards.
function renderInlineMarkdown(text) {
  if (!text) return null;
  const lines = text.split('\n').filter((l) => l.trim().length > 0);
  return lines.map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    const rendered = parts.map((p, j) => {
      if (p.startsWith('**') && p.endsWith('**')) {
        return <strong key={j}>{p.slice(2, -2)}</strong>;
      }
      return <span key={j}>{p}</span>;
    });
    return (
      <div key={i} style={{ marginTop: i === 0 ? 0 : 8 }}>
        {rendered}
      </div>
    );
  });
}

// Render recommendations as a numbered task list. Splits on bullets/numbers.
function renderRecommendationList(text) {
  if (!text) return null;
  // Split on bullet markers (•, -, * at line start) or numbered (1., 2.)
  const items = text
    .split(/\n\s*(?:[•\-*]|\d+\.)\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  if (items.length <= 1) {
    // Just one paragraph — render as inline markdown
    return renderInlineMarkdown(items[0] || text);
  }

  return (
    <div className="rec-list">
      {items.map((item, i) => (
        <div className="rec-item" key={i}>
          <div className="rec-num">{i + 1}</div>
          <div className="rec-text">{renderInlineMarkdown(item)}</div>
        </div>
      ))}
    </div>
  );
}

// Legacy markdown-ish renderer — used only in fallback (unstructured narrative) path.
function renderMarkdownishNarrative(text) {
  if (!text) return null;
  const lines = text.split('\n');
  return lines.map((line, i) => {
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
