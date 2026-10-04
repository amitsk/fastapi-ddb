"""Tests for the lift routes: spec bodies, statuses, ordering, and errors.

Every test runs against a fresh moto table seeded with ``app.sample.ITEMS`` and
built by the ``client`` fixture, so the assertions read as the spec does.
"""

from app.config import Settings
from app.db import dynamodb_resource
from app.repositories.skilifts import SkiLiftRepository


def test_get_profile_and_day(client):
    profile = client.get("/lifts/Lift%203/profile")
    assert profile.status_code == 200
    assert profile.json() == {
        "Lift": "Lift 3",
        "Metadata": "Static Data",
        "ExperiencedRidersOnly": False,
        "VerticalFeet": 1300,
        "LiftTime": "7:30",
    }
    day = client.get("/lifts/Lift%203/days/01-01-20")
    assert day.status_code == 200
    assert day.json() == {
        "Lift": "Lift 3",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": 5000,
        "AverageSnowCoverageInches": 30,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    }
    assert isinstance(day.json()["TotalUniqueLiftRiders"], int)
    assert "5000.0" not in day.text
    assert (
        client.get("/lifts/Lift%2010/days/01-01-20").json()["TotalUniqueLiftRiders"]
        == 0
    )


def test_put_lift_day_replaces(client):
    body = {
        "TotalUniqueLiftRiders": 1,
        "AverageSnowCoverageInches": 2,
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    }
    created = client.put("/lifts/New%20Lift/days/01-02-20", json=body)
    assert created.status_code == 200
    replaced = client.put(
        "/lifts/New%20Lift/days/01-02-20",
        json={**body, "LiftStatus": "Closed", "TotalUniqueLiftRiders": 9},
    )
    assert replaced.status_code == 200
    assert replaced.json()["LiftStatus"] == "Closed"
    assert replaced.json()["TotalUniqueLiftRiders"] == 9
    assert (
        client.get("/lifts/New%20Lift/days/01-02-20").json()["LiftStatus"] == "Closed"
    )


def test_put_profile_replaces(client):
    created = client.put(
        "/lifts/New%20Lift/profile",
        json={"ExperiencedRidersOnly": False, "VerticalFeet": 100, "LiftTime": "4:00"},
    )
    assert created.status_code == 200
    replaced = client.put(
        "/lifts/New%20Lift/profile",
        json={"ExperiencedRidersOnly": True, "VerticalFeet": 200, "LiftTime": "5:00"},
    )
    assert replaced.status_code == 200
    assert client.get("/lifts/New%20Lift/profile").json()["VerticalFeet"] == 200


def test_lift_partition_order_and_rankings_omit_profile(client):
    page = client.get("/lifts/Lift%203")
    assert [item["Metadata"] for item in page.json()["items"]] == [
        "01/01/20",
        "02/01/20",
        "03/01/20",
        "Static Data",
    ]
    assert "nextToken" not in page.json()
    rankings = client.get("/lifts/Lift%203/rankings")
    assert [
        (item["Metadata"], item["TotalUniqueLiftRiders"])
        for item in rankings.json()["items"]
    ] == [
        ("02/01/20", 6000),
        ("03/01/20", 5500),
        ("01/01/20", 5000),
    ]


def test_unknown_lift_is_an_empty_page(client):
    response = client.get("/lifts/No%20Such")
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}
    assert "nextToken" not in response.json()


def test_limit_one_paginates_without_repeating(client):
    first = client.get("/lifts/Lift%203", params={"limit": 1})
    assert first.json()["count"] == 1
    assert first.json()["items"][0]["Metadata"] == "01/01/20"
    second = client.get(
        "/lifts/Lift%203", params={"limit": 1, "nextToken": first.json()["nextToken"]}
    )
    assert second.json()["items"][0]["Metadata"] == "02/01/20"


def test_limit_defaults_to_20(client):
    for day in range(1, 22):
        response = client.put(
            f"/lifts/Limit%20Lift/days/01-{day:02d}-20",
            json={
                "TotalUniqueLiftRiders": day,
                "AverageSnowCoverageInches": 1,
                "LiftStatus": "Open",
                "AvalancheDanger": "Low",
            },
        )
        assert response.status_code == 200
    page = client.get("/lifts/Limit%20Lift")
    assert page.json()["count"] == 20
    assert "nextToken" in page.json()


def test_patch_one_field_preserves_the_others_and_reorders_rankings(client):
    patched = client.patch(
        "/lifts/Lift%203/days/01-01-20", json={"LiftStatus": "Closed"}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["LiftStatus"] == "Closed"
    assert body["TotalUniqueLiftRiders"] == 5000
    assert body["AverageSnowCoverageInches"] == 30
    assert body["AvalancheDanger"] == "Low"
    moved = client.patch(
        "/lifts/Lift%2023/days/02-01-20", json={"TotalUniqueLiftRiders": 2000}
    )
    assert moved.status_code == 200
    rankings = client.get("/lifts/Lift%2023/rankings")
    assert [
        (item["Metadata"], item["TotalUniqueLiftRiders"])
        for item in rankings.json()["items"]
    ] == [
        ("02/01/20", 2000),
        ("03/01/20", 1500),
        ("01/01/20", 1000),
    ]


def test_lift_errors(client):
    assert client.get("/lifts/Resort%20Data/profile").json() == {
        "detail": "Resort Data is served under /resort"
    }
    assert client.get("/lifts/Resort%20Data/profile").status_code == 400
    assert client.patch("/lifts/Lift%203/days/01-01-20", json={}).status_code == 400
    assert (
        client.patch("/lifts/Lift%203/days/01-01-20", json={}).json()["detail"]
        == "No fields to update"
    )
    missing = client.get("/lifts/Lift%203/days/04-01-20")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Day not found"}
    assert client.get("/lifts/Lift%203/profile").status_code == 200
    assert client.get("/lifts/Missing/profile").status_code == 404
    assert client.get("/lifts/Missing/profile").json() == {
        "detail": "Profile not found"
    }
    assert (
        client.patch(
            "/lifts/Lift%203/days/04-01-20", json={"LiftStatus": "Open"}
        ).status_code
        == 404
    )
    assert client.delete("/lifts/Lift%203/days/04-01-20").status_code == 404
    deleted = client.delete("/lifts/Lift%203/days/02-01-20")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get("/lifts/Lift%203/days/02-01-20").status_code == 404
    assert all(
        item["Metadata"] != "02/01/20"
        for item in client.get("/lifts/Lift%203/rankings").json()["items"]
    )
    assert (
        client.patch("/lifts/Lift%203/profile", json={"VerticalFeet": 1}).status_code
        == 405
    )
    assert client.delete("/lifts/Lift%203/profile").status_code == 405
    feet = client.put(
        "/lifts/Lift%203/profile",
        json={"ExperiencedRidersOnly": False, "VerticalFeet": 0, "LiftTime": "7:30"},
    )
    assert feet.status_code == 422
    assert ["body", "VerticalFeet"] in [
        list(err["loc"]) for err in feet.json()["detail"]
    ]


def test_lift_validation_locs(client):
    extra = client.put(
        "/lifts/Lift%203/profile",
        json={
            "ExperiencedRidersOnly": False,
            "VerticalFeet": 1,
            "LiftTime": "7:30",
            "Nope": 1,
        },
    )
    assert extra.status_code == 422
    assert ["body", "Nope"] in [list(err["loc"]) for err in extra.json()["detail"]]
    fractional = client.put(
        "/lifts/Lift%203/days/01-01-20",
        json={
            "TotalUniqueLiftRiders": 1.5,
            "AverageSnowCoverageInches": 1,
            "LiftStatus": "Open",
            "AvalancheDanger": "Low",
        },
    )
    assert ["body", "TotalUniqueLiftRiders"] in [
        list(err["loc"]) for err in fractional.json()["detail"]
    ]
    status = client.put(
        "/lifts/Lift%203/days/01-01-20",
        json={
            "TotalUniqueLiftRiders": 1,
            "AverageSnowCoverageInches": 1,
            "LiftStatus": "Shut",
            "AvalancheDanger": "Low",
        },
    )
    assert ["body", "LiftStatus"] in [
        list(err["loc"]) for err in status.json()["detail"]
    ]
    bad_date = client.get("/lifts/Lift%203/days/13-01-20")
    assert bad_date.status_code == 422
    assert ["path", "date"] in [list(err["loc"]) for err in bad_date.json()["detail"]]
    bad_limit = client.get("/lifts/Lift%203", params={"limit": 101})
    assert bad_limit.status_code == 422
    assert ["query", "limit"] in [
        list(err["loc"]) for err in bad_limit.json()["detail"]
    ]
    impossible = client.put(
        "/lifts/Lift%203/days/02-31-20",
        json={
            "TotalUniqueLiftRiders": 1,
            "AverageSnowCoverageInches": 1,
            "LiftStatus": "Open",
            "AvalancheDanger": "Low",
        },
    )
    assert impossible.status_code == 200
    assert impossible.json()["Metadata"] == "02/31/20"


def test_bad_tokens(client):
    ranking = client.get("/lifts/Lift%203/rankings", params={"limit": 1}).json()[
        "nextToken"
    ]
    wrong_route = client.get("/lifts/Lift%203", params={"nextToken": ranking})
    assert wrong_route.status_code == 400
    assert wrong_route.json() == {"detail": "Invalid nextToken"}
    table = client.get("/lifts/Lift%203", params={"limit": 1}).json()["nextToken"]
    wrong_lift = client.get("/lifts/Lift%2010", params={"nextToken": table})
    assert wrong_lift.status_code == 400
    malformed = client.get("/lifts/Lift%203", params={"nextToken": "%%%"})
    assert malformed.status_code == 400


def test_unreadable_stored_day_is_internal_error(client):
    settings = Settings()
    repo = SkiLiftRepository(
        dynamodb_resource(settings).Table(settings.dynamodb_table_name)
    )
    repo.put_item(
        {"Lift": "Lift 3", "Metadata": "04/01/20", "TotalUniqueLiftRiders": 1}
    )
    response = client.get("/lifts/Lift%203/days/04-01-20")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "TotalUniqueLiftRiders" not in response.text


def test_docs_are_served(client):
    assert client.get("/docs").status_code == 200
