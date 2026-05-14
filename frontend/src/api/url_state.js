// Shareable URL state.
//
// We encode {dateRange, cohort, savedFunnelId} into the URL hash.
// Why hash, not query string:
// - Hash isn't sent to the server (no leaking cohort filters into server logs)
// - Doesn't trigger page reloads on change
// - Works without backend support
//
// Why JSON-then-base64 instead of separate query params:
// - One state blob is easier to encode/decode atomically
// - Cohort filters are nested objects, painful as flat params
// - Easy to version (add a 'v' field) for future-proofing
//
// Trade-off: URL hash gets ugly. We accept that -- this is a tool not a
// landing page.

const HASH_KEY = 's';
const VERSION = 1;

export function encodeState({ dateRange, cohort, savedFunnelId, savedCohortId }) {
  // Don't include falsy/empty values to keep URLs short
  const state = { v: VERSION };
  if (dateRange?.start && dateRange?.end) state.d = [dateRange.start, dateRange.end];
  if (cohort && cohort.length > 0) state.c = cohort;
  if (savedFunnelId) state.f = savedFunnelId;
  if (savedCohortId) state.sc = savedCohortId;
  // Only ever encode if there's actually state to share
  if (Object.keys(state).length === 1) return null;

  try {
    const json = JSON.stringify(state);
    // base64-url-safe encoding (browsers support btoa, but we replace +/=)
    const b64 = btoa(unescape(encodeURIComponent(json)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    return b64;
  } catch (e) {
    console.warn('encodeState failed:', e);
    return null;
  }
}

export function decodeState(encoded) {
  if (!encoded) return null;
  try {
    const b64 = encoded.replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '==='.slice((b64.length + 3) % 4);
    const json = decodeURIComponent(escape(atob(padded)));
    const state = JSON.parse(json);
    if (state.v !== VERSION) {
      console.warn('Encoded state version mismatch');
      return null;
    }
    return {
      dateRange: state.d ? { start: state.d[0], end: state.d[1] } : null,
      cohort: state.c || [],
      savedFunnelId: state.f || null,
      savedCohortId: state.sc || null,
    };
  } catch (e) {
    console.warn('decodeState failed:', e);
    return null;
  }
}

// Read current state from window.location.hash (if any)
export function getStateFromUrl() {
  if (typeof window === 'undefined') return null;
  const hash = window.location.hash.replace(/^#/, '');
  if (!hash) return null;
  // Hash format: 's=<encoded>'
  const params = new URLSearchParams(hash);
  const encoded = params.get(HASH_KEY);
  return encoded ? decodeState(encoded) : null;
}

// Build a URL containing the encoded state
export function buildShareUrl({ dateRange, cohort, savedFunnelId, savedCohortId }) {
  const encoded = encodeState({ dateRange, cohort, savedFunnelId, savedCohortId });
  if (!encoded) return window.location.href.split('#')[0];
  const base = window.location.href.split('#')[0];
  return `${base}#${HASH_KEY}=${encoded}`;
}

// Update the browser URL (without a reload) with the current state
export function updateUrl({ dateRange, cohort, savedFunnelId, savedCohortId }) {
  const encoded = encodeState({ dateRange, cohort, savedFunnelId, savedCohortId });
  const newHash = encoded ? `${HASH_KEY}=${encoded}` : '';
  // Use replaceState so we don't fill up browser history with every filter change
  if (typeof window !== 'undefined') {
    const newUrl = window.location.pathname + window.location.search +
                   (newHash ? '#' + newHash : '');
    window.history.replaceState(null, '', newUrl);
  }
}
