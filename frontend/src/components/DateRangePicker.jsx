import { useState } from 'react';

// Why we built our own instead of pulling a date library:
// - Bundle size: react-datepicker + date-fns is ~80KB. We need 8 lines of UI.
// - The PM mental model is "last N days" or a quick preset, not a calendar.
// - Custom dates are still supported via the two date inputs.

const PRESETS = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 14 days', days: 14 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 90 days', days: 90 },
];

function ymdFromDate(d) {
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

function isoFromYmd(ymd) {
  // "20260425" -> "2026-04-25" for <input type="date">
  return `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`;
}

function ymdFromIso(iso) {
  return iso.replace(/-/g, '');
}

export default function DateRangePicker({ value, onChange }) {
  const [showCustom, setShowCustom] = useState(false);

  function applyPreset(days) {
    const end = new Date();
    end.setDate(end.getDate() - 1); // yesterday — daily export means today is incomplete
    const start = new Date(end);
    start.setDate(start.getDate() - (days - 1));
    onChange({ start: ymdFromDate(start), end: ymdFromDate(end) });
    setShowCustom(false);
  }

  function applyCustomStart(iso) {
    onChange({ ...value, start: ymdFromIso(iso) });
  }
  function applyCustomEnd(iso) {
    onChange({ ...value, end: ymdFromIso(iso) });
  }

  return (
    <div className="row" style={{ gap: 6, alignItems: 'center' }}>
      {PRESETS.map((p) => (
        <button
          key={p.label}
          className="secondary"
          style={{ fontSize: 12, padding: '4px 10px' }}
          onClick={() => applyPreset(p.days)}
        >
          {p.label}
        </button>
      ))}
      <button
        className="secondary"
        style={{ fontSize: 12, padding: '4px 10px' }}
        onClick={() => setShowCustom(!showCustom)}
      >
        Custom
      </button>
      {showCustom && (
        <>
          <input
            type="date"
            value={isoFromYmd(value.start)}
            onChange={(e) => applyCustomStart(e.target.value)}
            style={{ fontSize: 12, padding: '4px 8px' }}
          />
          <span className="muted" style={{ fontSize: 12 }}>→</span>
          <input
            type="date"
            value={isoFromYmd(value.end)}
            onChange={(e) => applyCustomEnd(e.target.value)}
            style={{ fontSize: 12, padding: '4px 8px' }}
          />
        </>
      )}
      <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>
        {isoFromYmd(value.start)} → {isoFromYmd(value.end)}
      </span>
    </div>
  );
}
