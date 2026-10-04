"""Tests for the service layer: key routing, error mapping, and conversions."""

from decimal import Decimal

import pytest

from app.schemas.skilifts import LiftDayPatch, ProfileWrite
from app.services.skilifts import (
    RESORT_LIFT,
    BadRequest,
    NotFound,
    SkiLiftService,
    UnreadableItem,
)


class FakeRepo:
    """A repository stand-in that records only what the service asked of it.

    Every call lands in ``calls`` as ``(name, *arguments)``, so a test can assert
    both what the service sent and that it sent nothing at all.
    """

    def __init__(self, item: dict | None = None) -> None:
        self.item = item
        self.updated = False
        self.calls: list[tuple] = []

    def get_item(self, lift: str, metadata: str) -> dict | None:
        self.calls.append(("get_item", lift, metadata))
        return self.item

    def update_item(self, lift: str, metadata: str, fields: dict) -> dict | None:
        self.calls.append(("update_item", lift, metadata, dict(fields)))
        self.updated = True
        return self.item

    def put_item(self, item: dict) -> None:
        self.calls.append(("put_item", dict(item)))
        self.item = item

    def delete_item(self, lift: str, metadata: str) -> bool:
        self.calls.append(("delete_item", lift, metadata))
        return self.item is not None

    def query_partition(
        self, lift: str, limit: int, start_key: dict | None
    ) -> tuple[list[dict], dict | None]:
        self.calls.append(("query_partition", lift, limit, start_key))
        return [], None

    def query_rankings(
        self, lift: str, limit: int, start_key: dict | None
    ) -> tuple[list[dict], dict | None]:
        self.calls.append(("query_rankings", lift, limit, start_key))
        return [], None


def test_resort_lift_is_rejected_before_a_write():
    repo = FakeRepo()
    service = SkiLiftService(repo)
    with pytest.raises(BadRequest) as caught:
        service.put_profile(
            RESORT_LIFT,
            ProfileWrite(ExperiencedRidersOnly=False, VerticalFeet=1, LiftTime="7:30"),
        )
    assert caught.value.detail == "Resort Data is served under /resort"
    assert repo.item is None


def test_empty_patch_does_not_call_the_repository():
    repo = FakeRepo()
    service = SkiLiftService(repo)
    with pytest.raises(BadRequest) as caught:
        service.patch_lift_day("Lift 3", "01-01-20", LiftDayPatch())
    assert caught.value.detail == "No fields to update"
    assert repo.updated is False


def test_missing_profile_names_the_profile():
    service = SkiLiftService(FakeRepo())
    with pytest.raises(NotFound) as caught:
        service.get_profile("Lift 3")
    assert caught.value.detail == "Profile not found"


def test_decimal_and_open_lifts_become_sorted_ints():
    item = {
        "Lift": "Resort Data",
        "Metadata": "03/01/20",
        "TotalUniqueLiftRiders": Decimal("6000"),
        "AverageSnowCoverageInches": Decimal("40"),
        "AvalancheDanger": "Low",
        "OpenLifts": {16, 3, 10, 23},
    }
    read = SkiLiftService(FakeRepo(item)).get_resort_day("03-01-20")
    assert read.TotalUniqueLiftRiders == 6000
    assert read.OpenLifts == [3, 10, 16, 23]


def test_fractional_number_is_unreadable():
    item = {
        "Lift": "Lift 3",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": Decimal("1.5"),
        "AverageSnowCoverageInches": Decimal("30"),
        "LiftStatus": "Open",
        "AvalancheDanger": "Low",
    }
    with pytest.raises(UnreadableItem):
        SkiLiftService(FakeRepo(item)).get_lift_day("Lift 3", "01-01-20")
