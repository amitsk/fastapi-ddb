"""Request and response models for the SkiLifts API.

Read models keep the table's PascalCase attribute names because those names are
the DynamoDB attributes and the JSON contract. Write models carry facet fields
only: the keys come from the path and are echoed in the response.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# A ``{date}`` path segment: month 01-12, day 01-31, two-digit year. The pattern
# deliberately does not reject impossible calendar days such as ``02-31-20``.
DATE_PATTERN = r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])-[0-9]{2}$"

LIFT_TIME_PATTERN = r"^\d{1,2}:\d{2}$"


class LiftStatus(StrEnum):
    """Whether a lift is running, closed, or not yet decided for the day."""

    OPEN = "Open"
    CLOSED = "Closed"
    PENDING = "Pending"


class AvalancheDanger(StrEnum):
    """The day's avalanche danger rating."""

    LOW = "Low"
    MODERATE = "Moderate"
    CONSIDERABLE = "Considerable"
    HIGH = "High"
    EXTREME = "Extreme"


# The reusable field types below are suffixed with ``Type`` where a field shares
# the name of its own type: PEP 649 resolves a field annotation after the class
# body has run, so a bare name would then resolve to the field's value.
RidersType = Annotated[int, Field(ge=0)]
SnowInchesType = Annotated[int, Field(ge=0)]
VerticalType = Annotated[int, Field(ge=1)]
LiftTimeType = Annotated[str, Field(pattern=LIFT_TIME_PATTERN)]
# A number set collapses duplicates and DynamoDB rejects an empty one.
OpenLiftsType = Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=1)]
LiftStatusType = LiftStatus
AvalancheDangerType = AvalancheDanger


class DomainModel(BaseModel):
    """Base model: bodies forbid extra fields and reject unknown attributes."""

    model_config = ConfigDict(extra="forbid")


class ProfileWrite(DomainModel):
    """Body for ``PUT /lifts/{lift}/profile``."""

    ExperiencedRidersOnly: bool
    VerticalFeet: VerticalType
    LiftTime: LiftTimeType


class ProfileRead(ProfileWrite):
    """A stored profile, with its keys."""

    Lift: str
    Metadata: str


class LiftDayWrite(DomainModel):
    """Body for ``PUT /lifts/{lift}/days/{date}``."""

    TotalUniqueLiftRiders: RidersType
    AverageSnowCoverageInches: SnowInchesType
    LiftStatus: LiftStatusType
    AvalancheDanger: AvalancheDangerType


class LiftDayPatch(DomainModel):
    """Body for ``PATCH /lifts/{lift}/days/{date}``: any subset of the facets."""

    TotalUniqueLiftRiders: RidersType | None = None
    AverageSnowCoverageInches: SnowInchesType | None = None
    LiftStatus: LiftStatusType | None = None
    AvalancheDanger: AvalancheDangerType | None = None


class LiftDayRead(LiftDayWrite):
    """A stored lift day, with its keys."""

    Lift: str
    Metadata: str


class ResortDayWrite(DomainModel):
    """Body for ``PUT /resort/days/{date}``."""

    TotalUniqueLiftRiders: RidersType
    AverageSnowCoverageInches: SnowInchesType
    AvalancheDanger: AvalancheDangerType
    OpenLifts: OpenLiftsType


class ResortDayPatch(DomainModel):
    """Body for ``PATCH /resort/days/{date}``: any subset of the facets."""

    TotalUniqueLiftRiders: RidersType | None = None
    AverageSnowCoverageInches: SnowInchesType | None = None
    AvalancheDanger: AvalancheDangerType | None = None
    OpenLifts: OpenLiftsType | None = None


class ResortDayRead(ResortDayWrite):
    """A stored resort day, with its keys."""

    Lift: str
    Metadata: str


class RankingRead(DomainModel):
    """A row of a rankings page: the lift, the date, and its rider count."""

    Lift: str
    Metadata: str
    TotalUniqueLiftRiders: RidersType


class Page(DomainModel):
    """Shared shape of a list response."""

    count: int
    # Present only when DynamoDB returns a LastEvaluatedKey.
    next_token: Annotated[
        str | None,
        Field(serialization_alias="nextToken", exclude_if=lambda token: token is None),
    ] = None


class LiftPage(Page):
    """A page of profiles and lift days from one lift partition."""

    items: list[ProfileRead | LiftDayRead]


class ResortPage(Page):
    """A page of resort days from the ``Resort Data`` partition."""

    items: list[ResortDayRead]


class RankingPage(Page):
    """A page of rankings, highest rider count first."""

    items: list[RankingRead]
