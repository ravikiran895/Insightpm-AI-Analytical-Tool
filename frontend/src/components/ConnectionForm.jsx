import { useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';

// Connect to BigQuery, optionally save as a named profile.
// Mode 1: First-time setup (full screen, shown when no connection exists)
// Mode 2: Add new connection (modal-ish, shown from the ProfileSwitcher dropdown)
export default function ConnectionForm({ onConnected, onCancel, embedded = false }) {
  const [project, setProject] = useState('');
  const [dataset, setDataset] = useState('');
  const [saJson, setSaJson] = useState('');
  const [saveAs, setSaveAs] = useState('');
  const [setDefault, setSetDefault] = useState(true);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      let parsed = null;
      if (saJson.trim()) {
        try { parsed = JSON.parse(saJson); }
        catch { throw new Error('Service account JSON is not valid JSON.'); }
      }
      await api.connect({
        project_id: project,
        dataset_id: dataset,
        service_account_json: parsed,
        save_as: saveAs.trim() || null,
        set_default: setDefault,
      });
      const c = await api.connection();
      onConnected(c);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={embedded ? { boxShadow: '0 4px 16px rgba(0,0,0,0.1)' } : {}}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>{embedded ? 'Add connection' : 'Connect to BigQuery'}</h2>
        {embedded && onCancel && (
          <button className="secondary" style={{ fontSize: 12 }} onClick={onCancel}>Cancel</button>
        )}
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Point InsightPM at your GA4 / Firebase Analytics export dataset. Service account
        JSON is held in memory on the backend and (if you save) in a local SQLite file on
        your machine — never sent anywhere else.
      </p>
      <ErrorBox error={err} />

      <div className="row" style={{ marginBottom: 8 }}>
        <input
          placeholder="GCP project_id (e.g. my-project)"
          value={project}
          onChange={(e) => setProject(e.target.value)}
          style={{ flex: 1 }}
        />
        <input
          placeholder="dataset_id (e.g. analytics_123456789)"
          value={dataset}
          onChange={(e) => setDataset(e.target.value)}
          style={{ flex: 1 }}
        />
      </div>
      <textarea
        placeholder="Service account JSON. Paste the contents of the .json key file you downloaded from GCP IAM."
        value={saJson}
        onChange={(e) => setSaJson(e.target.value)}
        style={{
          width: '100%', minHeight: 110,
          fontFamily: 'ui-monospace, SFMono-Regular, monospace',
          fontSize: 12, padding: 8, marginBottom: 8,
        }}
      />

      <div style={{
        background: '#f6f9ff',
        border: '1px solid #d8e3ff',
        borderRadius: 6,
        padding: 12,
        marginBottom: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input
            type="text"
            placeholder='Save as profile (e.g. "Production"). Leave empty to skip saving.'
            value={saveAs}
            onChange={(e) => setSaveAs(e.target.value)}
            style={{ flex: 1, fontSize: 13 }}
          />
        </div>
        {saveAs.trim() && (
          <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={setDefault}
              onChange={(e) => setSetDefault(e.target.checked)}
            />
            Make this the default (auto-load when the app starts)
          </label>
        )}
      </div>

      <button onClick={submit} disabled={busy || !project || !dataset}>
        {busy ? 'Connecting…' : saveAs.trim() ? 'Connect & save' : 'Connect'}
      </button>
    </div>
  );
}
