import { useState } from 'react';
import { api, setAuthDigest } from '../api/client';

export default function LoginScreen({ onLoggedIn }) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e?.preventDefault?.();
    if (!password.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const result = await api.authCheck(password);
      if (result.digest) {
        setAuthDigest(result.digest);
      }
      onLoggedIn();
    } catch (e) {
      setErr(e.message || 'Login failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #f6f9ff, #f0f4fa)',
    }}>
      <div className="card" style={{ width: 360, padding: 28 }}>
        <h1 style={{ margin: '0 0 4px 0', fontSize: 22 }}>InsightPM</h1>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          Enter the shared password to continue.
        </p>

        <form onSubmit={submit} style={{ marginTop: 16 }}>
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            style={{ width: '100%', fontSize: 14, padding: '10px 12px', boxSizing: 'border-box' }}
          />
          {err && (
            <div style={{
              marginTop: 10, padding: '8px 10px',
              background: '#fde8e8', color: '#b00',
              borderRadius: 4, fontSize: 13,
            }}>
              {err}
            </div>
          )}
          <button
            type="submit"
            disabled={busy || !password.trim()}
            style={{ width: '100%', marginTop: 12, padding: '10px 12px', fontSize: 14 }}
          >
            {busy ? 'Checking…' : 'Sign in'}
          </button>
        </form>

        <p className="muted" style={{ marginTop: 18, fontSize: 11, lineHeight: 1.5 }}>
          The password is set in <code>.env</code> by the person running this server.
          If you forgot it, contact them or remove <code>INSIGHTPM_PASSWORD</code> from the file
          to disable auth.
        </p>
      </div>
    </div>
  );
}
