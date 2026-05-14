import { useEffect, useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';
import { CardHeader } from './RetentionDashboard';
import SqlPreviewModal from './SqlPreviewModal';

// Color palette for breakdown series.
const SERIES_COLORS = ['#4f7cff', '#e6a23c', '#1a7d3a', '#d94f4f', '#8a5cf0', '#0ea5b8', '#f06292'];

export default function FunnelBuilder({ dateRange, cohort, fields, onResult, onEventsChange }) {
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [steps, setSteps] = useState([]);
  const [windowDays, setWindowDays] = useState(7);
  const [result, setResult] = useState(null);
  const [breakdownResult, setBreakdownResult] = useState(null);
  const [breakdownField, setBreakdownField] = useState('');
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showSql, setShowSql] = useState(false);

  // Saved funnel state
  const [saved, setSaved] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [currentFunnelId, setCurrentFunnelId] = useState(null);

  function loadSaved() {
    api.savedFunnels().then(setSaved).catch(() => setSaved([]));
  }
  useEffect(loadSaved, []);

  async function suggest() {
    setErr(null); setBusy(true);
    try {
      const { steps: suggested } = await api.funnelSuggest({
        start_event: start, end_event: end,
        start_date: dateRange.start, end_date: dateRange.end,
      });
      setSteps(suggested);
      onEventsChange({ start, end });
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  async function compute() {
    setErr(null); setBusy(true);
    setBreakdownResult(null); // computing main funnel clears breakdown view
    try {
      const stepList = steps.length > 0 ? steps : [start, end];
      const r = await api.funnel({
        steps: stepList,
        start_date: dateRange.start, end_date: dateRange.end,
        window_days: windowDays,
        cohort: cohort && cohort.length > 0 ? cohort : null,
      });
      setResult(r);
      onResult(r);
      onEventsChange({ start, end });
      setSteps(stepList);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  async function runBreakdown() {
    if (!breakdownField || steps.length < 2) return;
    setErr(null); setBusy(true);
    try {
      const [field_type, ...rest] = breakdownField.split(':');
      const field = rest.join(':');
      const r = await api.funnelBreakdown({
        steps,
        start_date: dateRange.start,
        end_date: dateRange.end,
        window_days: windowDays,
        breakdown_field: field,
        field_type: field_type,
        base_cohort: cohort && cohort.length > 0 ? cohort : null,
        top_n: 5,
      });
      setBreakdownResult(r);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  async function saveFunnel() {
    if (!saveName.trim() || steps.length < 2) return;
    setBusy(true); setErr(null);
    try {
      const config = {
        steps,
        window_days: windowDays,
        cohort: cohort && cohort.length > 0 ? cohort : null,
        default_start_date: null,
        default_end_date: null,
      };
      if (currentFunnelId) {
        await api.updateSavedFunnel(currentFunnelId, { name: saveName, config });
      } else {
        const created = await api.createSavedFunnel({ name: saveName, config });
        setCurrentFunnelId(created.id);
      }
      setSaveDialogOpen(false);
      setSaveName('');
      loadSaved();
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  function loadFunnel(f) {
    setSteps(f.config.steps);
    setStart(f.config.steps[0]);
    setEnd(f.config.steps[f.config.steps.length - 1]);
    setWindowDays(f.config.window_days || 7);
    setCurrentFunnelId(f.id);
    setSaveName(f.name);
    setPickerOpen(false);
    setResult(null);
    setBreakdownResult(null);
    onEventsChange({ start: f.config.steps[0], end: f.config.steps[f.config.steps.length - 1] });
  }

  async function deleteSaved(f, e) {
    e.stopPropagation();
    if (!confirm(`Delete saved funnel "${f.name}"?`)) return;
    try { await api.deleteSavedFunnel(f.id); loadSaved(); }
    catch (err) { alert(err.message); }
  }

  function newFunnel() {
    setSteps([]); setStart(''); setEnd('');
    setResult(null); setBreakdownResult(null);
    setCurrentFunnelId(null); setSaveName('');
    setPickerOpen(false);
  }

  function removeStep(idx) {
    if (steps.length <= 2) return;
    setSteps(steps.filter((_, i) => i !== idx));
  }

  const max = result?.steps?.[0]?.users || 1;
  const stepListForSql = steps.length > 0 ? steps : (start && end ? [start, end] : null);

  // Compose breakdown field options from the cohort fields list.
  const breakdownFieldOptions = fields
    ? [...fields.columns, ...fields.user_properties.slice(0, 10)]
    : [];

  return (
    <div className="card">
      <CardHeader
        title={currentFunnelId ? `Funnel · ${saveName}` : 'Funnel'}
        cohortCount={cohort?.length || 0}
        onViewSql={result && stepListForSql ? () => setShowSql(true) : null}
      />
      {showSql && stepListForSql && (
        <SqlPreviewModal
          kind="funnel"
          request={{
            start_date: dateRange.start, end_date: dateRange.end,
            funnel_steps: stepListForSql, window_days: windowDays,
          }}
          onClose={() => setShowSql(false)}
        />
      )}

      {/* Saved funnel toolbar */}
      <div className="row" style={{ marginBottom: 8, gap: 6 }}>
        <div style={{ position: 'relative' }}>
          <button
            className="secondary"
            onClick={() => setPickerOpen(!pickerOpen)}
            style={{ fontSize: 12 }}
          >
            📂 Saved ({saved.length}) ▾
          </button>
          {pickerOpen && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, marginTop: 4,
              background: '#fff', border: '1px solid #e6e6e6', borderRadius: 6,
              minWidth: 280, boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
              zIndex: 5, maxHeight: 300, overflow: 'auto',
            }}>
              {saved.length === 0 && (
                <div className="muted" style={{ padding: 12, fontSize: 13 }}>
                  No saved funnels yet. Build one and click Save.
                </div>
              )}
              {saved.map((f) => (
                <div
                  key={f.id}
                  onClick={() => loadFunnel(f)}
                  style={{
                    padding: '8px 12px', cursor: 'pointer',
                    borderBottom: '1px solid #f0f0f0',
                    display: 'flex', justifyContent: 'space-between', gap: 8,
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#fafbfc'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{f.name}</div>
                    <div className="muted" style={{ fontSize: 11, fontFamily: 'ui-monospace, SFMono-Regular, monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {f.config.steps.join(' → ')}
                    </div>
                  </div>
                  <button
                    className="secondary"
                    onClick={(e) => deleteSaved(f, e)}
                    style={{ fontSize: 11, padding: '2px 6px', color: '#b00' }}
                  >×</button>
                </div>
              ))}
            </div>
          )}
        </div>
        <button
          className="secondary"
          onClick={() => { setSaveName(saveName || ''); setSaveDialogOpen(true); }}
          disabled={steps.length < 2}
          style={{ fontSize: 12 }}
        >
          {currentFunnelId ? '💾 Update' : '💾 Save'}
        </button>
        {currentFunnelId && (
          <button className="secondary" onClick={newFunnel} style={{ fontSize: 12 }}>
            + New
          </button>
        )}
      </div>

      {saveDialogOpen && (
        <div style={{
          background: '#f6f9ff', border: '1px solid #d8e3ff',
          borderRadius: 6, padding: 10, marginBottom: 12,
          display: 'flex', gap: 8, alignItems: 'center',
        }}>
          <input
            placeholder="Name this funnel (e.g. 'Onboarding')"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && saveFunnel()}
            style={{ flex: 1, fontSize: 13 }}
            autoFocus
          />
          <button onClick={saveFunnel} disabled={busy || !saveName.trim()} style={{ fontSize: 12 }}>
            {currentFunnelId ? 'Update' : 'Save'}
          </button>
          <button className="secondary" onClick={() => setSaveDialogOpen(false)} style={{ fontSize: 12 }}>
            Cancel
          </button>
        </div>
      )}

      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder="start event (e.g. session_start)" value={start}
               onChange={(e) => setStart(e.target.value)}
               style={{ flex: 1, fontFamily: 'ui-monospace, SFMono-Regular, monospace' }} />
        <input placeholder="end event (e.g. purchase)" value={end}
               onChange={(e) => setEnd(e.target.value)}
               style={{ flex: 1, fontFamily: 'ui-monospace, SFMono-Regular, monospace' }} />
        <label className="muted" style={{ fontSize: 12 }} title="Conversion window: max time from step 1 to step N">
          Window
          <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}
                  style={{ fontSize: 12, padding: '4px 6px', marginLeft: 4 }}>
            <option value={1}>1 day</option>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
          </select>
        </label>
        <button className="secondary" onClick={suggest} disabled={busy || !start || !end}>
          Suggest steps
        </button>
        <button onClick={compute} disabled={busy || !start || !end}>
          {busy ? 'Running…' : 'Compute'}
        </button>
      </div>

      {steps.length > 0 && (
        <div className="step-chips">
          {steps.map((s, i) => (
            <span key={i} className="step-chip">
              <span className="step-chip-num">{i + 1}</span>
              {s}
              {steps.length > 2 && (
                <button className="step-chip-close" onClick={() => removeStep(i)} title="Remove step">×</button>
              )}
            </span>
          ))}
        </div>
      )}

      <ErrorBox error={err} onRetry={steps.length > 0 ? compute : undefined} />

      {busy && (<><div className="skeleton-line" /><div className="skeleton-line" /><div className="skeleton-line" /></>)}

      {/* Breakdown control bar — visible only when a funnel is computed */}
      {!busy && result && result.steps.length > 0 && (
        <div className="row" style={{
          marginTop: 12, padding: '8px 10px',
          background: '#fafbfc', borderRadius: 6, border: '1px solid #eee',
          gap: 8, alignItems: 'center',
        }}>
          <span style={{ fontSize: 12, color: '#666' }}>Break down by:</span>
          <select
            value={breakdownField}
            onChange={(e) => setBreakdownField(e.target.value)}
            style={{ fontSize: 12, padding: '4px 6px', flex: 1, maxWidth: 240 }}
          >
            <option value="">— pick a field —</option>
            {breakdownFieldOptions.map((c) => (
              <option key={c.field} value={`${c.field_type}:${c.field}`}>
                {c.label || c.field}
              </option>
            ))}
          </select>
          <button
            onClick={runBreakdown}
            disabled={busy || !breakdownField}
            style={{ fontSize: 12 }}
          >
            Compare
          </button>
          {breakdownResult && (
            <button
              className="secondary"
              onClick={() => setBreakdownResult(null)}
              style={{ fontSize: 12 }}
            >
              ← Show single
            </button>
          )}
        </div>
      )}

      {/* Single funnel rendering */}
      {!busy && result && !breakdownResult && result.steps.length > 0 && (
        <div className="funnel-viz">
          {result.steps.map((s, i) => {
            const widthPct = (s.users / max) * 100;
            const dropPct = s.drop_off_from_prev_pct;
            return (
              <div key={i} className="funnel-row">
                <div className="funnel-step-num">{i + 1}</div>
                <div className="funnel-step-name">{s.event}</div>
                <div className="funnel-step-bar">
                  <div className="funnel-step-fill" style={{ width: `${widthPct}%` }}>
                    <span className="funnel-step-pct">
                      {(s.conversion_from_start_pct * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div className="funnel-step-stats">
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{s.users.toLocaleString()}</div>
                  {dropPct !== null && dropPct > 0 && (
                    <div style={{ fontSize: 11, color: dropPct > 0.3 ? '#d94f4f' : '#999' }}>
                      −{(dropPct * 100).toFixed(1)}% from prev
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Breakdown rendering: side-by-side conversion rates per series */}
      {!busy && breakdownResult && breakdownResult.series.length > 0 && (
        <BreakdownTable result={breakdownResult} />
      )}
      {!busy && breakdownResult && breakdownResult.series.length === 0 && (
        <p className="muted">No values found for this breakdown field in the selected range.</p>
      )}

      {!busy && !result && !err && (
        <p className="muted">
          Enter a start and end event, then either compute the 2-step funnel
          directly or click "Suggest steps" to auto-fill the most common events
          users hit between the two.
        </p>
      )}
    </div>
  );
}

function BreakdownTable({ result }) {
  // Each series has the same step list. Build a matrix: rows = steps, cols = series.
  const series = result.series;
  const stepCount = series[0]?.steps.length || 0;

  return (
    <div style={{ marginTop: 12, overflowX: 'auto' }}>
      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
        Splitting by <code style={{ background: '#fff5e0', padding: '1px 4px', borderRadius: 3 }}>
          {result.breakdown_field}
        </code> · top {series.length} values
      </div>
      <table className="breakdown-table">
        <thead>
          <tr>
            <th>Step</th>
            {series.map((s, i) => (
              <th key={i} style={{ color: SERIES_COLORS[i % SERIES_COLORS.length] }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 10, height: 10, background: SERIES_COLORS[i % SERIES_COLORS.length], borderRadius: 2 }} />
                  {s.series_label}
                </div>
                <div className="muted" style={{ fontSize: 10, fontWeight: 400 }}>
                  {s.series_users.toLocaleString()} users
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: stepCount }).map((_, stepIdx) => (
            <tr key={stepIdx}>
              <td style={{
                fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                fontSize: 12, fontWeight: 500,
              }}>
                {stepIdx + 1}. {series[0].steps[stepIdx].event}
              </td>
              {series.map((s, seriesIdx) => {
                const step = s.steps[stepIdx];
                const conv = step.conversion_from_start_pct;
                const color = SERIES_COLORS[seriesIdx % SERIES_COLORS.length];
                return (
                  <td key={seriesIdx} style={{ minWidth: 100 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ flex: 1, height: 6, background: '#eef0f5', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', width: `${conv * 100}%`,
                          background: color, opacity: 0.8,
                        }} />
                      </div>
                      <span style={{ fontSize: 11, minWidth: 50, textAlign: 'right' }}>
                        <strong>{step.users.toLocaleString()}</strong>
                        <span className="muted" style={{ marginLeft: 4 }}>
                          ({(conv * 100).toFixed(1)}%)
                        </span>
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
