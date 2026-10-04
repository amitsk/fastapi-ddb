"""The routes for one lift's profile, its days, and its rider rankings.

The handlers are deliberately thin. Each one pulls the service off the request's
app, hands it the already-validated path, query and body values, and returns the
model it gets back. The resort partition is refused inside the service, dates are
converted there, and every error becomes a status code in ``app/errors.py``, so
nothing below this layer knows about HTTP.

A path parameter and a query parameter are declared with ``Annotated`` rather than
as a default value: ``limit = Query(20)`` is a call in a default argument, which
flake8-bugbear's ``B008`` rejects, while ``Annotated[int, Query(ge=1, le=100)] = 20``
says the same thing without a workaround.

The three list responses set ``response_model_exclude_none=True`` so a page with no
``LastEvaluatedKey`` carries no ``nextToken`` key at all.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response

from app.schemas.skilifts import (
    DATE_PATTERN,
    LiftDayPatch,
    LiftDayRead,
    LiftDayWrite,
    LiftPage,
    ProfileRead,
    ProfileWrite,
    RankingPage,
)
from app.services.skilifts import SkiLiftService

router = APIRouter(prefix="/lifts", tags=["lifts"])

# A lift name is a partition key: any non-empty path segment.
Lift = Annotated[str, Path(min_length=1)]
# The path form of a day; the service turns it into the stored ``MM/DD/YY``.
Date = Annotated[str, Path(pattern=DATE_PATTERN)]
# Page size and cursor, shared by both list routes.
Limit = Annotated[int, Query(ge=1, le=100)]
# The wire name is camelCase ``nextToken``; the Python name stays snake_case.
NextToken = Annotated[str | None, Query(alias="nextToken")]
DEFAULT_LIMIT = 20


def _service(request: Request) -> SkiLiftService:
    """Return the service the app's lifespan built."""
    return request.app.state.service


@router.put("/{lift}/profile", response_model=ProfileRead)
def put_profile(request: Request, lift: Lift, body: ProfileWrite) -> ProfileRead:
    """Write a lift's profile, replacing whatever was stored there."""
    return _service(request).put_profile(lift, body)


@router.get("/{lift}/profile", response_model=ProfileRead)
def get_profile(request: Request, lift: Lift) -> ProfileRead:
    """Read a lift's profile."""
    return _service(request).get_profile(lift)


@router.put("/{lift}/days/{date}", response_model=LiftDayRead)
def put_lift_day(
    request: Request, lift: Lift, date: Date, body: LiftDayWrite
) -> LiftDayRead:
    """Write one day of a lift, replacing whatever was stored there."""
    return _service(request).put_lift_day(lift, date, body)


@router.get("/{lift}/days/{date}", response_model=LiftDayRead)
def get_lift_day(request: Request, lift: Lift, date: Date) -> LiftDayRead:
    """Read one day of a lift."""
    return _service(request).get_lift_day(lift, date)


@router.patch("/{lift}/days/{date}", response_model=LiftDayRead)
def patch_lift_day(
    request: Request, lift: Lift, date: Date, body: LiftDayPatch
) -> LiftDayRead:
    """Update only the sent fields of one lift day."""
    return _service(request).patch_lift_day(lift, date, body)


@router.delete("/{lift}/days/{date}", status_code=204)
def delete_lift_day(request: Request, lift: Lift, date: Date) -> Response:
    """Delete one day of a lift, answering 204 with no body."""
    _service(request).delete_lift_day(lift, date)
    return Response(status_code=204)


@router.get(
    "/{lift}",
    response_model=LiftPage,
    response_model_exclude_none=True,
)
def list_lift(
    request: Request,
    lift: Lift,
    limit: Annotated[Limit, Query()] = DEFAULT_LIMIT,
    next_token: NextToken = None,
) -> LiftPage:
    """Read one page of a lift partition in sort key order."""
    return _service(request).list_lift(lift, limit, next_token)


@router.get(
    "/{lift}/rankings",
    response_model=RankingPage,
    response_model_exclude_none=True,
)
def list_lift_rankings(
    request: Request,
    lift: Lift,
    limit: Annotated[Limit, Query()] = DEFAULT_LIMIT,
    next_token: NextToken = None,
) -> RankingPage:
    """Read one page of a lift's rider rankings, highest count first."""
    return _service(request).list_lift_rankings(lift, limit, next_token)
