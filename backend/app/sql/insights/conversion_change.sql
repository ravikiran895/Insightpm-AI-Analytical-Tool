-- CONVERSION CHANGE WEEK-OVER-WEEK
-- For a given start->end event pair, compute conversion this week vs last week.
-- A user "converts" if they did @end_event within @window_days of doing @start_event.
--
-- This drives the "Signup conversion dropped X%" insight.

WITH this_week AS (
  SELECT user_pseudo_id, event_name, TIMESTAMP_MICROS(event_timestamp) AS t
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @this_start AND @this_end
    AND event_name IN (@start_event, @end_event)
),
last_week AS (
  SELECT user_pseudo_id, event_name, TIMESTAMP_MICROS(event_timestamp) AS t
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @last_start AND @last_end
    AND event_name IN (@start_event, @end_event)
),
this_conv AS (
  SELECT
    COUNT(DISTINCT IF(event_name = @start_event, user_pseudo_id, NULL)) AS starts,
    COUNT(DISTINCT IF(user_pseudo_id IN (
      SELECT a.user_pseudo_id FROM this_week a JOIN this_week b USING (user_pseudo_id)
      WHERE a.event_name = @start_event AND b.event_name = @end_event
        AND TIMESTAMP_DIFF(b.t, a.t, DAY) BETWEEN 0 AND @window_days
    ), user_pseudo_id, NULL)) AS finishes
  FROM this_week
),
last_conv AS (
  SELECT
    COUNT(DISTINCT IF(event_name = @start_event, user_pseudo_id, NULL)) AS starts,
    COUNT(DISTINCT IF(user_pseudo_id IN (
      SELECT a.user_pseudo_id FROM last_week a JOIN last_week b USING (user_pseudo_id)
      WHERE a.event_name = @start_event AND b.event_name = @end_event
        AND TIMESTAMP_DIFF(b.t, a.t, DAY) BETWEEN 0 AND @window_days
    ), user_pseudo_id, NULL)) AS finishes
  FROM last_week
)
SELECT
  tc.starts AS this_starts,
  tc.finishes AS this_finishes,
  SAFE_DIVIDE(tc.finishes, tc.starts) AS this_rate,
  lc.starts AS last_starts,
  lc.finishes AS last_finishes,
  SAFE_DIVIDE(lc.finishes, lc.starts) AS last_rate
FROM this_conv tc, last_conv lc;
