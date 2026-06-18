import { useEffect, useState } from 'react';
import { api, clearAuth, getAuthDigest, ymd } from './api/client';
import { getStateFromUrl, updateUrl } from './api/url_state';
import CohortBuilder from './components/CohortBuilder';
import ConnectionForm from './components/ConnectionForm';
import DashboardOverview from './components/DashboardOverview';
import DateRangePicker from './components/DateRangePicker';
import EventExplorer from './components/EventExplorer';
import FreshnessBadge from './components/FreshnessBadge';
import FunnelBuilder from './components/FunnelBuilder';
import InsightsPanel from './components/InsightsPanel';
import LoginScreen from './components/LoginScreen';
import NLQBox from './components/NLQBox';
import ProfileSwitcher from './components/ProfileSwitcher';
import RetentionDashboard from './components/RetentionDashboard';
import ShareButton from './components/ShareButton';
import UserProfiler from './components/UserProfiler';

// Tab definitions — single source of truth so nav and routing stay in sync.
const TABS = [
  { id: 'dashboard',    label: 'Dashboard' },
  { id: 'profile',      label: 'User Profile' },
  { id: 'investigator', label: 'Investigator' },
  { id: 'funnel',       label: 'Funnel' },
  { id: 'retention',    label: 'Retention' },
];

export default function App() {
  // ---- Auth state ----
  // null = unknown (still checking), false = no auth needed OR not logged in,
  // true = logged in (or auth not required)
  const [authState, setAuthState] = useState({ loading: true, required: false, ok: false });

  useEffect(() => {
    api.authStatus()
      .then((s) => {
        if (!s.enabled) {
          setAuthState({ loading: false, required: false, ok: true });
        } else {
          // Auth required. Are we already authed?
          const haveDigest = !!getAuthDigest();
          setAuthState({ loading: false, required: true, ok: haveDigest });
        }
      })
      .catch(() => {
        // If we can't reach the server, fail open visually -- the next API call will surface errors
        setAuthState({ loading: false, required: false, ok: true });
      });
  }, []);

  if (authState.loading) {
    return <div className="app"><p className="muted">Loading…</p></div>;
  }

  if (authState.required && !authState.ok) {
    return <LoginScreen onLoggedIn={() => setAuthState({ loading: false, required: true, ok: true })} />;
  }

  return <Main onSignOut={() => {
    clearAuth();
    setAuthState({ loading: false, required: true, ok: false });
  }} authRequired={authState.required} />;
}

function Main({ onSignOut, authRequired }) {
  const [conn, setConn] = useState(null);
  const [funnelResult, setFunnelResult] = useState(null);
  const [funnelEvents, setFunnelEvents] = useState({ start: null, end: null });

  // Hydrate state from URL hash if present (shareable links)
  const urlState = getStateFromUrl();
  const [dateRange, setDateRange] = useState(
    urlState?.dateRange || { start: ymd(30), end: ymd(1) }
  );
  const [cohort, setCohort] = useState(urlState?.cohort || []);

  const [showAddProfile, setShowAddProfile] = useState(false);
  const [fields, setFields] = useState({ columns: [], user_properties: [], event_params: [] });

  // Active tab — defaults to dashboard. Tab is intentionally NOT persisted to
  // the URL hash (url_state.js doesn't know about it). On reload you land on
  // Dashboard. Each tab's component state is preserved in memory while you
  // stay on the same browser session; switching tabs is instant.
  const [activeTab, setActiveTab] = useState('dashboard');

  useEffect(() => {
    api.connection().then(setConn).catch(() => setConn({ connected: false }));
  }, []);

  // Update URL when state changes (so reload preserves view + share works)
  useEffect(() => {
    updateUrl({ dateRange, cohort });
  }, [dateRange, cohort]);

  // Discoverable cohort fields (used by CohortBuilder + breakdown pickers)
  useEffect(() => {
    if (!conn?.connected) return;
    api.cohortFields(dateRange.start, dateRange.end)
      .then(setFields)
      .catch(() => {});
  }, [conn?.connected, conn?.profile_id, dateRange]);

  if (!conn) return <div className="app"><p className="muted">Loading…</p></div>;

  if (!conn.connected) {
    return (
      <div className="app">
        <div className="header"><h1>InsightPM</h1></div>
        <ConnectionForm onConnected={setConn} />
      </div>
    );
  }

  return (
    <div className="app">
      {/* === Sticky top region: header + tabs + date range stay pinned ===
          We wrap them in a single sticky container so they move together.
          z-index keeps them above scrolling content; Cohort stays in normal
          flow below because expanded filter pickers need page space. */}
      <div className="sticky-top">
        {/* Header: brand, freshness, share, profile switcher, sign out */}
        <div className="header">
          <h1>InsightPM</h1>
          <div className="row" style={{ gap: 10, alignItems: 'center' }}>
            <FreshnessBadge key={conn.profile_id || 'env'} />
            <ShareButton dateRange={dateRange} cohort={cohort} />
            <ProfileSwitcher
              currentConn={conn}
              onSwitch={(c) => {
                setConn(c);
                setFunnelResult(null);
                setFunnelEvents({ start: null, end: null });
                setCohort([]);
              }}
              onAddNew={() => setShowAddProfile(true)}
            />
            {authRequired && (
              <button
                className="secondary"
                onClick={() => { if (confirm('Sign out?')) onSignOut(); }}
                style={{ fontSize: 11, padding: '4px 10px' }}
                title="Sign out"
              >
                ⎋
              </button>
            )}
          </div>
        </div>

        {/* Tab navigation */}
        <div className="tab-nav">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab-btn ${activeTab === t.id ? 'active' : ''}`}
              onClick={() => setActiveTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Date range — sticky with the header */}
        <div className="card sticky-date-card" style={{ padding: '12px 20px' }}>
          <DateRangePicker value={dateRange} onChange={setDateRange} />
        </div>
      </div>

      {showAddProfile && (
        <div onClick={() => setShowAddProfile(false)}
             style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
                      zIndex: 100, display: 'flex', alignItems: 'flex-start',
                      justifyContent: 'center', padding: 40 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ maxWidth: 720, width: '100%' }}>
            <ConnectionForm embedded onCancel={() => setShowAddProfile(false)}
                            onConnected={(c) => { setConn(c); setShowAddProfile(false); }} />
          </div>
        </div>
      )}

      {/* === Cohort builder (in normal scroll flow, not sticky) === */}
      <div className="card" style={{ padding: '12px 20px' }}>
        <CohortBuilder dateRange={dateRange} value={cohort} onChange={setCohort} />
      </div>

      {/* === Tab content === */}
      {/* Each block renders only when its tab is active. We rely on React
          unmount/remount to keep memory low; if you want to preserve in-progress
          state across tab switches, change `activeTab === 'x' && (...)` to
          `<div style={{display: activeTab === 'x' ? 'block' : 'none'}}>...</div>`. */}

      {activeTab === 'dashboard' && (
        <>
          <DashboardOverview dateRange={dateRange} cohort={cohort} />
          <NLQBox />
          <EventExplorer dateRange={dateRange} cohort={cohort} />
        </>
      )}

      {activeTab === 'profile' && (
        <UserProfiler dateRange={dateRange} />
      )}

      {activeTab === 'investigator' && (
        // Investigator tab shows the same insights panel — clicking Investigate
        // on any insight opens the loading overlay + renders results inline,
        // exactly as on Dashboard. This tab is a focused view of the same data.
        <InsightsPanel
          funnelResult={funnelResult}
          funnelEvents={funnelEvents}
          dateRange={dateRange}
          cohort={cohort}
        />
      )}

      {activeTab === 'funnel' && (
        <FunnelBuilder
          dateRange={dateRange}
          cohort={cohort}
          fields={fields}
          onResult={setFunnelResult}
          onEventsChange={setFunnelEvents}
        />
      )}

      {activeTab === 'retention' && (
        <RetentionDashboard dateRange={dateRange} cohort={cohort} fields={fields} />
      )}
    </div>
  );
}
