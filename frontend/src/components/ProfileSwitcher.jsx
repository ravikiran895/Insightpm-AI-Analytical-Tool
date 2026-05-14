import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';

// Header dropdown for switching between saved BigQuery connections.
// Click the current connection -> dropdown shows other profiles + "Add new" + "Manage".
export default function ProfileSwitcher({ currentConn, onSwitch, onAddNew }) {
  const [profiles, setProfiles] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const ref = useRef(null);

  function loadProfiles() {
    api.profiles().then(setProfiles).catch(() => {});
  }

  useEffect(() => { loadProfiles(); }, []);

  // Click outside to close.
  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  async function switchTo(p) {
    setBusy(true); setErr(null);
    try {
      await api.useProfile(p.id);
      const conn = await api.connection();
      onSwitch(conn);
      setOpen(false);
      loadProfiles(); // refresh last_used_at
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function makeDefault(p, e) {
    e.stopPropagation();
    try { await api.setDefaultProfile(p.id); loadProfiles(); }
    catch { /* swallow */ }
  }

  async function remove(p, e) {
    e.stopPropagation();
    if (!confirm(`Delete profile "${p.name}"?`)) return;
    try { await api.deleteProfile(p.id); loadProfiles(); }
    catch (err) { alert(err.message); }
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        className="secondary"
        onClick={() => setOpen(!open)}
        disabled={busy}
        style={{ fontSize: 13, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 6 }}
      >
        <span style={{ fontWeight: 500 }}>
          {currentConn?.profile_name || `${currentConn?.project_id || '—'}`}
        </span>
        <span className="muted" style={{ fontSize: 11 }}>
          {currentConn?.dataset_id}
        </span>
        <span style={{ fontSize: 10, marginLeft: 4 }}>▾</span>
      </button>
      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            marginTop: 4,
            background: '#fff',
            border: '1px solid #e6e6e6',
            borderRadius: 8,
            minWidth: 320,
            boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
            zIndex: 10,
            overflow: 'hidden',
          }}
        >
          {err && <div className="error" style={{ margin: 8 }}>{err}</div>}
          {profiles.length === 0 && (
            <div className="muted" style={{ padding: 12, fontSize: 13 }}>
              No saved profiles yet.
            </div>
          )}
          {profiles.map((p) => {
            const isActive = p.id === currentConn?.profile_id;
            return (
              <div
                key={p.id}
                onClick={() => !isActive && switchTo(p)}
                style={{
                  padding: '10px 12px',
                  cursor: isActive ? 'default' : 'pointer',
                  background: isActive ? '#f6f9ff' : 'transparent',
                  borderBottom: '1px solid #f0f0f0',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.background = '#fafbfc';
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.background = 'transparent';
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, display: 'flex', gap: 6, alignItems: 'center' }}>
                    {p.name}
                    {p.is_default && (
                      <span style={{ fontSize: 10, color: '#1a7d3a', background: '#e6f7ed', padding: '1px 6px', borderRadius: 8 }}>
                        default
                      </span>
                    )}
                    {isActive && (
                      <span style={{ fontSize: 10, color: '#4f7cff' }}>● active</span>
                    )}
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                    {p.project_id} / {p.dataset_id}
                  </div>
                </div>
                <button
                  className="secondary"
                  onClick={(e) => makeDefault(p, e)}
                  title="Make default (auto-loads on app start)"
                  style={{ fontSize: 10, padding: '2px 6px' }}
                  disabled={p.is_default}
                >
                  ⭐
                </button>
                <button
                  className="secondary"
                  onClick={(e) => remove(p, e)}
                  title="Delete profile"
                  style={{ fontSize: 10, padding: '2px 6px', color: '#b00' }}
                >
                  ×
                </button>
              </div>
            );
          })}
          <div
            onClick={() => { setOpen(false); onAddNew(); }}
            style={{
              padding: '10px 12px',
              cursor: 'pointer',
              fontSize: 13,
              color: '#4f7cff',
              fontWeight: 500,
              background: '#fafbfc',
            }}
          >
            + Add new connection
          </div>
        </div>
      )}
    </div>
  );
}
