import { useState } from 'react';
import { api } from '../api/client';

const SUGGESTIONS = [
  'why is retention low',
  'what is the aha moment',
  'are we growing',
  'compare retention India vs US',
];

export default function NLQBox() {
  const [q, setQ] = useState('');
  const [a, setA] = useState(null);
  const [busy, setBusy] = useState(false);

  async function ask(question) {
    const text = (question ?? q).trim();
    if (!text) return;
    setBusy(true); setQ(text);
    try {
      setA(await api.nlq(text));
    } catch (e) {
      setA({ answer: `Error: ${e.message}`, intent: 'error', classifier: 'error' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        Ask
        {a && a.classifier === 'gemini' && (
          <span className="ai-badge" title="Question understood via Gemini">✨ Gemini</span>
        )}
        {a && a.classifier === 'anthropic' && (
          <span className="ai-badge" title="Question understood via Claude">✨ Claude</span>
        )}
        {a && a.classifier === 'keyword' && (
          <span className="ai-badge" style={{ background: '#eee', color: '#666' }}
                title="Using keyword fallback. Set GEMINI_API_KEY in .env to enable AI.">
            keyword
          </span>
        )}
      </h2>
      <div className="nlq-box">
        <input
          placeholder='Try: "compare retention India vs US" or "why is retention low"'
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask()}
        />
        <button onClick={() => ask()} disabled={busy}>{busy ? '…' : 'Ask'}</button>
      </div>      <div className="row" style={{ gap: 6, marginTop: 8 }}>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            className="secondary"
            style={{ fontSize: 12, padding: '4px 10px' }}
            onClick={() => ask(s)}
          >
            {s}
          </button>
        ))}
      </div>
      {a && (
        <div className="nlq-answer">
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            intent: {a.intent}
          </div>
          {a.answer}
        </div>
      )}
    </div>
  );
}
