"""Tests for the SQLite layer: connection profiles + saved funnels."""
import pytest


class TestConnectionProfiles:
    def test_create_and_list(self, temp_home):
        from app import db
        p = db.create_profile("Production", "my-proj", "analytics_1")
        assert p["id"] > 0
        assert p["name"] == "Production"
        assert p["has_credentials"] is False  # no SA passed

        profiles = db.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Production"

    def test_create_with_credentials(self, temp_home):
        from app import db
        sa = {"client_email": "x@y.iam.gserviceaccount.com", "private_key": "FAKE"}
        p = db.create_profile("Prod", "my-proj", "analytics_1", service_account_info=sa)
        assert p["has_credentials"] is True

        # has_credentials is exposed but the JSON itself shouldn't appear in list
        profiles = db.list_profiles()
        assert "service_account_info" not in profiles[0]
        assert "sa_json" not in profiles[0]

        # Retrievable explicitly
        full = db.get_profile(p["id"], with_credentials=True)
        assert full["service_account_info"]["client_email"] == "x@y.iam.gserviceaccount.com"

    def test_default_profile(self, temp_home):
        from app import db
        p1 = db.create_profile("Prod", "p1", "ds1", is_default=True)
        p2 = db.create_profile("Stage", "p2", "ds2", is_default=False)

        default = db.get_default_profile()
        assert default["name"] == "Prod"

        # Set p2 as default; p1 should no longer be default
        db.set_default_profile(p2["id"])
        default = db.get_default_profile()
        assert default["name"] == "Stage"

        p1_after = db.get_profile(p1["id"])
        assert p1_after["is_default"] is False

    def test_only_one_default_at_a_time(self, temp_home):
        from app import db
        db.create_profile("A", "p1", "ds1", is_default=True)
        db.create_profile("B", "p2", "ds2", is_default=True)
        # Creating B with is_default=True should have unset A's default
        defaults = [p for p in db.list_profiles() if p["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "B"

    def test_duplicate_name_rejected(self, temp_home):
        from app import db
        db.create_profile("Production", "p1", "ds1")
        with pytest.raises(Exception):  # IntegrityError
            db.create_profile("Production", "p2", "ds2")

    def test_last_used_tracking(self, temp_home):
        from app import db
        p = db.create_profile("Prod", "p1", "ds1")
        assert p["last_used_at"] is None

        db.update_profile_last_used(p["id"])
        fresh = db.get_profile(p["id"])
        assert fresh["last_used_at"] is not None

    def test_delete(self, temp_home):
        from app import db
        p = db.create_profile("Prod", "p1", "ds1")
        assert db.delete_profile(p["id"]) is True
        assert db.get_profile(p["id"]) is None
        assert db.delete_profile(p["id"]) is False  # already deleted


class TestSavedFunnels:
    def test_create_and_list_scoped_per_profile(self, temp_home):
        from app import db
        p1 = db.create_profile("ProdA", "x", "y")
        p2 = db.create_profile("ProdB", "x2", "y2")

        config = {"steps": ["a", "b", "c"], "window_days": 7}
        f1 = db.create_saved_funnel(p1["id"], "Funnel A", config)
        db.create_saved_funnel(p1["id"], "Funnel A2", config)

        # p1 sees both, p2 sees zero
        assert len(db.list_saved_funnels(p1["id"])) == 2
        assert len(db.list_saved_funnels(p2["id"])) == 0

    def test_config_round_trip(self, temp_home):
        from app import db
        p = db.create_profile("P", "x", "y")
        config = {
            "steps": ["GameStart", "MaxAttended"],
            "window_days": 14,
            "cohort": [
                {"field": "geo.country", "field_type": "column",
                 "operator": "equals", "values": ["IN"]}
            ],
        }
        f = db.create_saved_funnel(p["id"], "India Game Flow", config)
        retrieved = db.get_saved_funnel(f["id"])
        assert retrieved["config"]["steps"] == ["GameStart", "MaxAttended"]
        assert retrieved["config"]["cohort"][0]["values"] == ["IN"]
        assert retrieved["config"]["window_days"] == 14

    def test_update(self, temp_home):
        from app import db
        p = db.create_profile("P", "x", "y")
        f = db.create_saved_funnel(p["id"], "v1", {"steps": ["a", "b"], "window_days": 7})
        updated = db.update_saved_funnel(f["id"], "v2", {"steps": ["a", "b", "c"], "window_days": 14})
        assert updated["name"] == "v2"
        assert len(updated["config"]["steps"]) == 3

    def test_delete(self, temp_home):
        from app import db
        p = db.create_profile("P", "x", "y")
        f = db.create_saved_funnel(p["id"], "x", {"steps": ["a", "b"]})
        assert db.delete_saved_funnel(f["id"]) is True
        assert db.get_saved_funnel(f["id"]) is None

    def test_cascade_delete_with_profile(self, temp_home):
        """Deleting a profile should remove its saved funnels."""
        from app import db
        p = db.create_profile("P", "x", "y")
        f = db.create_saved_funnel(p["id"], "x", {"steps": ["a", "b"]})
        assert db.get_saved_funnel(f["id"]) is not None

        db.delete_profile(p["id"])
        assert db.get_saved_funnel(f["id"]) is None
