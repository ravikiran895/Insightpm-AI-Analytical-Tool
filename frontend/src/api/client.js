// One thin fetch wrapper. All endpoints called through `api.*`.
const BASE = '/api';

// Auth digest is stored in sessionStorage so a tab close clears the session.
// The backend never sees the plain password; only the digest of it.
const AUTH_KEY = 'insightpm.auth.digest';

export function getAuthDigest() {
  return sessionStorage.getItem(AUTH_KEY);
}

export function setAuthDigest(digest) {
  if (digest) sessionStorage.setItem(AUTH_KEY, digest);
  else sessionStorage.removeItem(AUTH_KEY);
}

export function clearAuth() {
  sessionStorage.removeItem(AUTH_KEY);
}

async function req(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  // Attach auth header if we have a digest. Backend ignores it when auth is disabled.
  const digest = getAuthDigest();
  if (digest) headers['X-InsightPM-Auth'] = digest;

  const res = await fetch(BASE + path, { ...opts, headers });

  if (res.status === 401) {
    // Auth required but missing/wrong. Clear the digest so the user re-logs in.
    clearAuth();
    const err = new Error('Authentication required.');
    err.kind = 'auth_required';
    err.status = 401;
    throw err;
  }

  if (!res.ok) {
    const text = await res.text();
    try {
      const j = JSON.parse(text);
      const err = new Error(j.detail || `HTTP ${res.status}`);
      err.kind = j.kind || 'internal_error';
      err.detail = j.detail;
      throw err;
    } catch (parseErr) {
      if (parseErr.kind) throw parseErr;
      const err = new Error(text || `HTTP ${res.status}`);
      err.kind = 'internal_error';
      throw err;
    }
  }
  return res.json();
}

// Default a date range used when no other source provides one.
// Argument is days back from today.
export function ymd(daysBack) {
  const d = new Date();
  d.setDate(d.getDate() - daysBack);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}${m}${day}`;
}

export const api = {
  // Auth
  authStatus: () => req('/auth/status'),
  authCheck: (password) =>
    req('/auth/check', { method: 'POST', body: JSON.stringify({ password }) }),

  // Connection / profiles
  connection: () => req('/connection'),
  connect: (body) => req('/connect', { method: 'POST', body: JSON.stringify(body) }),
  profiles: () => req('/profiles'),
  useProfile: (id) => req(`/profiles/${id}/use`, { method: 'POST' }),
  setDefaultProfile: (id) => req(`/profiles/${id}/default`, { method: 'POST' }),
  deleteProfile: (id) => req(`/profiles/${id}`, { method: 'DELETE' }),

  // Core analytics
  events: (start, end, limit = 50) =>
    req(`/events?start_date=${start}&end_date=${end}&limit=${limit}`),
  eventsWithCohort: (body) =>
    req('/events', { method: 'POST', body: JSON.stringify(body) }),
  activity: (start, end) => req(`/activity?start_date=${start}&end_date=${end}`),
  retention: (start, end) => req(`/retention?start_date=${start}&end_date=${end}`),
  retentionWithCohort: (body) =>
    req('/retention', { method: 'POST', body: JSON.stringify(body) }),
  funnel: (body) => req('/funnel', { method: 'POST', body: JSON.stringify(body) }),
  funnelSuggest: (body) =>
    req('/funnel/suggest', { method: 'POST', body: JSON.stringify(body) }),

  // Insights + AI
  insights: (body) => req('/insights', { method: 'POST', body: JSON.stringify(body) }),
  explainInsight: (body) =>
    req('/insights/explain', { method: 'POST', body: JSON.stringify(body) }),
  investigateInsight: (body) =>
    req('/insights/investigate', { method: 'POST', body: JSON.stringify(body) }),
  nlq: (question) =>
    req('/nlq', { method: 'POST', body: JSON.stringify({ question }) }),

  // System
  freshness: () => req('/freshness'),
  cacheStats: () => req('/cache/stats'),
  sqlPreview: (body) => req('/sql-preview', { method: 'POST', body: JSON.stringify(body) }),

  // Cohort fields
  cohortFields: (start, end) =>
    req(`/cohort-fields?start_date=${start}&end_date=${end}`),

  // Saved funnels
  savedFunnels: () => req('/saved-funnels'),
  createSavedFunnel: (body) =>
    req('/saved-funnels', { method: 'POST', body: JSON.stringify(body) }),
  updateSavedFunnel: (id, body) =>
    req(`/saved-funnels/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteSavedFunnel: (id) =>
    req(`/saved-funnels/${id}`, { method: 'DELETE' }),

  // Saved cohorts (Phase 9)
  savedCohorts: () => req('/saved-cohorts'),
  createSavedCohort: (body) =>
    req('/saved-cohorts', { method: 'POST', body: JSON.stringify(body) }),
  updateSavedCohort: (id, body) =>
    req(`/saved-cohorts/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteSavedCohort: (id) =>
    req(`/saved-cohorts/${id}`, { method: 'DELETE' }),

  // Breakdowns
  funnelBreakdown: (body) =>
    req('/funnel/breakdown', { method: 'POST', body: JSON.stringify(body) }),
  retentionBreakdown: (body) =>
    req('/retention/breakdown', { method: 'POST', body: JSON.stringify(body) }),

  // User Behavior Profile
  profileUser: (body) =>
    req('/users/profile', { method: 'POST', body: JSON.stringify(body) }),
  recentUsers: (start, end, limit = 20) =>
    req(`/users/recent?start_date=${start}&end_date=${end}&limit=${limit}`),
};
