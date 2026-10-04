import re

import pytest
from pydantic import ValidationError

from app.data.sample import ITEMS
from app.schemas.skilifts import (
    DATE_PATTERN,
    LiftDayPatch,
    LiftDayRead,
    LiftDayWrite,
    LiftPage,
    ProfileRead,
    ResortDayPatch,
    ResortDayRead,
    ResortDayWrite,
)

# The three sample tables of the spec, transcribed value by value:
# (Lift, ExperiencedRidersOnly, VerticalFeet, LiftTime).
SPEC_PROFILES = [
    ("Lift 3", False, 1300, "7:30"),
    ("Lift 23", True, 900, "5:45"),
    ("Lift 16", False, 1500, "9:00"),
    ("Lift 10", True, 1000, "6:00"),
]
# (Lift, Metadata, TotalUniqueLiftRiders, AverageSnowCoverageInches, LiftStatus,
# AvalancheDanger).
SPEC_LIFT_DAYS = [
    ("Lift 3", "01/01/20", 5000, 30, "Open", "Low"),
    ("Lift 23", "01/01/20", 1000, 45, "Open", "Considerable"),
    ("Lift 16", "01/01/20", 4500, 35, "Open", "Low"),
    ("Lift 10", "01/01/20", 0, 40, "Pending", "High"),
    ("Lift 3", "02/01/20", 6000, 35, "Open", "Low"),
    ("Lift 23", "02/01/20", 0, 50, "Closed", "Extreme"),
    ("Lift 16", "02/01/20", 5500, 40, "Open", "Low"),
    ("Lift 10", "02/01/20", 3500, 45, "Open", "Moderate"),
    ("Lift 3", "03/01/20", 5500, 35, "Open", "Low"),
    ("Lift 23", "03/01/20", 1500, 45, "Open", "Moderate"),
    ("Lift 16", "03/01/20", 4000, 40, "Open", "Low"),
    ("Lift 10", "03/01/20", 2500, 45, "Open", "Moderate"),
]
# (Metadata, TotalUniqueLiftRiders, AverageSnowCoverageInches, AvalancheDanger,
# OpenLifts) in the written order of the table, which is not sorted.
SPEC_RESORT_DAYS = [
    ("01/01/20", 5500, 35, "Considerable", [3, 23, 16]),
    ("02/01/20", 6500, 45, "Moderate", [3, 16, 10]),
    ("03/01/20", 6000, 40, "Low", [3, 23, 16, 10]),
]


def test_sample_has_the_nineteen_spec_items():
    assert len(ITEMS) == 19
    profile = next(
        item
        for item in ITEMS
        if item["Lift"] == "Lift 3" and item["Metadata"] == "Static Data"
    )
    assert ProfileRead.model_validate(profile).VerticalFeet == 1300
    day = next(
        item
        for item in ITEMS
        if item["Lift"] == "Lift 3" and item["Metadata"] == "01/01/20"
    )
    assert LiftDayRead.model_validate(day).TotalUniqueLiftRiders == 5000
    resort = next(
        item
        for item in ITEMS
        if item["Lift"] == "Resort Data" and item["Metadata"] == "03/01/20"
    )
    assert resort["OpenLifts"] == [3, 23, 16, 10]


def test_date_pattern_accepts_an_impossible_calendar_day():
    assert re.fullmatch(DATE_PATTERN, "02-31-20")
    assert re.fullmatch(DATE_PATTERN, "13-01-20") is None


def test_write_models_reject_bad_facet_values():
    with pytest.raises(ValidationError) as extra:
        LiftDayWrite.model_validate(
            {
                "TotalUniqueLiftRiders": 1,
                "AverageSnowCoverageInches": 1,
                "LiftStatus": "Open",
                "AvalancheDanger": "Low",
                "Nope": 1,
            }
        )
    assert extra.value.errors()[0]["loc"] == ("Nope",)
    with pytest.raises(ValidationError) as riders:
        LiftDayWrite(
            TotalUniqueLiftRiders=1.5,
            AverageSnowCoverageInches=1,
            LiftStatus="Open",
            AvalancheDanger="Low",
        )
    assert any(
        err["loc"] == ("TotalUniqueLiftRiders",) for err in riders.value.errors()
    )
    with pytest.raises(ValidationError) as status:
        LiftDayWrite(
            TotalUniqueLiftRiders=1,
            AverageSnowCoverageInches=1,
            LiftStatus="Shut",
            AvalancheDanger="Low",
        )
    assert any(err["loc"] == ("LiftStatus",) for err in status.value.errors())
    with pytest.raises(ValidationError):
        ResortDayWrite(
            TotalUniqueLiftRiders=1,
            AverageSnowCoverageInches=1,
            AvalancheDanger="Low",
            OpenLifts=[],
        )


def test_patch_model_takes_a_subset_and_still_validates_the_fields():
    patch = LiftDayPatch(LiftStatus="Closed")
    assert patch.model_dump(exclude_unset=True) == {"LiftStatus": "Closed"}
    with pytest.raises(ValidationError) as bad:
        LiftDayPatch(LiftStatus="Shut", Nope=1)
    locs = {err["loc"] for err in bad.value.errors()}
    assert ("LiftStatus",) in locs
    assert ("Nope",) in locs


def test_patch_models_reject_an_explicit_null_and_accept_an_empty_body():
    for body, model in (
        ({"LiftStatus": None}, LiftDayPatch),
        ({"TotalUniqueLiftRiders": None}, LiftDayPatch),
        ({"OpenLifts": None}, ResortDayPatch),
    ):
        with pytest.raises(ValidationError) as null_field:
            model.model_validate(body)
        (field,) = body
        assert null_field.value.errors()[0]["loc"] == (field,)
    assert LiftDayPatch().model_dump(exclude_unset=True) == {}
    assert ResortDayPatch().model_dump(exclude_unset=True) == {}
    # A patch that sets a field still enforces that field's rule.
    with pytest.raises(ValidationError) as negative:
        LiftDayPatch.model_validate({"TotalUniqueLiftRiders": -1})
    assert negative.value.errors()[0]["loc"] == ("TotalUniqueLiftRiders",)


def test_every_sample_item_carries_the_spec_values():
    assert len(ITEMS) == len(SPEC_PROFILES) + len(SPEC_LIFT_DAYS) + len(
        SPEC_RESORT_DAYS
    )
    assert [(item["Lift"], item["Metadata"]) for item in ITEMS] == [
        (lift, "Static Data") for lift, *_ in SPEC_PROFILES
    ] + [(lift, metadata) for lift, metadata, *_ in SPEC_LIFT_DAYS] + [
        ("Resort Data", metadata) for metadata, *_ in SPEC_RESORT_DAYS
    ]
    assert [
        (
            item["Lift"],
            item["ExperiencedRidersOnly"],
            item["VerticalFeet"],
            item["LiftTime"],
        )
        for item in ITEMS
        if item["Metadata"] == "Static Data"
    ] == SPEC_PROFILES
    assert [
        (
            item["Lift"],
            item["Metadata"],
            item["TotalUniqueLiftRiders"],
            item["AverageSnowCoverageInches"],
            item["LiftStatus"],
            item["AvalancheDanger"],
        )
        for item in ITEMS
        if item["Metadata"] != "Static Data" and item["Lift"] != "Resort Data"
    ] == SPEC_LIFT_DAYS
    assert [
        (
            item["Metadata"],
            item["TotalUniqueLiftRiders"],
            item["AverageSnowCoverageInches"],
            item["AvalancheDanger"],
            item["OpenLifts"],
        )
        for item in ITEMS
        if item["Lift"] == "Resort Data"
    ] == SPEC_RESORT_DAYS


def test_every_sample_item_validates_as_its_kind():
    for item in ITEMS:
        if item["Metadata"] == "Static Data":
            model = ProfileRead
        elif item["Lift"] == "Resort Data":
            model = ResortDayRead
        else:
            model = LiftDayRead
        # extra="forbid" makes this fail on an unknown or missing attribute too.
        assert model.model_validate(item).model_dump() == item


def test_page_serializes_the_next_token_alias_and_omits_a_missing_token():
    day = next(
        item
        for item in ITEMS
        if item["Lift"] == "Lift 3" and item["Metadata"] == "01/01/20"
    )
    last_page = LiftPage.model_validate(
        {"items": [day], "count": 1, "next_token": "abc"}
    )
    assert last_page.model_dump(by_alias=True) == {
        "count": 1,
        "nextToken": "abc",
        "items": [dict(day)],
    }
    last_page = LiftPage(items=[LiftDayRead.model_validate(day)], count=1)
    assert last_page.model_dump(by_alias=True) == {"count": 1, "items": [dict(day)]}
