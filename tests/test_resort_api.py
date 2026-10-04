"""Tests for the resort routes: spec bodies, statuses, ordering, and errors.

Every test runs against a fresh moto table seeded with ``app.sample.ITEMS`` and
built by the ``client`` fixture, so the assertions read as the spec does.
"""


def test_resort_day_and_sorted_open_lifts(client):
    day = client.get("/resort/days/03-01-20")
    assert day.status_code == 200
    assert day.json() == {
        "Lift": "Resort Data",
        "Metadata": "03/01/20",
        "TotalUniqueLiftRiders": 6000,
        "AverageSnowCoverageInches": 40,
        "AvalancheDanger": "Low",
        "OpenLifts": [3, 10, 16, 23],
    }
    patched = client.patch("/resort/days/03-01-20", json={"AvalancheDanger": "High"})
    assert patched.status_code == 200
    assert patched.json()["AvalancheDanger"] == "High"
    assert patched.json()["TotalUniqueLiftRiders"] == 6000
    assert patched.json()["AverageSnowCoverageInches"] == 40
    assert patched.json()["OpenLifts"] == [3, 10, 16, 23]
    created = client.put(
        "/resort/days/04-01-20",
        json={
            "TotalUniqueLiftRiders": 10,
            "AverageSnowCoverageInches": 2,
            "AvalancheDanger": "Low",
            "OpenLifts": [3, 3, 10],
        },
    )
    assert created.status_code == 200
    assert created.json()["OpenLifts"] == [3, 10]
    replaced = client.put(
        "/resort/days/04-01-20",
        json={
            "TotalUniqueLiftRiders": 11,
            "AverageSnowCoverageInches": 2,
            "AvalancheDanger": "High",
            "OpenLifts": [1],
        },
    )
    assert replaced.json()["TotalUniqueLiftRiders"] == 11
    assert replaced.json()["AvalancheDanger"] == "High"


def test_resort_rankings_order_and_pagination(client):
    page = client.get("/resort/rankings")
    assert [
        (item["Metadata"], item["TotalUniqueLiftRiders"])
        for item in page.json()["items"]
    ] == [
        ("02/01/20", 6500),
        ("03/01/20", 6000),
        ("01/01/20", 5500),
    ]
    first = client.get("/resort/rankings", params={"limit": 1})
    second = client.get(
        "/resort/rankings", params={"limit": 1, "nextToken": first.json()["nextToken"]}
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["Metadata"] == "03/01/20"


def test_resort_days_sort_by_metadata(client):
    page = client.get("/resort/days")
    assert [item["Metadata"] for item in page.json()["items"]] == [
        "01/01/20",
        "02/01/20",
        "03/01/20",
    ]


def test_resort_errors(client):
    assert client.get("/resort/days/04-04-20").status_code == 404
    assert client.get("/resort/days/04-04-20").json() == {
        "detail": "Resort day not found"
    }
    assert (
        client.patch(
            "/resort/days/04-04-20", json={"AverageSnowCoverageInches": 1}
        ).status_code
        == 404
    )
    assert client.delete("/resort/days/04-04-20").status_code == 404
    empty = client.patch("/resort/days/01-01-20", json={})
    assert empty.status_code == 400
    assert empty.json() == {"detail": "No fields to update"}
    blank = client.put(
        "/resort/days/05-01-20",
        json={
            "TotalUniqueLiftRiders": 1,
            "AverageSnowCoverageInches": 1,
            "AvalancheDanger": "Low",
            "OpenLifts": [],
        },
    )
    assert blank.status_code == 422
    assert ["body", "OpenLifts"] in [list(err["loc"]) for err in blank.json()["detail"]]
    deleted = client.delete("/resort/days/01-01-20")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get("/resort/days/01-01-20").status_code == 404
