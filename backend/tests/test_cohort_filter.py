"""Cohort filter security + correctness tests.

This suite is critical: the cohort filter compiler is the only place where
user input becomes part of generated SQL. Everything else uses query
parameters. A regression here is an injection vulnerability.
"""
import pytest

from app.services.cohort_filter import (
    _RAW_COLUMNS,
    compile_filters,
    humanize_filter,
)


class TestEmpty:
    def test_empty_list_returns_empty(self):
        r = compile_filters([])
        assert r.sql == ""
        assert r.params == {}

    def test_none_returns_empty(self):
        r = compile_filters(None)
        assert r.sql == ""
        assert r.params == {}


class TestRawColumns:
    def test_geo_country_equals(self):
        r = compile_filters([
            {"field": "geo.country", "field_type": "column",
             "operator": "equals", "values": ["IN"]}
        ])
        assert "geo.country = @f0_v0" in r.sql
        assert r.params["f0_v0"] == "IN"

    def test_platform_in(self):
        r = compile_filters([
            {"field": "platform", "field_type": "column",
             "operator": "in", "values": ["ANDROID", "IOS"]}
        ])
        assert "IN UNNEST(@f0_vs)" in r.sql
        assert r.params["f0_vs"] == ["ANDROID", "IOS"]

    def test_app_version_starts_with(self):
        r = compile_filters([
            {"field": "app_info.version", "field_type": "column",
             "operator": "starts_with", "values": ["2.4"]}
        ])
        assert "LIKE @f0_v0" in r.sql
        assert r.params["f0_v0"] == "2.4%"


class TestUserProperties:
    def test_user_property_extracted_via_unnest(self):
        r = compile_filters([
            {"field": "subscription_tier", "field_type": "user_property",
             "operator": "equals", "values": ["pro"]}
        ])
        # Field name is bound as a parameter, not inlined
        assert "UNNEST(user_properties)" in r.sql
        assert "WHERE key = @f0_key" in r.sql
        assert r.params["f0_key"] == "subscription_tier"
        assert r.params["f0_v0"] == "pro"


class TestEventParams:
    def test_event_param_contains(self):
        r = compile_filters([
            {"field": "screen_name", "field_type": "event_param",
             "operator": "contains", "values": ["checkout"]}
        ])
        assert "UNNEST(event_params)" in r.sql
        assert "LIKE @f0_v0" in r.sql
        assert r.params["f0_v0"] == "%checkout%"


class TestMultipleFilters:
    def test_multiple_anded(self):
        r = compile_filters([
            {"field": "geo.country", "field_type": "column",
             "operator": "equals", "values": ["IN"]},
            {"field": "app_info.version", "field_type": "column",
             "operator": "equals", "values": ["2.4.0"]},
        ])
        assert " AND " in r.sql
        assert r.params["f0_v0"] == "IN"
        assert r.params["f1_v0"] == "2.4.0"

    def test_param_names_dont_collide(self):
        # 5 filters -> 5 distinct param keys per value
        filters = [
            {"field": "platform", "field_type": "column",
             "operator": "equals", "values": [f"v{i}"]}
            for i in range(5)
        ]
        r = compile_filters(filters)
        # All 5 param keys should be present
        for i in range(5):
            assert f"@f{i}_v0" in r.sql
            assert r.params[f"f{i}_v0"] == f"v{i}"


# =============================================================
# SECURITY tests — these MUST pass
# =============================================================

class TestSecurityAllowlists:
    def test_raw_column_allowlist_enforced(self):
        # user_pseudo_id is NOT in the allowlist, must be rejected
        with pytest.raises(ValueError, match="not allowed"):
            compile_filters([
                {"field": "user_pseudo_id", "field_type": "column",
                 "operator": "equals", "values": ["abc"]}
            ])

    def test_arbitrary_sql_as_field_rejected(self):
        with pytest.raises(ValueError):
            compile_filters([
                {"field": "1=1; DROP TABLE x;--", "field_type": "column",
                 "operator": "equals", "values": ["x"]}
            ])

    def test_bad_operator_rejected(self):
        with pytest.raises(ValueError, match="operator"):
            compile_filters([
                {"field": "geo.country", "field_type": "column",
                 "operator": "DROP TABLE; --", "values": ["x"]}
            ])

    def test_bad_field_type_rejected(self):
        with pytest.raises(ValueError, match="field_type"):
            compile_filters([
                {"field": "x", "field_type": "raw_sql",
                 "operator": "equals", "values": ["x"]}
            ])

    def test_non_primitive_value_rejected(self):
        with pytest.raises(ValueError):
            compile_filters([
                {"field": "geo.country", "field_type": "column",
                 "operator": "equals", "values": [{"$ne": None}]}
            ])

    def test_empty_values_rejected(self):
        with pytest.raises(ValueError):
            compile_filters([
                {"field": "geo.country", "field_type": "column",
                 "operator": "equals", "values": []}
            ])


class TestSecurityInjection:
    """The whole point of parameterization: malicious values land in params,
    not in the SQL string. BigQuery binds them safely at execution time."""

    def test_sql_injection_in_value_isolated_to_params(self):
        evil = "'; DROP TABLE foo; --"
        r = compile_filters([
            {"field": "geo.country", "field_type": "column",
             "operator": "equals", "values": [evil]}
        ])
        # Malicious string is in the params dict, NOT in the SQL string
        assert "DROP TABLE" not in r.sql
        assert r.params["f0_v0"] == evil

    def test_injection_in_user_property_value(self):
        evil = "x'; DELETE FROM users; --"
        r = compile_filters([
            {"field": "tier", "field_type": "user_property",
             "operator": "equals", "values": [evil]}
        ])
        assert "DELETE" not in r.sql
        assert r.params["f0_v0"] == evil

    def test_injection_in_field_name_for_user_property_is_bound_too(self):
        """User-property field NAMES go through @bd_key params,
        so a malicious field name can't break out either."""
        r = compile_filters([
            {"field": "evil'; --", "field_type": "user_property",
             "operator": "equals", "values": ["x"]}
        ])
        # The injection attempt is in params, not in SQL
        assert "evil';" not in r.sql
        assert r.params["f0_key"] == "evil'; --"


class TestRawColumnsList:
    """Sanity check on the allowlist contents."""

    def test_allowlist_contains_expected_columns(self):
        expected = {
            "platform", "geo.country", "app_info.version",
            "device.category", "traffic_source.source",
        }
        assert expected.issubset(_RAW_COLUMNS)

    def test_allowlist_does_not_contain_user_pseudo_id(self):
        # user_pseudo_id is the user identifier; should NOT be filterable
        # via raw column path (no PII surfacing through filters)
        assert "user_pseudo_id" not in _RAW_COLUMNS


class TestHumanize:
    def test_equals_humanized(self):
        assert "=" in humanize_filter({
            "field": "geo.country", "field_type": "column",
            "operator": "equals", "values": ["IN"]
        })

    def test_contains_humanized(self):
        h = humanize_filter({
            "field": "page", "field_type": "event_param",
            "operator": "contains", "values": ["checkout"]
        })
        assert "contains" in h
