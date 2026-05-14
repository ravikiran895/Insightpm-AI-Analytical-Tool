import { useEffect, useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';
import { CardHeader } from './RetentionDashboard';

function severityStyle(s) {
  if (s >= 0.7) return { className: 'insight high', icon: '🔴' };
  if (s >= 0.4) return { className: 'insight med',  icon: '🟡' };
  return { className: 'insight', icon: '🔵' };
}

const KIND_ICONS = {
  conversion: '↘',
  funnel: '⬇',
  retention: '🌱',
  volume: '📈',
};

export default function InsightsPanel({ funnelResult, funnelEvents, dateRange, cohort }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  function fetchInsights() {
    setLoading(true);
    setErr(null);
    api.insights({
      funnel_start_event: funnelEvents?.start || null,
      funnel_end_event: funnelEvents?.end || null,
      funnel_steps: funnelResult?.steps || null,
      start_date: dateRange?.start || null,
      end_date: dateRange?.end || null,
    })
      .then(setData)
      .catch(setErr)
      .finally(() => setLoading(false));
  }

  useEffect(fetchInsights, [funnelResult, funnelEvents, dateRange]); // eslint-disable-line

  return (
    <div className="card">
      <CardHeader title="Insights" />
      {loading && (
        <>
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line" style={{ width: '70%' }} />
        </>
      )}
      <ErrorBox error={err} onRetry={fetchInsights} />
      {!loading && !err && data && data.insights.length === 0 && (
        <div className="empty-state" style={{ padding: '20px 0' }}>
          <div style={{ fontSize: 28, marginBottom: 6 }}>🔍</div>
          <div style={{ fontWeight: 500 }}>No notable changes detected</div>
          <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
            That's good — or it could mean low traffic / a recent dataset. Try a wider date range.
          </div>
        </div>
      )}
      {data && data.insights.map((i) => (
        <InsightCard key={i.id} insight={i} dateRange={dateRange} cohort={cohort} />
      ))}
    </div>
  );
}

function InsightCard({ insight, dateRange, cohort }) {
  const { className, icon } = severityStyle(insight.severity);
  const kindIcon = KIND_ICONS[insight.kind] || '•';

  // Two AI features per insight: Explain (Phase 5) and Investigate (Phase 9)
  const [explanation, setExplanation] = useState(null);
  const [explainBusy, setExplainBusy] = useState(false);
  const [explainErr, setExplainErr] = useState(null);

  const [investigation, setInvestigation] = useState(null);
  const [investigateBusy, setInvestigateBusy] = useState(false);
  const [investigateErr, setInvestigateErr] = useState(null);

  async function explain() {
    setExplainBusy(true);
    setExplainErr(null);
    try {
      const r = await api.explainInsight({
        insight,
        start_date: dateRange.start,
        end_date: dateRange.end,
      });
      setExplanation(r);
    } catch (e) {
      setExplainErr(e.message);
    } finally {
      setExplainBusy(false);
    }
  }

  async function investigate() {
    setInvestigateBusy(true);
    setInvestigateErr(null);
    try {
      const r = await api.investigateInsight({
        insight,
        start_date: dateRange.start,
        end_date: dateRange.end,
        base_cohort: cohort && cohort.length > 0 ? cohort : null,
      });
      setInvestigation(r);
    } catch (e) {
      setInvestigateErr(e.message);
    } finally {
      setInvestigateBusy(false);
    }
  }

  return (
    <div className={className}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 14, lineHeight: '20px' }}>{icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="title">
            <span style={{ marginRight: 6, color: '#666' }}>{kindIcon}</span>
            {insight.title}
          </div>
          <div className="detail">{insight.detail}</div>

          {!explanation && !explainBusy && !explainErr && !investigation && !investigateBusy && (
            <div className="row" style={{ marginTop: 8, gap: 6 }}>
              <button
                className="secondary"
                onClick={explain}
                style={{ fontSize: 11, padding: '3px 10px', color: '#666' }}
                title="Generate a hypothesis using context from your data"
              >
                💡 Explain why
              </button>
              <button
                className="secondary"
                onClick={investigate}
                style={{
                  fontSize: 11, padding: '3px 10px',
                  color: '#fff',
                  background: 'linear-gradient(90deg, #4f7cff, #8a5cf0)',
                  border: 'none',
                }}
                title="Deep investigation: where it's concentrated, when it started, why it happened, and what to do"
              >
                🔍 Investigate
              </button>
            </div>
          )}

          {explainBusy && (
            <div className="muted" style={{ fontSize: 12, marginTop: 8, fontStyle: 'italic' }}>
              Thinking…
            </div>
          )}
          {explainErr && (
            <div style={{ fontSize: 12, color: '#b00', marginTop: 8 }}>{explainErr}</div>
          )}
          {explanation && (
            <div className="explanation-box">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <span className="explanation-source-tag">
                  {explanation.source === 'gemini' && '✨ Gemini'}
                  {explanation.source === 'anthropic' && '✨ Claude'}
                  {explanation.source === 'template' && 'Rule-based'}
                </span>
                <button
                  className="secondary"
                  onClick={() => setExplanation(null)}
                  style={{ fontSize: 10, padding: '1px 6px', color: '#888' }}
                  title="Dismiss"
                >×</button>
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.5, color: '#333' }}>
                {explanation.explanation}
              </div>
            </div>
          )}

          {investigateBusy && (
            <div className="muted" style={{ fontSize: 12, marginTop: 8, fontStyle: 'italic' }}>
              Investigating across multiple dimensions… this takes a few seconds.
            </div>
          )}
          {investigateErr && (
            <div style={{ fontSize: 12, color: '#b00', marginTop: 8 }}>{investigateErr}</div>
          )}
          {investigation && (
            <InvestigationView result={investigation} onClose={() => setInvestigation(null)} />
          )}
        </div>
        <span className="severity-badge" style={{
          background: insight.severity >= 0.7 ? '#fde8e8' : insight.severity >= 0.4 ? '#fff5e0' : '#e6efff',
          color: insight.severity >= 0.7 ? '#b00' : insight.severity >= 0.4 ? '#a86d11' : '#3055d8',
        }}>
          {Math.round(insight.severity * 100)}
        </span>
      </div>
    </div>
  );
}

// Renders the Where/When/Why investigation result
function InvestigationView({ result, onClose }) {
  const where = result.where || { axes: {} };
  const when = result.when || { timeline: [] };

  return (
    <div className="investigation-box">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{
          background: 'linear-gradient(90deg, #4f7cff, #8a5cf0)',
          color: '#fff', fontSize: 11, fontWeight: 600,
          padding: '3px 10px', borderRadius: 8,
        }}>
          🔍 Investigation
        </span>
        <button
          className="secondary"
          onClick={onClose}
          style={{ fontSize: 10, padding: '1px 6px', color: '#888' }}
          title="Close"
        >×</button>
      </div>

      {/* WHERE */}
      <div className="invest-section">
        <div className="invest-label">📍 WHERE</div>
        <div className="invest-axes">
          {Object.entries(where.axes || {}).map(([axis, rows]) => {
            if (!rows || rows.length === 0) return null;
            const top = rows[0];
            const concentrated = top.share >= 0.6;
            return (
              <div key={axis} className="invest-axis">
                <div className="invest-axis-label">By {axis}</div>
                {rows.slice(0, 3).map((r, i) => (
                  <div key={i} className="invest-axis-row">
                    <span className={i === 0 && concentrated ? 'invest-top-bold' : ''}>
                      {r.value}
                    </span>
                    <span className="invest-axis-bar" style={{ flex: 1 }}>
                      <span style={{
                        display: 'block',
                        height: 6, borderRadius: 3,
                        background: i === 0 && concentrated ? '#4f7cff' : '#bcd0ff',
                        width: `${(r.share * 100).toFixed(0)}%`,
                      }} />
                    </span>
                    <span className="invest-axis-pct">
                      {(r.share * 100).toFixed(0)}% ({r.users.toLocaleString()})
                    </span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>

      {/* WHEN */}
      <div className="invest-section">
        <div className="invest-label">📅 WHEN</div>
        {when.change_started_on ? (
          <div style={{ fontSize: 13 }}>
            Change appears to have begun on <strong>{when.change_started_on}</strong>.
            <Sparkline timeline={when.timeline} boundaryDate={when.analysis_period?.start} />
          </div>
        ) : (
          <div style={{ fontSize: 13 }}>
            No clear inflection point detected — the change is gradual or noisy.
            <Sparkline timeline={when.timeline} boundaryDate={when.analysis_period?.start} />
          </div>
        )}
      </div>

      {/* WHY + WHAT */}
      <div className="invest-section">
        <div className="invest-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          🧠 WHY + WHAT
          <span className="explanation-source-tag" style={{ fontSize: 9 }}>
            {result.source === 'gemini' && '✨ Gemini'}
            {result.source === 'anthropic' && '✨ Claude'}
            {result.source === 'template' && 'Rule-based'}
          </span>
        </div>
        <div className="invest-why-what">
          {renderMarkdownish(result.why_what)}
        </div>
        {result.source === 'template' && (
          <div className="muted" style={{ fontSize: 10, marginTop: 6, fontStyle: 'italic' }}>
            Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env for AI-powered hypotheses.
          </div>
        )}
      </div>
    </div>
  );
}

function Sparkline({ timeline, boundaryDate }) {
  if (!timeline || timeline.length === 0) return null;
  const w = 360, h = 50;
  const max = Math.max(...timeline.map((r) => r.target_count), 1);
  const stepX = w / Math.max(timeline.length - 1, 1);
  const points = timeline.map((r, i) => `${i * stepX},${h - (r.target_count / max) * h}`).join(' ');

  // Find boundary index
  const boundaryIdx = boundaryDate
    ? timeline.findIndex((r) => r.date.replace(/-/g, '') >= boundaryDate)
    : -1;

  return (
    <svg width={w} height={h + 10} style={{ display: 'block', marginTop: 8 }}>
      {boundaryIdx > 0 && (
        <line
          x1={boundaryIdx * stepX} x2={boundaryIdx * stepX}
          y1={0} y2={h}
          stroke="#aaa" strokeDasharray="3,3"
        />
      )}
      <polyline
        fill="none" stroke="#4f7cff" strokeWidth="2"
        points={points}
      />
      <text x={0} y={h + 9} fontSize="9" fill="#999">{timeline[0]?.date}</text>
      <text x={w - 60} y={h + 9} fontSize="9" fill="#999">{timeline[timeline.length - 1]?.date}</text>
    </svg>
  );
}

function renderMarkdownish(text) {
  if (!text) return null;
  const lines = text.split('\n');
  return lines.map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    const rendered = parts.map((p, j) => {
      if (p.startsWith('**') && p.endsWith('**')) {
        return <strong key={j}>{p.slice(2, -2)}</strong>;
      }
      return <span key={j}>{p}</span>;
    });
    return (
      <div key={i} style={{ marginTop: line.trim() ? 6 : 0, fontSize: 13, lineHeight: 1.5 }}>
        {rendered}
      </div>
    );
  });
}
