"""
Insight Engine.

Architecture:
- Each insight is a Rule with: (1) a trigger function that runs SQL and returns
  a "finding" or None, (2) a template that turns the finding into plain English,
  (3) a severity/score so we can rank the top-N for the dashboard.
- Rules are intentionally small and independent. Adding a new insight is just
  appending a new Rule -- no changes to the orchestrator.
- We deliberately *don't* use an LLM here. PMs need to trust the numbers; a
  template-driven explanation that ties to a specific SQL result is auditable.
  Future: optional LLM "polish" pass that rewrites the template output, with
  the numbers held constant.

Severity scale:
- 0.0 -> not worth showing
- 0.4 -> notable
- 0.7 -> probably should look at this
- 1.0 -> dropping everything is justified
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Optional

from ..bigquery_client import run_query
from ..config import get_active_config
from ..sql import load_sql, render


@dataclass
class Insight:
    id: str
    title: str         # 1-line summary, plain English
    detail: str        # 1-2 sentences elaborating
    severity: float    # 0..1
    metric: dict       # raw numbers backing the claim (for the UI to render chips)
    kind: str          # "conversion" | "funnel" | "retention" | "volume"


# ---------- helpers ----------

def _yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _periods_from_range(start_yyyymmdd: str, end_yyyymmdd: str) -> tuple[str, str, str, str]:
    """Given a 'this period' YYYYMMDD range, return (this_start, this_end, prev_start, prev_end).

    The previous period is the same length immediately before. So a 30-day window
    from 2026-04-01 to 2026-04-30 compares against 2026-03-02 to 2026-03-31.
    """
    this_start = date(int(start_yyyymmdd[:4]), int(start_yyyymmdd[4:6]), int(start_yyyymmdd[6:8]))
    this_end = date(int(end_yyyymmdd[:4]), int(end_yyyymmdd[4:6]), int(end_yyyymmdd[6:8]))
    length_days = (this_end - this_start).days + 1
    prev_end = this_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length_days - 1)
    return _yyyymmdd(this_start), _yyyymmdd(this_end), _yyyymmdd(prev_start), _yyyymmdd(prev_end)


def _week_windows(today: date) -> tuple[str, str, str, str]:
    """Returns (this_start, this_end, last_start, last_end) as YYYYMMDD strings."""
    this_end = today - timedelta(days=1)
    this_start = this_end - timedelta(days=6)
    last_end = this_start - timedelta(days=1)
    last_start = last_end - timedelta(days=6)
    return _yyyymmdd(this_start), _yyyymmdd(this_end), _yyyymmdd(last_start), _yyyymmdd(last_end)


def _humanize_pct(x: float) -> str:
    return f"{x*100:.1f}%"


# ---------- individual rules ----------

def rule_conversion_change(
    start_event: str,
    end_event: str,
    today: date,
    window_days: int = 7,
    date_range: Optional[tuple[str, str]] = None,
) -> Optional[Insight]:
    """Conversion rate this period vs previous period of same length."""
    cfg = get_active_config()
    if date_range:
        this_s, this_e, last_s, last_e = _periods_from_range(*date_range)
        period_label = "vs previous period"
    else:
        this_s, this_e, last_s, last_e = _week_windows(today)
        period_label = "vs last week"
    sql = render(load_sql("insights/conversion_change.sql"), EVENTS_TABLE=cfg.events_table)
    rows = run_query(sql, {
        "start_event": start_event,
        "end_event": end_event,
        "this_start": this_s, "this_end": this_e,
        "last_start": last_s, "last_end": last_e,
        "window_days": window_days,
    })
    if not rows:
        return None
    r = rows[0]
    this_rate = float(r.get("this_rate") or 0)
    last_rate = float(r.get("last_rate") or 0)
    if last_rate == 0:
        return None
    delta = this_rate - last_rate
    rel = delta / last_rate

    # Only surface meaningful moves (>=5% relative, with at least 50 starts).
    if abs(rel) < 0.05 or (r.get("this_starts") or 0) < 50:
        return None

    direction = "dropped" if delta < 0 else "increased"
    severity = min(1.0, abs(rel) * 2)
    return Insight(
        id=f"conv_change_{start_event}_{end_event}",
        title=f"{start_event} → {end_event} conversion {direction} {_humanize_pct(abs(rel))} {period_label}",
        detail=(
            f"This period: {_humanize_pct(this_rate)} ({r['this_finishes']} of {r['this_starts']} users). "
            f"Previous: {_humanize_pct(last_rate)} ({r['last_finishes']} of {r['last_starts']})."
        ),
        severity=severity,
        metric={
            "this_rate": this_rate, "last_rate": last_rate, "rel_change": rel,
            "this_starts": r["this_starts"], "this_finishes": r["this_finishes"],
        },
        kind="conversion",
    )


def rule_largest_funnel_dropoff(funnel_steps: list[dict]) -> Optional[Insight]:
    """Given a computed funnel, flag the worst step."""
    if len(funnel_steps) < 2:
        return None
    worst = None
    for s in funnel_steps[1:]:
        d = s.get("drop_off_from_prev_pct")
        if d is None:
            continue
        if worst is None or d > worst.get("drop_off_from_prev_pct", 0):
            worst = s
    if not worst or (worst.get("drop_off_from_prev_pct") or 0) < 0.3:
        return None
    severity = min(1.0, worst["drop_off_from_prev_pct"])
    return Insight(
        id=f"funnel_drop_{worst['event']}",
        title=f"Biggest drop-off is at \"{worst['event']}\" ({_humanize_pct(worst['drop_off_from_prev_pct'])})",
        detail=(
            f"Only {worst['users']} of the previous step's users continued to {worst['event']}. "
            "This is the single biggest leak in the funnel."
        ),
        severity=severity,
        metric={
            "step": worst["index"], "event": worst["event"],
            "users": worst["users"],
            "drop_off_pct": worst["drop_off_from_prev_pct"],
        },
        kind="funnel",
    )


def rule_retention_correlation(
    today: date,
    window_days: int = 30,
    min_users: int = 50,
    date_range: Optional[tuple[str, str]] = None,
) -> list[Insight]:
    """Find day-1 events that strongly predict D7 retention."""
    cfg = get_active_config()
    if date_range:
        start_str, end_str = date_range
    else:
        end = today - timedelta(days=1)
        start = end - timedelta(days=window_days)
        start_str, end_str = _yyyymmdd(start), _yyyymmdd(end)
    sql = render(load_sql("insights/retention_correlation.sql"), EVENTS_TABLE=cfg.events_table)
    rows = run_query(sql, {
        "start_date": start_str,
        "end_date": end_str,
        "min_users": min_users,
    })
    out: list[Insight] = []
    for r in rows[:3]:  # top 3 signals only
        with_r = float(r.get("d7_retention_with_event") or 0)
        without_r = float(r.get("d7_retention_without_event") or 0)
        lift = with_r - without_r
        if lift < 0.1:  # need >=10pp absolute lift to mention
            continue
        severity = min(1.0, lift * 2)
        out.append(Insight(
            id=f"ret_corr_{r['event_name']}",
            title=f"Users who do \"{r['event_name']}\" on day 1 retain {lift*100:.1f}pp better at D7",
            detail=(
                f"D7 retention with event: {_humanize_pct(with_r)} "
                f"({r['did_event_users']} users). Without: {_humanize_pct(without_r)} "
                f"({r['no_event_users']} users). Lift: +{lift*100:.1f} percentage points."
            ),
            severity=severity,
            metric={
                "event": r["event_name"],
                "d7_with": with_r, "d7_without": without_r, "lift": lift,
            },
            kind="retention",
        ))
    return out


def rule_event_volume_change(
    today: date,
    min_users: int = 50,
    date_range: Optional[tuple[str, str]] = None,
) -> list[Insight]:
    cfg = get_active_config()
    if date_range:
        this_s, this_e, last_s, last_e = _periods_from_range(*date_range)
        period_label = "this period"
    else:
        this_s, this_e, last_s, last_e = _week_windows(today)
        period_label = "this week"
    sql = render(load_sql("insights/event_volume_change.sql"), EVENTS_TABLE=cfg.events_table)
    rows = run_query(sql, {
        "this_start": this_s, "this_end": this_e,
        "last_start": last_s, "last_end": last_e,
        "min_users": min_users,
    })
    out: list[Insight] = []
    for r in rows[:3]:
        rel = float(r.get("pct_change") or 0)
        if abs(rel) < 0.25:  # require 25% move
            continue
        direction = "spiked" if rel > 0 else "dropped"
        severity = min(1.0, abs(rel))
        out.append(Insight(
            id=f"vol_{r['event_name']}",
            title=f"\"{r['event_name']}\" {direction} {_humanize_pct(abs(rel))} {period_label}",
            detail=(
                f"This period: {r['this_users']} users. Previous: {r['last_users']} users."
            ),
            severity=severity,
            metric={"event": r["event_name"], "this": r["this_users"], "last": r["last_users"], "rel_change": rel},
            kind="volume",
        ))
    return out


# ---------- orchestrator ----------

def run_insights(
    today: date,
    funnel_steps: Optional[list[dict]] = None,
    funnel_start_event: Optional[str] = None,
    funnel_end_event: Optional[str] = None,
    date_range: Optional[tuple[str, str]] = None,
) -> list[Insight]:
    """Run all rules, return ranked list."""
    findings: list[Insight] = []

    # 1. Volume changes (always run)
    try:
        findings.extend(rule_event_volume_change(today, date_range=date_range))
    except Exception as e:  # noqa: BLE001
        print(f"[insights] volume change failed: {e}")

    # 2. Retention correlation (always run)
    try:
        findings.extend(rule_retention_correlation(today, date_range=date_range))
    except Exception as e:  # noqa: BLE001
        print(f"[insights] retention correlation failed: {e}")

    # 3. Conversion change (only if PM gave us a funnel pair)
    if funnel_start_event and funnel_end_event:
        try:
            f = rule_conversion_change(funnel_start_event, funnel_end_event, today, date_range=date_range)
            if f:
                findings.append(f)
        except Exception as e:  # noqa: BLE001
            print(f"[insights] conversion change failed: {e}")

    # 4. Funnel drop-off (only if a funnel was already computed)
    if funnel_steps:
        f = rule_largest_funnel_dropoff(funnel_steps)
        if f:
            findings.append(f)

    findings.sort(key=lambda i: i.severity, reverse=True)
    return findings
