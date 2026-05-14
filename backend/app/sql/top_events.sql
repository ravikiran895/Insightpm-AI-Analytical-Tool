-- Top events by unique users and total count.
-- Cohort filter (if any) restricts to users matching the filter.
--
-- Semantics: a user "matches" the cohort if any of their events in the window
-- satisfy the filter. We compute matching users once, then count events from
-- only those users.

WITH cohort_users AS (
  SELECT DISTINCT user_pseudo_id
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    {COHORT_FILTER_AND}
)
SELECT
  e.event_name,
  COUNT(*) AS event_count,
  COUNT(DISTINCT e.user_pseudo_id) AS unique_users
FROM {EVENTS_TABLE} e
{COHORT_JOIN}
WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
GROUP BY e.event_name
ORDER BY event_count DESC
LIMIT @limit;
