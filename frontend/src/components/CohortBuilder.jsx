import { useEffect, useState } from 'react';
import { api } from '../api/client';

const OPERATORS = [
  { value: 'equals', label: 'is' },
  { value: 'not_equals', label: 'is not' },
  { value: 'in', label: 'is one of' },
  { value: 'not_in', label: 'is none of' },
  { value: 'contains', label: 'contains' },
  { value: 'starts_with', label: 'starts with' },
];

function emptyFilter() {
  return { field: '', field_type: 'column', operator: 'equals', valuesText: '' };
}

function toApiFilters(uiFilters) {
  return uiFilters
    .filter((f) => f.field && f.valuesText.trim())
    .map((f) => ({
      field: f.field,
      field_type: f.field_type,
      operator: f.operator,
      values: ['in', 'not_in'].includes(f.operator)
        ? f.valuesText.split(',').map((v) => v.trim()).filter(Boolean)
        : [f.valuesText.trim()],
    }));
}

// Convert API filter shape back to UI shape (used when loading a saved cohort).
function fromApiFilters(apiFilters) {
  return apiFilters.map((f) => ({
    field: f.field,
    field_type: f.field_type,
    operator: f.operator,
    valuesText: ['in', 'not_in'].includes(f.operator)
      ? f.values.join(', ')
      : (f.values[0] || ''),
  }));
}

export default function CohortBuilder({ dateRange, value, onChange }) {
  const [fields, setFields] = useState({ columns: [], user_properties: [], event_params: [] });
  const [draftFilters, setDraftFilters] = useState([]);
  const [expanded, setExpanded] = useState(false);

  // Saved cohorts
  const [saved, setSaved] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [currentCohortId, setCurrentCohortId] = useState(null);
  const [saveErr, setSaveErr] = useState(null);

  function loadSaved() {
    api.savedCohorts().then(setSaved).catch(() => setSaved([]));
  }
  useEffect(loadSaved, []);

  useEffect(() => {
    api.cohortFields(dateRange.start, dateRange.end)
      .then(setFields)
      .catch(() => {});
  }, [dateRange]);

  // Sync from external value (when parent changes the cohort, e.g. via URL state)
  useEffect(() => {
    if (!value || value.length === 0) {
      setDraftFilters([]);
      setCurrentCohortId(null);
    } else {
      setDraftFilters(fromApiFilters(value));
    }
  }, [value]);

  function addRow() {
    setDraftFilters([...draftFilters, emptyFilter()]);
    setExpanded(true);
  }

  function updateRow(idx, patch) {
    const next = [...draftFilters];
    next[idx] = { ...next[idx], ...patch };
    setDraftFilters(next);
  }

  function removeRow(idx) {
    const next = draftFilters.filter((_, i) => i !== idx);
    setDraftFilters(next);
    if (next.length === 0) {
      onChange([]);
      setCurrentCohortId(null);
    }
  }

  function apply() {
    onChange(toApiFilters(draftFilters));
  }

  function clearAll() {
    setDraftFilters([]);
    setCurrentCohortId(null);
    onChange([]);
  }

  function pickField(idx, fieldStr) {
    if (!fieldStr) {
      updateRow(idx, { field: '', field_type: 'column' });
      return;
    }
    const [field_type, ...rest] = fieldStr.split(':');
    const field = rest.join(':');
    updateRow(idx, { field, field_type });
  }

  // Saved cohort actions
  function loadCohort(c) {
    setDraftFilters(fromApiFilters(c.filters));
    setCurrentCohortId(c.id);
    setSaveName(c.name);
    setPickerOpen(false);
    setExpanded(true);
    onChange(c.filters); // immediately apply
  }

  async function saveCohort() {
    const apiFilters = toApiFilters(draftFilters);
    if (!saveName.trim() || apiFilters.length === 0) return;
    setSaveErr(null);
    try {
      if (currentCohortId) {
        const updated = await api.updateSavedCohort(currentCohortId, {
          name: saveName, filters: apiFilters,
        });
        setCurrentCohortId(updated.id);
      } else {
        const created = await api.createSavedCohort({
          name: saveName, filters: apiFilters,
        });
        setCurrentCohortId(created.id);
      }
      setSaveDialogOpen(false);
      loadSaved();
    } catch (e) {
      setSaveErr(e.message);
    }
  }

  async function deleteSaved(c, e) {
    e.stopPropagation();
    if (!confirm(`Delete saved cohort "${c.name}"?`)) return;
    try { await api.deleteSavedCohort(c.id); loadSaved(); }
    catch (err) { alert(err.message); }
  }

  const activeCount = (value || []).length;
  const hasUnsaved = JSON.stringify(toApiFilters(draftFilters)) !== JSON.stringify(value || []);
  const canSave = toApiFilters(draftFilters).length > 0;

  return (
    <div className="cohort-builder">
      <div className="row" style={{ alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 500 }}>Cohort filter:</span>
        {activeCount === 0 && draftFilters.length === 0 && (
          <span className="muted" style={{ fontSize: 13 }}>All users</span>
        )}
        {(value || []).map((f, i) => (
          <span key={i} className="cohort-chip">
            {f.field} {OPERATORS.find((o) => o.value === f.operator)?.label || f.operator}{' '}
            {f.values.length > 1 ? `[${f.values.length}]` : f.values[0]}
          </span>
        ))}

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, position: 'relative' }}>
          <button
            className="secondary"
            onClick={() => { setPickerOpen(!pickerOpen); }}
            style={{ fontSize: 12, padding: '4px 10px' }}
          >
            📂 Saved ({saved.length}) ▾
          </button>
          {pickerOpen && (
            <div className="saved-picker">
              {saved.length === 0 && (
                <div className="muted" style={{ padding: 12, fontSize: 13 }}>
                  No saved cohorts yet. Build one and click Save.
                </div>
              )}
              {saved.map((c) => (
                <div
                  key={c.id}
                  onClick={() => loadCohort(c)}
                  className="saved-row"
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{c.name}</div>
                    <div className="muted" style={{ fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {c.filters.length} filter{c.filters.length !== 1 ? 's' : ''}
                    </div>
                  </div>
                  <button
                    className="secondary"
                    onClick={(e) => deleteSaved(c, e)}
                    style={{ fontSize: 11, padding: '2px 6px', color: '#b00' }}
                  >×</button>
                </div>
              ))}
            </div>
          )}
          <button
            className="secondary"
            onClick={() => setExpanded(!expanded)}
            style={{ fontSize: 12, padding: '4px 10px' }}
          >
            {expanded ? 'Hide' : (activeCount > 0 ? 'Edit' : 'Add filter')}
          </button>
          {(activeCount > 0 || draftFilters.length > 0) && (
            <button
              className="secondary"
              onClick={clearAll}
              style={{ fontSize: 12, padding: '4px 10px' }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: 12 }}>
          {draftFilters.length === 0 && (
            <p className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
              Filters narrow every chart on this page. Pick a field, an operator, and a value.
            </p>
          )}
          {draftFilters.map((f, i) => (
            <div key={i} className="cohort-filter-row">
              <select
                value={f.field ? `${f.field_type}:${f.field}` : ''}
                onChange={(e) => pickField(i, e.target.value)}
                style={{ flex: 1, fontSize: 13 }}
              >
                <option value="">— pick a field —</option>
                {fields.columns.length > 0 && (
                  <optgroup label="Standard fields">
                    {fields.columns.map((c) => (
                      <option key={c.field} value={`${c.field_type}:${c.field}`}>
                        {c.label || c.field}
                      </option>
                    ))}
                  </optgroup>
                )}
                {fields.user_properties.length > 0 && (
                  <optgroup label="User properties">
                    {fields.user_properties.map((c) => (
                      <option key={c.field} value={`${c.field_type}:${c.field}`}>
                        {c.field}
                      </option>
                    ))}
                  </optgroup>
                )}
                {fields.event_params.length > 0 && (
                  <optgroup label="Event params">
                    {fields.event_params.map((c) => (
                      <option key={c.field} value={`${c.field_type}:${c.field}`}>
                        {c.field}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>

              <select
                value={f.operator}
                onChange={(e) => updateRow(i, { operator: e.target.value })}
                style={{ fontSize: 13, width: 110 }}
              >
                {OPERATORS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>

              <input
                placeholder={['in', 'not_in'].includes(f.operator) ? 'value1, value2, ...' : 'value'}
                value={f.valuesText}
                onChange={(e) => updateRow(i, { valuesText: e.target.value })}
                style={{ flex: 1, fontSize: 13 }}
              />

              <button
                className="secondary"
                onClick={() => removeRow(i)}
                style={{ fontSize: 13, padding: '4px 8px' }}
              >
                ×
              </button>
            </div>
          ))}
          <div className="row" style={{ marginTop: 8, gap: 6 }}>
            <button className="secondary" onClick={addRow} style={{ fontSize: 12 }}>
              + Add another filter
            </button>
            {draftFilters.length > 0 && (
              <>
                <button
                  onClick={apply}
                  disabled={!hasUnsaved}
                  style={{ fontSize: 12 }}
                >
                  {hasUnsaved ? 'Apply' : 'Applied'}
                </button>
                <button
                  className="secondary"
                  onClick={() => { setSaveDialogOpen(true); setSaveErr(null); }}
                  disabled={!canSave}
                  style={{ fontSize: 12 }}
                  title={canSave ? 'Save this cohort for reuse' : 'Add a filter first'}
                >
                  💾 {currentCohortId ? 'Update' : 'Save'}
                </button>
              </>
            )}
          </div>

          {saveDialogOpen && (
            <div style={{
              background: '#f6f9ff', border: '1px solid #d8e3ff',
              borderRadius: 6, padding: 10, marginTop: 8,
              display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
            }}>
              <input
                placeholder="Name this cohort (e.g. 'India Android Power Users')"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && saveCohort()}
                style={{ flex: 1, minWidth: 200, fontSize: 13 }}
                autoFocus
              />
              <button onClick={saveCohort} disabled={!saveName.trim()} style={{ fontSize: 12 }}>
                {currentCohortId ? 'Update' : 'Save'}
              </button>
              <button className="secondary" onClick={() => setSaveDialogOpen(false)} style={{ fontSize: 12 }}>
                Cancel
              </button>
              {saveErr && (
                <div style={{ width: '100%', color: '#b00', fontSize: 12 }}>{saveErr}</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
