import { useEffect, useState } from 'react';
import { api } from '../api/client';

// Modal that shows the SQL behind a chart. Triggered by a small "View SQL"
// link on each card.
//
// Why this matters: the single biggest reason PMs distrust analytics tools
// is "where do these numbers come from?". Showing the actual SQL --
// parameterized, with bound values inline -- is the cheapest possible answer.

export default function SqlPreviewModal({ kind, request, onClose }) {
  const [sql, setSql] = useState(null);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!kind || !request) return;
    api.sqlPreview({ kind, ...request })
      .then((r) => setSql(r.sql))
      .catch((e) => setErr(e.message));
  }, [kind, request]);

  function copy() {
    if (!sql) return;
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#fff',
          borderRadius: 10,
          maxWidth: 900,
          width: '100%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 600 }}>SQL — {kind}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="secondary" onClick={copy} style={{ fontSize: 12 }}>
              {copied ? '✓ Copied' : 'Copy'}
            </button>
            <button onClick={onClose} style={{ fontSize: 12 }}>Close</button>
          </div>
        </div>
        <div style={{ padding: 20, overflow: 'auto', flex: 1 }}>
          {err && <div className="error">{err}</div>}
          {!sql && !err && <div className="muted">Loading SQL…</div>}
          {sql && (
            <pre style={{
              fontFamily: 'ui-monospace, SFMono-Regular, monospace',
              fontSize: 12,
              lineHeight: 1.5,
              background: '#0d1117',
              color: '#e6edf3',
              padding: 16,
              borderRadius: 6,
              overflow: 'auto',
              margin: 0,
            }}>
              {sql}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
