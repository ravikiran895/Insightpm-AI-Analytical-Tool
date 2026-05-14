"""SQL template loader with cohort-filter placeholder support.

The cohort feature works by adding two coordinated placeholders to every query:

  {COHORT_FILTER_AND}   - inside the cohort_users CTE, expands to "AND <filters>"
                          when filters are present, or "" otherwise.

  {COHORT_JOIN}         - in the main query body, expands to a JOIN that
                          restricts to filtered users when filters are present,
                          or "" otherwise (so the same template works either way).
"""
from __future__ import annotations

from pathlib import Path

_SQL_DIR = Path(__file__).parent

_cache: dict[str, str] = {}


def load_sql(relpath: str) -> str:
    if relpath in _cache:
        return _cache[relpath]
    text = (_SQL_DIR / relpath).read_text(encoding="utf-8")
    _cache[relpath] = text
    return text


def render(template: str, **identifiers: str) -> str:
    """Replace {NAMED} placeholders with trusted identifier strings.

    SECURITY: Only call this with identifiers we control (table refs,
    pre-validated step expressions, cohort fragments produced by
    cohort_filter.compile_filters). Never with raw user input.
    """
    out = template
    for k, v in identifiers.items():
        out = out.replace("{" + k + "}", v)
    return out


def cohort_clauses(cohort_filter_sql: str) -> dict[str, str]:
    """Given a compiled cohort filter SQL fragment (or empty string), return
    the dict of placeholder substitutions for the SQL templates.

    When no filter:
        COHORT_FILTER_AND = ""   (no extra AND in the cohort_users CTE)
        COHORT_JOIN = ""         (no JOIN in the main body, all users analyzed)

    When filter present:
        COHORT_FILTER_AND = "AND <fragment>"
        COHORT_JOIN = "JOIN cohort_users cu USING (user_pseudo_id)"

    The cohort_users CTE is computed once but only useful when filters exist.
    BigQuery's optimizer prunes the unused CTE, so the no-filter path doesn't
    pay for it.
    """
    if cohort_filter_sql.strip():
        return {
            "COHORT_FILTER_AND": f"AND {cohort_filter_sql}",
            "COHORT_JOIN": "JOIN cohort_users cu USING (user_pseudo_id)",
        }
    return {
        "COHORT_FILTER_AND": "",
        "COHORT_JOIN": "",
    }
