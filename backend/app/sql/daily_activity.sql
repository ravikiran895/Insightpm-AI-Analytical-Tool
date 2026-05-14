-- Daily active users in a window. Used by the "growth" insight bucket.
SELECT
  PARSE_DATE('%Y%m%d', _TABLE_SUFFIX) AS day,
  COUNT(DISTINCT user_pseudo_id) AS dau
FROM {EVENTS_TABLE}
WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
GROUP BY day
ORDER BY day;
