-- USER BEHAVIOR PROFILE
-- Fetches the full event journey of a single user_pseudo_id within a window.
-- Returns up to @event_limit events ordered chronologically.
--
-- We deliberately don't return user_pseudo_id in the result -- the caller
-- already has it. This makes log inspection less risky.

SELECT
  TIMESTAMP_MICROS(event_timestamp) AS event_time,
  event_name,
  platform,
  -- Pull commonly useful params for behavioral analysis
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_title') AS page_title,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'screen_name') AS screen_name,
  (SELECT value.int_value    FROM UNNEST(event_params) WHERE key = 'engagement_time_msec') AS engagement_msec,
  (SELECT value.int_value    FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
  geo.country AS country,
  device.category AS device_category,
  device.operating_system AS os,
  app_info.version AS app_version
FROM {EVENTS_TABLE}
WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
  AND user_pseudo_id = @user_id
ORDER BY event_timestamp
LIMIT @event_limit;
