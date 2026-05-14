-- RETENTION CORRELATION
-- For each event, compute D7 retention of users who did the event in their
-- first 24 hours vs users who didn't. Surfaces "aha moment" candidates.
--
-- Drives the "Users who do X retain N% better" insight.

WITH first_seen AS (
  SELECT
    user_pseudo_id,
    DATE(MIN(TIMESTAMP_MICROS(event_timestamp))) AS cohort_date,
    MIN(TIMESTAMP_MICROS(event_timestamp)) AS first_t
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
  GROUP BY user_pseudo_id
),
day1_events AS (
  -- Events done within 24h of first seen.
  SELECT DISTINCT
    e.user_pseudo_id,
    e.event_name
  FROM {EVENTS_TABLE} e
  JOIN first_seen f USING (user_pseudo_id)
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    AND TIMESTAMP_DIFF(TIMESTAMP_MICROS(e.event_timestamp), f.first_t, HOUR) BETWEEN 0 AND 24
),
d7_returning AS (
  SELECT DISTINCT f.user_pseudo_id
  FROM first_seen f
  JOIN {EVENTS_TABLE} e USING (user_pseudo_id)
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    AND DATE_DIFF(DATE(TIMESTAMP_MICROS(e.event_timestamp)), f.cohort_date, DAY) = 7
),
event_universe AS (
  SELECT DISTINCT event_name FROM day1_events
)
SELECT
  eu.event_name,
  COUNT(DISTINCT IF(de.user_pseudo_id IS NOT NULL, fs.user_pseudo_id, NULL)) AS did_event_users,
  COUNT(DISTINCT IF(de.user_pseudo_id IS NULL,     fs.user_pseudo_id, NULL)) AS no_event_users,
  SAFE_DIVIDE(
    COUNT(DISTINCT IF(de.user_pseudo_id IS NOT NULL AND ret.user_pseudo_id IS NOT NULL, fs.user_pseudo_id, NULL)),
    NULLIF(COUNT(DISTINCT IF(de.user_pseudo_id IS NOT NULL, fs.user_pseudo_id, NULL)), 0)
  ) AS d7_retention_with_event,
  SAFE_DIVIDE(
    COUNT(DISTINCT IF(de.user_pseudo_id IS NULL AND ret.user_pseudo_id IS NOT NULL, fs.user_pseudo_id, NULL)),
    NULLIF(COUNT(DISTINCT IF(de.user_pseudo_id IS NULL, fs.user_pseudo_id, NULL)), 0)
  ) AS d7_retention_without_event
FROM event_universe eu
CROSS JOIN first_seen fs
LEFT JOIN day1_events de ON de.user_pseudo_id = fs.user_pseudo_id AND de.event_name = eu.event_name
LEFT JOIN d7_returning ret ON ret.user_pseudo_id = fs.user_pseudo_id
GROUP BY eu.event_name
HAVING did_event_users >= @min_users AND no_event_users >= @min_users
ORDER BY (d7_retention_with_event - d7_retention_without_event) DESC
LIMIT 10;
