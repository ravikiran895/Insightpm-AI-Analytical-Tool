"""Saved cohorts CRUD + isolation tests."""


class TestSavedCohorts:
    def test_create_and_list_scoped_per_profile(self, temp_home):
        from app import db
        p1 = db.create_profile("ProdA", "x", "y")
        p2 = db.create_profile("ProdB", "x2", "y2")

        filters = [{"field": "geo.country", "field_type": "column",
                    "operator": "equals", "values": ["IN"]}]
        c1 = db.create_saved_cohort(p1["id"], "India users", filters)
        db.create_saved_cohort(p1["id"], "Power users", [
            {"field": "platform", "field_type": "column",
             "operator": "in", "values": ["ANDROID", "IOS"]}
        ])

        # p1 sees both, p2 sees zero
        assert len(db.list_saved_cohorts(p1["id"])) == 2
        assert len(db.list_saved_cohorts(p2["id"])) == 0

    def test_filters_round_trip(self, temp_home):
        from app import db
        p = db.create_profile("P", "x", "y")
        filters = [
            {"field": "geo.country", "field_type": "column",
             "operator": "equals", "values": ["IN"]},
            {"field": "platform", "field_type": "column",
             "operator": "equals", "values": ["ANDROID"]},
        ]
        c = db.create_saved_cohort(p["id"], "India Android", filters)
        retrieved = db.get_saved_cohort(c["id"])

        assert retrieved["name"] == "India Android"
        assert len(retrieved["filters"]) == 2
        assert retrieved["filters"][0]["values"] == ["IN"]
        assert retrieved["filters"][1]["field"] == "platform"

    def test_update(self, temp_home):
        from app import db
        p = db.create_profile("P", "x", "y")
        c = db.create_saved_cohort(p["id"], "v1", [
            {"field": "geo.country", "field_type": "column",
             "operator": "equals", "values": ["IN"]}
        ])
        new_filters = [
            {"field": "geo.country", "field_type": "column",
             "operator": "in", "values": ["IN", "US"]}
        ]
        updated = db.update_saved_cohort(c["id"], "v2", new_filters)
        assert updated["name"] == "v2"
        assert updated["filters"][0]["operator"] == "in"
        assert "US" in updated["filters"][0]["values"]

    def test_delete(self, temp_home):
        from app import db
        p = db.create_profile("P", "x", "y")
        c = db.create_saved_cohort(p["id"], "x", [
            {"field": "platform", "field_type": "column",
             "operator": "equals", "values": ["ANDROID"]}
        ])
        assert db.delete_saved_cohort(c["id"]) is True
        assert db.get_saved_cohort(c["id"]) is None

    def test_cascade_delete_with_profile(self, temp_home):
        """Deleting a profile should remove its saved cohorts."""
        from app import db
        p = db.create_profile("P", "x", "y")
        c = db.create_saved_cohort(p["id"], "x", [
            {"field": "platform", "field_type": "column",
             "operator": "equals", "values": ["ANDROID"]}
        ])
        assert db.get_saved_cohort(c["id"]) is not None

        db.delete_profile(p["id"])
        assert db.get_saved_cohort(c["id"]) is None

    def test_unique_name_per_profile(self, temp_home):
        """Two cohorts in same profile cannot share a name."""
        import pytest
        from app import db
        p = db.create_profile("P", "x", "y")
        db.create_saved_cohort(p["id"], "MyName", [
            {"field": "platform", "field_type": "column",
             "operator": "equals", "values": ["ANDROID"]}
        ])
        with pytest.raises(Exception):  # IntegrityError
            db.create_saved_cohort(p["id"], "MyName", [
                {"field": "platform", "field_type": "column",
                 "operator": "equals", "values": ["IOS"]}
            ])

    def test_same_name_ok_across_profiles(self, temp_home):
        """Two profiles can each have a cohort with the same name."""
        from app import db
        p1 = db.create_profile("P1", "x", "y")
        p2 = db.create_profile("P2", "x2", "y2")
        c1 = db.create_saved_cohort(p1["id"], "MyCohort", [
            {"field": "platform", "field_type": "column",
             "operator": "equals", "values": ["ANDROID"]}
        ])
        c2 = db.create_saved_cohort(p2["id"], "MyCohort", [
            {"field": "platform", "field_type": "column",
             "operator": "equals", "values": ["IOS"]}
        ])
        assert c1["id"] != c2["id"]
        assert c1["name"] == c2["name"] == "MyCohort"
