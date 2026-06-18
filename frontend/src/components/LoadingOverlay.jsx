import { useEffect, useState, useRef } from 'react';

/**
 * Full-screen loading overlay with InsightPM logo + sequenced step animation.
 *
 * Used by:
 *   - InsightsPanel (investigation flow)
 *   - UserProfiler (build profile flow)
 *
 * Behavior:
 *   - Opens immediately on `busy=true`
 *   - Reveals steps on a quick schedule (the first N-1 steps complete on a timer
 *     while the API runs, because the backend's parallel queries finish in
 *     ~0.5-1.5s each but the UI can't see that progress)
 *   - The LAST step (typically "Claude synthesis") stays in the spinning state
 *     until `busy=false` — this is honest about which part is actually slow
 *   - Pressing Escape or clicking the backdrop dismisses the overlay (the
 *     underlying API request continues in the background; cancellation is
 *     the parent component's job if needed)
 *   - Live timer shows elapsed seconds so the user knows it's not frozen
 *
 * Props:
 *   - busy: boolean — show/hide overlay (parent controls based on API state)
 *   - title: string — main heading
 *   - desc: string — descriptive subtitle
 *   - steps: [{ name, duration }] — duration is ms before this step auto-completes
 *   - onDismiss: optional — called when user presses Escape or clicks backdrop
 */
export default function LoadingOverlay({ busy, title, desc, steps, onDismiss }) {
  // Track each step's state: 'pending' | 'active' | 'done'
  const [stepStates, setStepStates] = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const startedAtRef = useRef(null);
  const timersRef = useRef([]);
  const tickerRef = useRef(null);

  // Reset and start animation when overlay opens
  useEffect(() => {
    if (!busy) {
      // Cleanup all timers
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
      if (tickerRef.current) clearInterval(tickerRef.current);
      tickerRef.current = null;
      startedAtRef.current = null;
      setStepStates([]);
      setElapsed(0);
      return;
    }

    // Initialize states: all pending
    const initial = steps.map(() => 'pending');
    setStepStates(initial);
    startedAtRef.current = Date.now();
    setElapsed(0);

    // Activate step 0 immediately
    timersRef.current.push(setTimeout(() => {
      setStepStates((prev) => {
        const next = [...prev];
        if (next[0] === 'pending') next[0] = 'active';
        return next;
      });
    }, 60));

    // Schedule each step's completion AND the next step's activation.
    // The LAST step never auto-completes — it waits for busy=false.
    let cumulative = 0;
    steps.forEach((step, i) => {
      cumulative += step.duration;

      if (i < steps.length - 1) {
        // Complete this step + activate next
        timersRef.current.push(setTimeout(() => {
          setStepStates((prev) => {
            const next = [...prev];
            next[i] = 'done';
            if (next[i + 1] === 'pending') next[i + 1] = 'active';
            return next;
          });
        }, cumulative));
      }
    });

    // Live timer (updates every 100ms)
    tickerRef.current = setInterval(() => {
      if (startedAtRef.current) {
        setElapsed(((Date.now() - startedAtRef.current) / 1000));
      }
    }, 100);

    // Cleanup on unmount or busy toggle
    return () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
      if (tickerRef.current) clearInterval(tickerRef.current);
      tickerRef.current = null;
    };
  }, [busy, steps]);

  // Escape-to-dismiss
  useEffect(() => {
    if (!busy || !onDismiss) return;
    const handler = (e) => {
      if (e.key === 'Escape') onDismiss();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [busy, onDismiss]);

  if (!busy) return null;

  return (
    <div
      className="ipm-overlay"
      onClick={(e) => {
        // Click on backdrop only — not on the card itself
        if (e.target === e.currentTarget && onDismiss) onDismiss();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="ipm-overlay-card">
        <div className="ipm-overlay-logo">
          {/* Inline brand SVG — works fully offline, never loads from CDN */}
          <svg viewBox="0 0 24 24" width="36" height="36" xmlns="http://www.w3.org/2000/svg">
            <rect x="3" y="14" width="3" height="7" rx="0.5" fill="white" fillOpacity="0.55" />
            <rect x="8" y="10" width="3" height="11" rx="0.5" fill="white" fillOpacity="0.78" />
            <rect x="13" y="6" width="3" height="15" rx="0.5" fill="white" />
            <circle cx="17.5" cy="8.5" r="4.5" fill="none" stroke="white" strokeWidth="1.8" />
            <line x1="20.8" y1="11.8" x2="23" y2="14" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </div>
        <div className="ipm-overlay-title">{title}</div>
        <div className="ipm-overlay-desc">{desc}</div>
        <div className="ipm-overlay-steps">
          {steps.map((step, i) => {
            const state = stepStates[i] || 'pending';
            return (
              <div key={i} className={`ipm-overlay-step ipm-step-${state}`}>
                <span className="ipm-step-icon">
                  {state === 'done' && <CheckIcon />}
                  {state === 'active' && <SpinnerIcon />}
                  {state === 'pending' && <DotIcon />}
                </span>
                <span className="ipm-step-name">{step.name}</span>
                {state === 'done' && (
                  <span className="ipm-step-time">
                    {(step.duration / 1000).toFixed(1)}s
                  </span>
                )}
              </div>
            );
          })}
        </div>
        <div className="ipm-overlay-timer">{elapsed.toFixed(1)}s elapsed</div>
        {onDismiss && (
          <button
            className="ipm-overlay-dismiss"
            onClick={onDismiss}
            type="button"
          >
            Dismiss (esc) — request continues in background
          </button>
        )}
      </div>
    </div>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="13 4 6 12 3 9" />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="13"
      height="13"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      className="ipm-step-spinner"
    >
      <path d="M21 12a9 9 0 1 1-6.2-8.5" />
    </svg>
  );
}

function DotIcon() {
  return (
    <svg viewBox="0 0 16 16" width="9" height="9" className="ipm-step-dot">
      <circle cx="8" cy="8" r="4" fill="currentColor" />
    </svg>
  );
}
