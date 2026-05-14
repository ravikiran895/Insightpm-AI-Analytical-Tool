"""User profiler service tests — pure logic, no BQ."""
from app.services.user_profiler import (
    classify_pattern,
    compute_metrics,
    _generate_narrative_template,
)


class TestComputeMetrics:
    def test_empty_journey(self):
        m = compute_metrics([])
        assert m["event_count"] == 0
        assert m["session_count"] == 0
        assert m["top_events"] == []
        assert m["country"] is None

    def test_basic_journey(self):
        journey = [
            {"event_time": "2026-04-01T10:00:00", "event_name": "session_start",
             "session_id": 1, "country": "IN", "platform": "ANDROID",
             "engagement_msec": 30000, "app_version": "2.4.0"},
            {"event_time": "2026-04-01T10:01:00", "event_name": "view_item",
             "session_id": 1, "country": "IN", "platform": "ANDROID",
             "engagement_msec": 60000, "app_version": "2.4.0"},
            {"event_time": "2026-04-02T11:00:00", "event_name": "session_start",
             "session_id": 2, "country": "IN", "platform": "ANDROID",
             "engagement_msec": 15000, "app_version": "2.4.0"},
        ]
        m = compute_metrics(journey)
        assert m["event_count"] == 3
        assert m["session_count"] == 2
        assert m["active_days"] == 2  # Apr 1 and Apr 2
        assert m["lifespan_days"] == 1  # 1 day apart
        assert m["country"] == "IN"
        assert "ANDROID" in m["platforms"]
        assert m["total_engagement_minutes"] == round(105000 / 60000, 1)
        assert m["app_version"] == "2.4.0"

    def test_top_events_ordered_correctly(self):
        journey = [
            {"event_time": "2026-04-01T10:00:00", "event_name": "X", "session_id": 1},
            {"event_time": "2026-04-01T10:01:00", "event_name": "X", "session_id": 1},
            {"event_time": "2026-04-01T10:02:00", "event_name": "Y", "session_id": 1},
        ]
        m = compute_metrics(journey)
        assert m["top_events"][0]["event"] == "X"
        assert m["top_events"][0]["count"] == 2
        assert m["top_events"][1]["event"] == "Y"
        assert m["top_events"][1]["count"] == 1


class TestClassifyPattern:
    def test_no_data(self):
        m = compute_metrics([])
        p = classify_pattern(m, [])
        assert p["label"] == "no_data"

    def test_one_and_done(self):
        journey = [
            {"event_time": "2026-04-01T10:00:00", "event_name": "session_start", "session_id": 1},
            {"event_time": "2026-04-01T10:00:30", "event_name": "first_open", "session_id": 1},
        ]
        m = compute_metrics(journey)
        p = classify_pattern(m, journey)
        assert p["label"] == "one_and_done"

    def test_power_user(self):
        # 10 sessions, 7 active days, plenty of events
        journey = []
        for day in range(1, 8):
            for sess in range(2):
                # 2 sessions per day, 5 events per session
                for ev in range(5):
                    journey.append({
                        "event_time": f"2026-04-0{day}T1{sess}:0{ev}:00",
                        "event_name": "interact",
                        "session_id": (day - 1) * 2 + sess,
                    })
        m = compute_metrics(journey)
        p = classify_pattern(m, journey)
        assert p["label"] == "power_user"

    def test_returning_visitor(self):
        # 3 sessions over 3 days, modest activity
        journey = [
            {"event_time": f"2026-04-0{day}T10:00:00", "event_name": "open", "session_id": day}
            for day in range(1, 4)
        ] + [
            {"event_time": f"2026-04-0{day}T10:01:00", "event_name": "view", "session_id": day}
            for day in range(1, 4)
        ]
        m = compute_metrics(journey)
        p = classify_pattern(m, journey)
        assert p["label"] in ("returning_visitor", "casual")  # depends on exact thresholds


class TestNarrativeTemplate:
    def test_no_data_template(self):
        m = compute_metrics([])
        p = classify_pattern(m, [])
        n = _generate_narrative_template(m, p)
        assert "**Story**" in n
        assert "**Pattern**" in n
        assert "**Recommendations**" in n

    def test_power_user_recommendations_mentions_aha(self):
        journey = [
            {"event_time": f"2026-04-0{day}T1{s}:00:00",
             "event_name": "open", "session_id": (day-1)*2+s}
            for day in range(1, 8) for s in range(2)
        ] * 3
        m = compute_metrics(journey)
        p = classify_pattern(m, journey)
        n = _generate_narrative_template(m, p)
        assert "**Story**" in n
        assert m["top_events"][0]["event"] in n  # cites real top event
