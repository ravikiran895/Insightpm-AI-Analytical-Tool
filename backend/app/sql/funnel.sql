-- FUNNEL TEMPLATE (cohort filter aware).
-- Step list is dynamic, so the Python service generates the MIN(IF(...)) lines
-- for each step before executing. See funnel_service.py.
--
-- Funnel semantics:
--   - A user "completes" step N if they did step N's event AFTER they did step (N-1).
--   - Conversion window is bounded by @window_days from step 1 to step N.
--   - Cohort filter (if any) restricts the analyzed user set.

WITH cohort_users AS (
  SELECT DISTINCT user_pseudo_id
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    {COHORT_FILTER_AND}
),
step_events AS (
  SELECT
    e.user_pseudo_id,
    e.event_name,
    TIMESTAMP_MICROS(e.event_timestamp) AS event_time
  FROM {EVENTS_TABLE} e
  {COHORT_JOIN}
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    AND e.event_name IN UNNEST(@step_events)
),
user_step_times AS (
  SELECT
    user_pseudo_id,
    {STEP_AGGREGATIONS}
  FROM step_events
  GROUP BY user_pseudo_id
)
SELECT
  {STEP_COUNTS}
FROM user_step_times;
