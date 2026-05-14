"""
Natural Language Query.

Uses the LLM abstraction (Gemini → Anthropic → keyword fallback) to map
free-text questions to a structured intent + parameters from a closed set.
The numeric answer always comes from deterministic services -- the LLM
never produces numbers.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

from . import event_service, insight_engine, retention_service
from .llm_client import call_llm_json, is_refusal

log = logging.getLogger("insightpm.nlq")


_INTENTS_SPEC = [
    {
        "name": "retention_overview",
        "description": "User retention metrics - D1, D7, D30. Use when asking about retention being low/high, churn, users coming back.",
        "params": {},
    },
    {
        "name": "where_users_drop",
        "description": "Find biggest drop-off step in a funnel. Use for questions about where users drop off, leaks, conversion problems.",
        "params": {},
    },
    {
        "name": "top_events",
        "description": "List most common events by user count. Use for what users are doing, top/popular events.",
        "params": {},
    },
    {
        "name": "growth_check",
        "description": "Compare DAU over time. Use for growth questions, are we growing, DAU/MAU trends.",
        "params": {},
    },
    {
        "name": "aha_moment",
        "description": "Find events that predict retention. Use for aha moment, magic moment, what makes users retain.",
        "params": {},
    },
    {
        "name": "compare_cohorts",
        "description": "Compare retention for two user segments. Use for any 'X vs Y' question between user groups (countries, versions, etc).",
        "params": {
            "dimension": "the user property/column to compare on (e.g. 'geo.country', 'app_info.version', 'platform')",
            "value_a": "first segment value",
            "value_b": "second segment value (or empty string to compare against everyone else)",
        },
    },
    {
        "name": "off_topic",
        "description": "Question is NOT about product analytics data (e.g. asking about news, recipes, code unrelated to data, general knowledge, jokes, opinions, anything outside the analytics scope). Use this for any question that doesn't relate to events/users/funnels/retention/cohorts/behavior in the dataset.",
        "params": {},
    },
    {
        "name": "unknown",
        "description": "Question is about analytics but doesn't match any specific intent above.",
        "params": {},
    },
]


_NLQ_SYSTEM_PROMPT = """You are an intent classifier for InsightPM, a product analytics tool.

Pick the SINGLE best matching intent from the list and extract any parameters.

If the question is NOT about product analytics data (events, users, funnels, retention, cohorts, behavior), pick "off_topic".

Respond with a JSON object: {"intent": "<intent_name>", "params": {...}}

Never invent intents not in the list. Never invent parameter values."""


def _build_intent_descriptions() -> str:
    lines = []
    for spec in _INTENTS_SPEC:
        lines.append(f"- {spec['name']}: {spec['description']}")
        if spec["params"]:
            lines.append(f"  params: {json.dumps(spec['params'])}")
    return "\n".join(lines)


def _classify_with_llm(question: str) -> Optional[dict]:
    """Returns {intent, params, classifier} or None on failure."""
    full_prompt = _NLQ_SYSTEM_PROMPT + "\n\nAvailable intents:\n" + _build_intent_descriptions()
    result = call_llm_json(full_prompt, question, max_tokens=200)
    if result is None:
        return None
    parsed, provider = result

    valid_intents = {s["name"] for s in _INTENTS_SPEC}
    if "intent" not in parsed or parsed["intent"] not in valid_intents:
        log.warning(f"LLM returned invalid intent: {parsed}")
        return None
    parsed.setdefault("params", {})
    return {**parsed, "classifier": provider}


# ---- Keyword fallback (used when no LLM available) ----

_KEYWORD_PHRASES = {
    "retention_overview": [
        "why is retention low", "why low retention",
        "retention dropping", "retention is dropping", "retention is going down",
        "retention bad", "retention is bad", "retention is low",
        "users not coming back", "churn",
    ],
    "where_users_drop": [
        "where do users drop", "where do they drop", "biggest drop",
        "funnel drop", "where are we losing", "dropoff",
    ],
    "top_events": [
        "top events", "most common events", "what are users doing",
        "what events", "biggest events",
    ],
    "growth_check": [
        "is growth", "are we growing", "dau", "users growing",
        "user growth", "active users",
    ],
    "aha_moment": [
        "aha moment", "what makes users retain", "what predicts retention",
        "magic moment", "key event",
    ],
}

# Heuristic off-topic filter for the keyword path. Imperfect but better than
# nothing when no LLM is available.
_OFF_TOPIC_HINTS = [
    "weather", "recipe", "joke", "movie", "music", "song", "stock", "crypto",
    "translate", "write me", "tell me a", "what's the news", "who is the",
    "capital of", "president of", "code for me", "fix my code",
]


def _classify_with_keywords(question: str) -> dict:
    q = question.lower().strip()

    # Quick off-topic check
    for hint in _OFF_TOPIC_HINTS:
        if hint in q:
            return {"intent": "off_topic", "params": {}, "classifier": "keyword"}

    best_intent = "unknown"
    best_score = 0
    for intent, phrases in _KEYWORD_PHRASES.items():
        for p in phrases:
            if p in q and len(p) > best_score:
                best_score = len(p)
                best_intent = intent
    return {"intent": best_intent, "params": {}, "classifier": "keyword"}


def _classify(question: str) -> dict:
    llm_result = _classify_with_llm(question)
    if llm_result:
        return llm_result
    return _classify_with_keywords(question)


# ---- Answer assembly (deterministic) ----

_OFF_TOPIC_RESPONSE = (
    "Sorry, I can only help with questions about your product analytics data. "
    "Try asking about retention, funnels, top events, user growth, or comparing cohorts."
)


def answer(question: str, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    classification = _classify(question)
    intent = classification["intent"]
    params = classification.get("params", {})
    classifier = classification["classifier"]

    end = today - timedelta(days=1)
    start = end - timedelta(days=29)
    start_s, end_s = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    base = {"intent": intent, "classifier": classifier}

    # Off-topic: refuse cleanly
    if intent == "off_topic":
        return {**base, "answer": _OFF_TOPIC_RESPONSE, "data": {}}

    if intent == "retention_overview":
        ret = retention_service.cohort_retention(start_s, end_s)
        h = ret["headline"]
        # h["dN_avg"] is already a rate (0-1). v0.9.1 fix: don't double-divide.
        d1 = h["d1_avg"]
        d7 = h["d7_avg"]
        d30 = h["d30_avg"]
        text = (
            f"Across the last 30 days, average D1 retention is {d1:.1%}, "
            f"D7 is {d7:.1%}, and D30 is {d30:.1%}. "
        )
        try:
            corr = insight_engine.rule_retention_correlation(today)
            if corr:
                text += f"Strongest signal: {corr[0].title.lower()}."
        except Exception:
            pass
        return {**base, "answer": text, "data": {"retention": ret}}

    if intent == "where_users_drop":
        return {
            **base,
            "answer": (
                "Pick a start and end event in the Funnel section and click Compute. "
                "I'll then highlight the step with the biggest drop in the Insights panel."
            ),
            "data": {},
        }

    if intent == "top_events":
        rows = event_service.top_events(start_s, end_s, limit=10)
        if not rows:
            return {**base, "answer": "No events in the last 30 days.", "data": {}}
        bullets = ", ".join(f"{r['event_name']} ({r['unique_users']} users)" for r in rows[:5])
        return {**base, "answer": f"Top events: {bullets}.", "data": {"events": rows}}

    if intent == "growth_check":
        rows = event_service.daily_activity(start_s, end_s)
        if len(rows) < 14:
            return {**base, "answer": "Not enough days of data to compute growth.", "data": {"daily": rows}}
        first_week = sum(r["dau"] for r in rows[:7]) / 7
        last_week = sum(r["dau"] for r in rows[-7:]) / 7
        rel = (last_week - first_week) / first_week if first_week else 0
        direction = "up" if rel >= 0 else "down"
        return {
            **base,
            "answer": (
                f"Average DAU is {direction} {abs(rel):.1%} over the last 30 days "
                f"(first week avg: {first_week:.0f}, last week avg: {last_week:.0f})."
            ),
            "data": {"daily": rows},
        }

    if intent == "aha_moment":
        corr = insight_engine.rule_retention_correlation(today)
        if not corr:
            return {
                **base,
                "answer": "No event found a strong retention lift (>10pp) in the last 30 days. Try widening the range.",
                "data": {},
            }
        bullets = " ".join(f"• {c.title}." for c in corr[:3])
        return {**base, "answer": f"Top retention-predicting events: {bullets}",
                "data": {"correlations": [c.__dict__ for c in corr]}}

    if intent == "compare_cohorts":
        dim = params.get("dimension")
        a = params.get("value_a")
        b = params.get("value_b")
        if not dim or not a:
            return {
                **base,
                "answer": "I understood you want to compare cohorts but couldn't extract which dimension. Try: 'compare retention India vs US'.",
                "data": {},
            }

        from .cohort_filter import _RAW_COLUMNS
        ft = "column" if dim in _RAW_COLUMNS else "user_property"

        cohort_a = [{"field": dim, "field_type": ft, "operator": "equals", "values": [a]}]
        ret_a = retention_service.cohort_retention(start_s, end_s, cohort=cohort_a)
        ha = ret_a["headline"]
        # d7_avg is already a rate (v0.9.1 fix)
        d7_a = ha["d7_avg"]

        if b:
            cohort_b = [{"field": dim, "field_type": ft, "operator": "equals", "values": [b]}]
            ret_b = retention_service.cohort_retention(start_s, end_s, cohort=cohort_b)
            hb = ret_b["headline"]
            d7_b = hb["d7_avg"]
            text = (
                f"D7 retention: {dim}={a} → {d7_a:.1%} ({ha['total_users']} users), "
                f"{dim}={b} → {d7_b:.1%} ({hb['total_users']} users)."
            )
            return {**base, "answer": text, "data": {"a": ret_a, "b": ret_b, "dim": dim}}
        else:
            text = f"D7 retention for {dim}={a}: {d7_a:.1%} across {ha['total_users']} users."
            return {**base, "answer": text, "data": {"a": ret_a, "dim": dim}}

    # Unknown but on-topic
    return {
        **base,
        "answer": (
            "I can answer questions like: \"why is retention low\", \"where do users drop\", "
            "\"top events\", \"are we growing\", \"aha moment\", or \"compare retention India vs US\"."
        ),
        "data": {},
    }
