import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import ErrorBox from './ErrorBox';
import LoadingOverlay from './LoadingOverlay';
import { CardHeader } from './RetentionDashboard';

function severityStyle(s) {
  if (s >= 0.7) return { className: 'insight high', icon: '🔴', tone: 'high' };
  if (s >= 0.4) return { className: 'insight med',  icon: '🟡', tone: 'med' };
  return { className: 'insight', icon: '🔵', tone: 'low' };
}

const KIND_ICONS = {
  conversion: '↘',
  funnel: '⬇',
  retention: '🌱',
  volume: '📈',
};

const KIND_LABELS = {
  conversion: 'Conversion change',
  funnel: 'Funnel drop-off',
  retention: 'Retention correlation',
  volume: 'Volume change',
};

export default function InsightsPanel({ funnelResult, funnelEvents, dateRange, cohort }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  // Panel-level state for the loading overlay. Hoisted from InsightCard so that
  // periodic re-fetches (which can re-mount the cards) don't unmount the overlay
  // and cause it to blink. Each card hands its insight id + cancel callback up
  // when it starts an investigation; the panel renders ONE overlay total.
  const [activeInvestigation, setActiveInvestigation] = useState(null);
  // shape: { insightId, onCancel } | null

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

  // Only show the loading skeleton on the very first fetch (when there's no
  // data yet). Background re-fetches that arrive while data exists stay silent —
  // showing skeleton lines while a user is mid-investigation made the panel
  // grow/shrink under the overlay, which read as "blinking" through the blur.
  const showSkeleton = loading && !data;

  return (
    <InvestigationOverlayContext.Provider value={{ activeInvestigation, setActiveInvestigation }}>
      <div className="card">
        <CardHeader title="Insights" />
        {showSkeleton && (
          <>
            <div className="skeleton-line" />
            <div className="skeleton-line" />
            <div className="skeleton-line" style={{ width: '70%' }} />
          </>
        )}
        <ErrorBox error={err} onRetry={fetchInsights} />
        {!showSkeleton && !err && data && data.insights.length === 0 && (
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

      {/* Panel-level overlay — one instance, controlled by whichever card is active.
          Lives OUTSIDE InsightCard so card remounts during re-fetch don't blink it. */}
      <LoadingOverlay
        busy={!!activeInvestigation}
        title="Investigating across multiple dimensions"
        desc="Running BigQuery queries in parallel, then asking AI to synthesize the hypothesis."
        steps={[
          { name: 'Where queries (country, platform, version, device)', duration: 700 },
          { name: 'When timeline (daily breakdown)', duration: 600 },
          { name: 'Adjacent movers analysis', duration: 700 },
          { name: 'AI synthesis (hypothesis + actions)', duration: 1300 },
        ]}
        onCancel={() => {
          if (activeInvestigation?.onCancel) activeInvestigation.onCancel();
          setActiveInvestigation(null);
        }}
      />
    </InvestigationOverlayContext.Provider>
  );
}

// Context lets each InsightCard report its busy state UP to the panel
// without prop-drilling through every level.
const InvestigationOverlayContext = createContext({
  activeInvestigation: null,
  setActiveInvestigation: () => {},
});

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

  // Pull the panel-level overlay controller so we can register this card's
  // busy state at the panel. The overlay itself is rendered by InsightsPanel,
  // not by InsightCard — that way periodic re-fetches that re-mount cards
  // don't blink the overlay.
  const { setActiveInvestigation } = useContext(InvestigationOverlayContext);

  // Abort flag for investigate — if user cancels while the API is in flight,
  // any late-arriving result is discarded so the overlay closing doesn't
  // suddenly reveal results from a cancelled request.
  const investigateAbortRef = useRef({ aborted: false });

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
    // Reset abort flag for this fresh request
    investigateAbortRef.current = { aborted: false };
    const abortToken = investigateAbortRef.current;
    setInvestigateBusy(true);
    setInvestigateErr(null);
    // Register at the panel level so the panel's single overlay shows.
    // Hand up our cancel callback so X/Escape/backdrop dismiss this request.
    setActiveInvestigation({
      insightId: insight.id,
      onCancel: cancelInvestigation,
    });
    try {
      const r = await api.investigateInsight({
        insight,
        start_date: dateRange.start,
        end_date: dateRange.end,
        base_cohort: cohort && cohort.length > 0 ? cohort : null,
      });
      // Only apply the result if this specific request wasn't cancelled
      if (!abortToken.aborted) {
        setInvestigation(r);
      }
    } catch (e) {
      if (!abortToken.aborted) {
        setInvestigateErr(e.message);
      }
    } finally {
      if (!abortToken.aborted) {
        setInvestigateBusy(false);
      }
      // Always clear the panel-level overlay when this request settles,
      // regardless of cancel state — the overlay should not persist past
      // the API call returning.
      setActiveInvestigation(null);
    }
  }

  function cancelInvestigation() {
    // Mark the in-flight request as aborted (its result will be discarded
    // if it eventually arrives) and immediately hide the overlay.
    investigateAbortRef.current.aborted = true;
    setInvestigateBusy(false);
    setActiveInvestigation(null);
  }

  return (
    <div className={className}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 14, lineHeight: '20px' }}>{icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="title">
            <span style={{ marginRight: 6, color: 'var(--text-3)' }}>{kindIcon}</span>
            {insight.title}
          </div>
          <div className="detail">{insight.detail}</div>

          {!explanation && !explainBusy && !explainErr && !investigation && !investigateBusy && (
            <div className="row" style={{ marginTop: 8, gap: 6 }}>
              <button
                className="secondary"
                onClick={explain}
                style={{ fontSize: 11, padding: '4px 10px' }}
                title="Generate a hypothesis using context from your data"
              >
                💡 Explain why
              </button>
              <button
                className="btn-investigate"
                onClick={investigate}
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
            <div style={{ fontSize: 12, color: 'var(--danger-text)', marginTop: 8 }}>{explainErr}</div>
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
                  style={{ fontSize: 10, padding: '1px 6px' }}
                  title="Dismiss"
                >×</button>
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--text)' }}>
                {explanation.explanation}
              </div>
            </div>
          )}

          {investigateErr && (
            <div style={{ fontSize: 12, color: 'var(--danger-text)', marginTop: 8 }}>{investigateErr}</div>
          )}
          {investigation && (
            <InvestigationView
              result={investigation}
              insight={insight}
              onClose={() => setInvestigation(null)}
            />
          )}
        </div>
        <span className="severity-badge" style={{
          background: insight.severity >= 0.7 ? 'var(--danger-soft)' : insight.severity >= 0.4 ? 'var(--amber-soft)' : 'var(--blue-soft)',
          color: insight.severity >= 0.7 ? 'var(--danger-text)' : insight.severity >= 0.4 ? 'var(--amber-text)' : 'var(--navy)',
        }}>
          {Math.round(insight.severity * 100)}
        </span>
      </div>
    </div>
  );
}

// Renders the Where/When/Why investigation result
function InvestigationView({ result, insight, onClose }) {
  const where = result.where || { axes: {} };
  const when = result.when || { timeline: [] };
  const totalAffected = where.total_affected_users;
  const kindLabel = KIND_LABELS[insight?.kind] || 'Investigation';

  // Parse why_what into Hypothesis + Actions when the LLM follows the structure.
  // Falls back to flat rendering if it doesn't.
  const parsed = parseWhyWhat(result.why_what);

  return (
    <div className="investigation-box-v2">
      {/* Hero strip — title, severity, kind, close button */}
      <div className="invest-hero">
        <div className="row" style={{ gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
          <span className="invest-hero-badge">🔍 Investigation</span>
          <span className="invest-hero-severity" style={{
            background: insight?.severity >= 0.7 ? 'var(--danger-soft)' : insight?.severity >= 0.4 ? 'var(--amber-soft)' : 'var(--blue-soft)',
            color: insight?.severity >= 0.7 ? 'var(--danger-text)' : insight?.severity >= 0.4 ? 'var(--amber-text)' : 'var(--navy)',
          }}>
            Severity {Math.round((insight?.severity || 0) * 100)}
          </span>
          <span className="invest-hero-kind">{kindLabel}</span>
          <button
            className="secondary"
            onClick={onClose}
            style={{ marginLeft: 'auto', fontSize: 10, padding: '1px 6px' }}
            title="Close"
          >×</button>
        </div>
        <div className="invest-hero-title">{insight?.title}</div>
        {totalAffected !== undefined && (
          <div className="invest-hero-sub">
            Across {totalAffected.toLocaleString()} affected users in the cohort
          </div>
        )}
      </div>

      {/* WHERE + WHEN side-by-side on wide screens */}
      <div className="invest-grid">
        <div className="invest-panel">
          <div className="invest-panel-head">
            <span className="invest-panel-title">📍 Where</span>
            <span className="invest-panel-sub">Concentration by dimension</span>
          </div>
          <div className="invest-panel-body">
            {Object.entries(where.axes || {}).map(([axis, rows]) => {
              if (!rows || rows.length === 0) return null;
              const top = rows[0];
              const concentrated = top && top.share >= 0.6;
              return (
                <div key={axis} className="where-axis-v2">
                  <div className="where-axis-label-v2">{axis}</div>
                  {rows.slice(0, 4).map((r, i) => {
                    const isTop = i === 0 && concentrated;
                    return (
                      <div key={i} className={`where-row-v2 ${isTop ? 'top' : ''}`}>
                        <span className="where-name-v2">{r.value}</span>
                        <span className="where-bar-v2">
                          <span
                            className="where-fill-v2"
                            style={{ width: `${(r.share * 100).toFixed(0)}%` }}
                          />
                        </span>
                        <span className="where-val-v2">
                          {(r.share * 100).toFixed(0)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        <div className="invest-panel">
          <div className="invest-panel-head">
            <span className="invest-panel-title">📅 When</span>
            <span className="invest-panel-sub">
              {when.change_started_on
                ? `Inflection · ${when.change_started_on}`
                : 'Gradual or noisy'}
            </span>
          </div>
          <div className="invest-panel-body">
            <SparklineV2
              timeline={when.timeline}
              boundaryDate={when.analysis_period?.start}
              changeDate={when.change_started_on}
            />
            <div className="invest-when-caption">
              {when.change_started_on
                ? `Daily counts show a clear inflection on ${when.change_started_on}.`
                : 'No clear inflection — the change is gradual or noisy.'}
            </div>
          </div>
        </div>
      </div>

      {/* WHY + WHAT — soft blue card with structured sections when possible */}
      <div className="why-what-card">
        <div className="why-what-head">
          <span className="invest-panel-title">💡 Why &amp; What to do</span>
          <span className="explanation-source-tag" style={{ fontSize: 9 }}>
            {result.source === 'gemini' && '✨ Gemini'}
            {result.source === 'anthropic' && '✨ Claude'}
            {result.source === 'template' && 'Rule-based'}
          </span>
        </div>
        <div className="why-what-body">
          {parsed.isStructured ? (
            <>
              {parsed.hypothesis && (
                <div className="why-what-section">
                  <div className="why-what-label">Hypothesis</div>
                  <div className="why-what-text">
                    {renderInlineMarkdown(parsed.hypothesis)}
                  </div>
                </div>
              )}
              {parsed.actions && parsed.actions.length > 0 && (
                <div className="why-what-section">
                  <div className="why-what-label">Recommended actions</div>
                  <div className="invest-action-list">
                    {parsed.actions.map((a, i) => (
                      <div className="invest-action-item" key={i}>
                        <div className="invest-action-num">{i + 1}</div>
                        <div className="invest-action-text">
                          {renderInlineMarkdown(a)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="why-what-text">
              {renderMarkdownish(result.why_what)}
            </div>
          )}
        </div>
        {result.source === 'template' && (
          <div className="muted" style={{ fontSize: 10, marginTop: 6, fontStyle: 'italic', padding: '0 14px 12px' }}>
            Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env for AI-powered hypotheses.
          </div>
        )}
      </div>
    </div>
  );
}

// Polished sparkline with gradient fill and optional inflection marker.
function SparklineV2({ timeline, boundaryDate, changeDate }) {
  if (!timeline || timeline.length === 0) {
    return <div className="muted" style={{ fontSize: 12 }}>No timeline data available.</div>;
  }
  const w = 360, h = 100;
  const max = Math.max(...timeline.map((r) => r.target_count), 1);
  const stepX = w / Math.max(timeline.length - 1, 1);
  const points = timeline.map((r, i) => `${i * stepX},${h - (r.target_count / max) * (h - 10)}`);
  const linePath = points.join(' ');
  const areaPath = `M0,${h} L${linePath.replace(/ /g, ' L')} L${w},${h} Z`;

  const boundaryIdx = boundaryDate
    ? timeline.findIndex((r) => r.date.replace(/-/g, '') >= boundaryDate)
    : -1;
  const changeIdx = changeDate
    ? timeline.findIndex((r) => r.date === changeDate)
    : -1;

  return (
    <svg
      viewBox={`0 0 ${w} ${h + 14}`}
      preserveAspectRatio="none"
      style={{ display: 'block', width: '100%', height: 110 }}
    >
      <defs>
        <linearGradient id="invG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--blue)" stopOpacity="0.25" />
          <stop offset="100%" stopColor="var(--blue)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* horizontal guide lines */}
      <g stroke="var(--border)" strokeWidth="0.5">
        <line x1="0" y1={h * 0.33} x2={w} y2={h * 0.33} />
        <line x1="0" y1={h * 0.66} x2={w} y2={h * 0.66} />
      </g>
      <path d={areaPath} fill="url(#invG)" />
      <polyline
        fill="none"
        stroke="var(--blue)"
        strokeWidth="2"
        points={linePath}
      />
      {/* analysis-period start (dashed grey) */}
      {boundaryIdx > 0 && (
        <line
          x1={boundaryIdx * stepX} x2={boundaryIdx * stepX}
          y1={0} y2={h}
          stroke="var(--text-3)" strokeDasharray="3,3" strokeWidth="1"
        />
      )}
      {/* inflection (solid amber) */}
      {changeIdx > 0 && (
        <>
          <line
            x1={changeIdx * stepX} x2={changeIdx * stepX}
            y1={0} y2={h}
            stroke="var(--amber)" strokeWidth="1.5" strokeDasharray="4,3"
          />
          <rect
            x={Math.min(Math.max(changeIdx * stepX - 38, 2), w - 76)}
            y={2} width="76" height="14" rx="3"
            fill="var(--amber)"
          />
          <text
            x={Math.min(Math.max(changeIdx * stepX - 32, 6), w - 70)}
            y={11}
            fontSize="9" fill="#fff" fontWeight="500" fontFamily="Inter"
          >
            Inflection
          </text>
        </>
      )}
      <text x={0} y={h + 11} fontSize="9" fill="var(--text-3)" fontFamily="JetBrains Mono">{timeline[0]?.date}</text>
      <text x={w - 60} y={h + 11} fontSize="9" fill="var(--text-3)" fontFamily="JetBrains Mono">{timeline[timeline.length - 1]?.date}</text>
    </svg>
  );
}

// Parse why_what text into Hypothesis + numbered Actions.
// LLM prompts often produce "**Hypothesis** ... **What to do** ..." structure,
// but plain text fallback works fine too.
function parseWhyWhat(text) {
  if (!text || typeof text !== 'string') {
    return { isStructured: false, hypothesis: null, actions: [] };
  }
  // Try to find a "Hypothesis" section.
  const hypMatch = text.match(/\*\*(?:Hypothesis|Why)\*\*[:\s]*([\s\S]*?)(?=\*\*(?:What|Recommendations?|Actions?)\*\*|$)/i);
  // Try to find a "What to do" / "Actions" / "Recommendations" section.
  const actMatch = text.match(/\*\*(?:What(?:\s+to\s+do)?|Recommendations?|Actions?)\*\*[:\s]*([\s\S]*?)$/i);

  const hypothesis = hypMatch?.[1]?.trim() || null;
  const actionBlock = actMatch?.[1]?.trim() || null;

  let actions = [];
  if (actionBlock) {
    actions = actionBlock
      .split(/\n\s*(?:[•\-*]|\d+[.)])\s+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  }

  return {
    isStructured: !!(hypothesis || actions.length > 0),
    hypothesis,
    actions,
  };
}

function renderInlineMarkdown(text) {
  if (!text) return null;
  const lines = text.split('\n').filter((l) => l.trim().length > 0);
  return lines.map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    const rendered = parts.map((p, j) => {
      if (p.startsWith('**') && p.endsWith('**')) {
        return <strong key={j}>{p.slice(2, -2)}</strong>;
      }
      return <span key={j}>{p}</span>;
    });
    return (
      <div key={i} style={{ marginTop: i === 0 ? 0 : 6 }}>
        {rendered}
      </div>
    );
  });
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
      <div key={i} style={{ marginTop: line.trim() ? 6 : 0, fontSize: 13, lineHeight: 1.55 }}>
        {rendered}
      </div>
    );
  });
}
