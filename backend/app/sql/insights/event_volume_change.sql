-- EVENT VOLUME CHANGE
-- Top N events with the largest week-over-week change in unique users.
-- Powers "X event spiked / dropped this week" insights.

WITH this_week AS (
  SELECT event_name, COUNT(DISTINCT user_pseudo_id) AS users
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @this_start AND @this_end
  GROUP BY event_name
),
last_week AS (
  SELECT event_name, COUNT(DISTINCT user_pseudo_id) AS users
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @last_start AND @last_end
  GROUP BY event_name
)
SELECT
  COALESCE(t.event_name, l.event_name) AS event_name,
  COALESCE(t.users, 0) AS this_users,
  COALESCE(l.users, 0) AS last_users,
  SAFE_DIVIDE(COALESCE(t.users, 0) - COALESCE(l.users, 0), NULLIF(l.users, 0)) AS pct_change
FROM this_week t
FULL OUTER JOIN last_week l USING (event_name)
WHERE COALESCE(l.users, 0) >= @min_users
ORDER BY ABS(IFNULL(pct_change, 0)) DESC
LIMIT 10;
