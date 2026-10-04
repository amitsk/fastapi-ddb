"""The routes for the resort-wide partition: its days and its rider rankings.

There is no ``{lift}`` here. The partition key is always ``Resort Data``, which
the service supplies, so a path cannot reach another lift's data and no resort
guard is needed. As in ``app/routes/lifts.py`` the handlers stay thin: each one
pulls the service off the request's app and returns the model it gets back, so
nothing below this layer knows about HTTP.

A ``{date}`` path parameter is declared with ``Annotated`` rather than as a
default value, for the ``B008`` reason spelled out in the lift routes: the
pattern lives in the annotation and the value in the path.

The two list responses set ``response_model_exclude_none=True`` so a page with no
``LastEvaluatedKey`` carries no ``nextToken`` key at all.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response

from app.schemas.skilifts import (
    DATE_PATTERN,
    RankingPage,
    ResortDayPatch,
    ResortDayRead,
    ResortDayWrite,
    ResortPage,
)
from app.services.skilifts import SkiLiftService

router = APIRouter(prefix="/resort", tags=["resort"])

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


@router.put("/days/{date}", response_model=ResortDayRead)
def put_resort_day(request: Request, date: Date, body: ResortDayWrite) -> ResortDayRead:
    """Write one resort-wide day, replacing whatever was stored there.

    ``OpenLifts`` is a DynamoDB number set, so the table collapses duplicates and
    stores the numbers in ascending order, while the service echoes back the body
    it was handed. Reading the item back is what makes this answer agree with a
    ``GET`` of the day just written, so a caller never has to guess which of the
    two shapes a write returned.
    """
    service = _service(request)
    service.put_resort_day(date, body)
    return service.get_resort_day(date)


@router.get("/days/{date}", response_model=ResortDayRead)
def get_resort_day(request: Request, date: Date) -> ResortDayRead:
    """Read one resort-wide day."""
    return _service(request).get_resort_day(date)


@router.patch("/days/{date}", response_model=ResortDayRead)
def patch_resort_day(
    request: Request, date: Date, body: ResortDayPatch
) -> ResortDayRead:
    """Update only the sent fields of one resort-wide day."""
    return _service(request).patch_resort_day(date, body)


@router.delete("/days/{date}", status_code=204)
def delete_resort_day(request: Request, date: Date) -> Response:
    """Delete one resort-wide day, answering 204 with no body."""
    _service(request).delete_resort_day(date)
    return Response(status_code=204)


@router.get(
    "/days",
    response_model=ResortPage,
    response_model_exclude_none=True,
)
def list_resort_days(
    request: Request,
    limit: Annotated[Limit, Query()] = DEFAULT_LIMIT,
    next_token: NextToken = None,
) -> ResortPage:
    """Read one page of the resort partition in sort key order."""
    return _service(request).list_resort_days(limit, next_token)


@router.get(
    "/rankings",
    response_model=RankingPage,
    response_model_exclude_none=True,
)
def list_resort_rankings(
    request: Request,
    limit: Annotated[Limit, Query()] = DEFAULT_LIMIT,
    next_token: NextToken = None,
) -> RankingPage:
    """Read one page of the resort's rider rankings, highest count first."""
    return _service(request).list_resort_rankings(limit, next_token)
