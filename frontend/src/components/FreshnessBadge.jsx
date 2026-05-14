import { useEffect, useState } from 'react';
import { api } from '../api/client';

// Tiny status indicator. Sits next to the project/dataset label in the header.
// Helps PMs trust the dashboard: if data is stale they see WHY it looks weird.
export default function FreshnessBadge() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.freshness().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;

  const colors = {
    fresh: { bg: '#e6f7ed', fg: '#1a7d3a', label: 'Fresh' },
    stale: { bg: '#fff5e0', fg: '#a86d11', label: 'Stale' },
    broken: { bg: '#fde8e8', fg: '#b00', label: 'Broken' },
    no_data: { bg: '#eee', fg: '#666', label: 'No data' },
    unknown: { bg: '#eee', fg: '#666', label: 'Unknown' },
  };
  const c = colors[data.status] || colors.unknown;

  let title = `Latest event: ${data.latest_event || 'none'}`;
  if (data.hours_old !== null && data.hours_old !== undefined) {
    title += ` (${data.hours_old}h ago)`;
  }

  return (
    <span
      title={title}
      style={{
        background: c.bg,
        color: c.fg,
        fontSize: 11,
        padding: '3px 8px',
        borderRadius: 12,
        fontWeight: 500,
      }}
    >
      {c.label}
      {data.hours_old !== null && data.hours_old !== undefined &&
        ` · ${data.hours_old}h old`}
    </span>
  );
}
