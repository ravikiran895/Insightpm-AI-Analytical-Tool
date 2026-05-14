-- COHORT RETENTION (cohort filter aware).
-- A user belongs to cohort C if their first event in the window is on day C.
-- They are "retained on day N" if they have any event on day C+N.
-- Optional cohort filter restricts the analyzed user set up front.

WITH cohort_users AS (
  SELECT DISTINCT user_pseudo_id
  FROM {EVENTS_TABLE}
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    {COHORT_FILTER_AND}
),
first_seen AS (
  SELECT
    e.user_pseudo_id,
    DATE(MIN(TIMESTAMP_MICROS(e.event_timestamp))) AS cohort_date
  FROM {EVENTS_TABLE} e
  {COHORT_JOIN}
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
  GROUP BY e.user_pseudo_id
),
activity AS (
  SELECT DISTINCT
    e.user_pseudo_id,
    DATE(TIMESTAMP_MICROS(e.event_timestamp)) AS active_date
  FROM {EVENTS_TABLE} e
  {COHORT_JOIN}
  WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
),
joined AS (
  SELECT
    fs.cohort_date,
    fs.user_pseudo_id,
    DATE_DIFF(a.active_date, fs.cohort_date, DAY) AS day_offset
  FROM first_seen fs
  JOIN activity a USING (user_pseudo_id)
  WHERE DATE_DIFF(a.active_date, fs.cohort_date, DAY) BETWEEN 0 AND 30
),
cohort_sizes AS (
  SELECT cohort_date, COUNT(DISTINCT user_pseudo_id) AS cohort_size
  FROM first_seen GROUP BY cohort_date
)
SELECT
  j.cohort_date,
  cs.cohort_size,
  COUNTIF(j.day_offset = 1) AS d1_users,
  COUNTIF(j.day_offset = 7) AS d7_users,
  COUNTIF(j.day_offset = 30) AS d30_users,
  SAFE_DIVIDE(COUNTIF(j.day_offset = 1), cs.cohort_size) AS d1_rate,
  SAFE_DIVIDE(COUNTIF(j.day_offset = 7), cs.cohort_size) AS d7_rate,
  SAFE_DIVIDE(COUNTIF(j.day_offset = 30), cs.cohort_size) AS d30_rate
FROM joined j
JOIN cohort_sizes cs USING (cohort_date)
GROUP BY j.cohort_date, cs.cohort_size
ORDER BY j.cohort_date;
