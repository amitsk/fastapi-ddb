import re

import pytest
from pydantic import ValidationError

from app.sample import ITEMS
from app.schemas.skilifts import (
    DATE_PATTERN,
    LiftDayPatch,
    LiftDayRead,
    LiftDayWrite,
    LiftPage,
    ProfileRead,
    ResortDayWrite,
)


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
