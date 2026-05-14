import { useState } from 'react';
import { buildShareUrl } from '../api/url_state';

export default function ShareButton({ dateRange, cohort, savedFunnelId }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    const url = buildShareUrl({ dateRange, cohort, savedFunnelId });
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API can fail in non-https or older browsers. Fallback:
      // show a prompt the user can manually copy from.
      window.prompt('Copy this URL:', url);
    }
  }

  return (
    <button
      className="secondary"
      onClick={copy}
      style={{ fontSize: 12, padding: '4px 10px' }}
      title="Copy a URL that captures the current date range, cohort, and view"
    >
      {copied ? '✓ Copied' : '🔗 Share'}
    </button>
  );
}
