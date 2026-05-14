// Centralized error display so we get consistent messaging across components
// instead of every component rolling its own div.error.
//
// Why this exists: 'Internal Server Error' tells a PM nothing. The backend
// already classifies errors by kind (permission_denied, not_found, etc.).
// Here we add an actionable hint per kind.

const HINTS = {
  permission_denied:
    'Open the GCP IAM page and add "BigQuery Data Viewer" + "BigQuery Job User" roles to your service account.',
  not_found:
    'Double-check your project_id and dataset_id on the connection screen. The dataset name should look like analytics_NNNNNNNNN.',
  quota_exceeded:
    'BigQuery hit a rate limit. Wait a minute and refresh.',
  internal_error: null,
};

export default function ErrorBox({ error, onRetry }) {
  if (!error) return null;

  // Error can be a string (legacy) or an object with detail/kind from our handler.
  let message, kind;
  if (typeof error === 'string') {
    try {
      const parsed = JSON.parse(error);
      message = parsed.detail || error;
      kind = parsed.kind;
    } catch {
      message = error;
      kind = 'internal_error';
    }
  } else {
    message = error.detail || error.message || String(error);
    kind = error.kind || 'internal_error';
  }

  const hint = HINTS[kind];

  return (
    <div className="error">
      <div style={{ fontWeight: 500, marginBottom: hint ? 6 : 0 }}>{message}</div>
      {hint && <div style={{ fontSize: 12, opacity: 0.8 }}>💡 {hint}</div>}
      {onRetry && (
        <button
          className="secondary"
          style={{ marginTop: 8, fontSize: 12, padding: '4px 10px' }}
          onClick={onRetry}
        >
          Retry
        </button>
      )}
    </div>
  );
}
