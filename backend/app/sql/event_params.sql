-- Extract event_params for a given event. The GA4 schema stores params as
-- ARRAY<STRUCT<key STRING, value STRUCT<string_value STRING, int_value INT64, ...>>>
-- so we UNNEST and pivot the value to its actual type.
SELECT
  user_pseudo_id,
  TIMESTAMP_MICROS(event_timestamp) AS event_time,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = @param_key) AS param_string,
  (SELECT value.int_value    FROM UNNEST(event_params) WHERE key = @param_key) AS param_int,
  (SELECT value.double_value FROM UNNEST(event_params) WHERE key = @param_key) AS param_double
FROM {EVENTS_TABLE}
WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
  AND event_name = @event_name
LIMIT @limit;
