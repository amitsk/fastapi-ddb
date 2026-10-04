"""Sentinel keys, date conversion, pagination tokens, domain errors, and the service.

The service layer knows the table's sentinels and the wire format of a
``nextToken``; it knows nothing about HTTP status codes, which ``app/errors.py``
maps from the errors raised here. ``SkiLiftService`` turns the models of a route
into repository calls and back again: it routes the resort partition away from
the lift routes, converts path dates and stored numbers, and raises the domain
errors the routes map to status codes.
"""

import base64
import json
from decimal import Decimal

from pydantic import BaseModel, ValidationError

# ``app.db`` creates the index, so it owns the name and the service re-exports it
# rather than defining a second literal. The alias is the re-export marker.
from app.db import GSI_NAME as GSI_NAME  # noqa: PLC0414
from app.repositories.skilifts import SkiLiftRepository
from app.schemas.skilifts import (
    LiftDayPatch,
    LiftDayRead,
    LiftDayWrite,
    LiftPage,
    ProfileRead,
    ProfileWrite,
    RankingPage,
    RankingRead,
    ResortDayPatch,
    ResortDayRead,
    ResortDayWrite,
    ResortPage,
)

# Sentinel values the routes and the repository branch on.
STATIC_METADATA = "Static Data"
RESORT_LIFT = "Resort Data"

# The exact key set a token must carry for each paginated route.
TABLE_TOKEN_KEYS = frozenset({"Lift", "Metadata"})
RANKING_TOKEN_KEYS = frozenset({"Lift", "Metadata", "TotalUniqueLiftRiders"})


# N818 wants an ``Error`` suffix on exception names, but the spec fixes the names
# below; the noqa on each class is the only way to keep them.
class NotFound(Exception):  # noqa: N818
    """The requested item does not exist."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BadRequest(Exception):  # noqa: N818
    """The request cannot be served as sent."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidToken(BadRequest):
    """A ``nextToken`` is absent, malformed, or not for this route."""

    def __init__(self, detail: str = "Invalid nextToken") -> None:
        super().__init__(detail)


class UnreadableItem(Exception):  # noqa: N818
    """A stored item cannot be parsed as the kind the route expects."""


def path_date_to_metadata(date: str) -> str:
    """Turn a ``01-01-20`` path segment into the stored ``01/01/20`` sort key."""
    return date.replace("-", "/")


def encode_token(key: dict[str, str | int]) -> str:
    """Encode a ``LastEvaluatedKey`` as unpadded base64url of canonical JSON.

    Keys are sorted and separators are compact, so the same key always encodes to
    the same token.
    """
    payload = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_token(
    token: str, *, expected_keys: frozenset[str], lift: str
) -> dict[str, str | int]:
    """Decode a ``nextToken`` into a ``LastEvaluatedKey`` for this route.

    The token is only accepted when it is canonical base64url of a JSON object
    whose keys are exactly ``expected_keys``, whose string keys hold strings,
    whose rider count is a JSON integer, and whose ``Lift`` is the partition being
    queried. Anything else raises ``InvalidToken``.
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
    except ValueError:  # covers binascii.Error, UnicodeDecodeError, JSONDecodeError
        raise InvalidToken from None
    if not isinstance(decoded, dict) or frozenset(decoded) != expected_keys:
        raise InvalidToken
    token_key: dict[str, str | int] = {}
    for name, value in decoded.items():
        if name in ("Lift", "Metadata"):
            if not isinstance(value, str):
                raise InvalidToken
        elif isinstance(value, bool) or not isinstance(value, int):
            raise InvalidToken
        token_key[name] = value
    if token_key["Lift"] != lift:
        raise InvalidToken
    return token_key


def _as_int(value: object) -> object:
    """Return a whole ``Decimal`` as ``int`` and leave every other value alone.

    A fractional number is left as a ``Decimal`` on purpose: the read model then
    refuses it and the item becomes ``UnreadableItem``.
    """
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return value


def _parse[ModelT: BaseModel](item: dict, model: type[ModelT]) -> ModelT:
    """Build a read model from a stored item.

    boto3 hands every number back as a ``Decimal`` and a number set as an
    unordered ``set`` of them, so both are converted here: whole numbers become
    ``int`` and ``OpenLifts`` becomes a list sorted ascending. A missing required
    field, an unexpected attribute, or a fractional number fails validation and
    becomes ``UnreadableItem``.
    """
    attributes: dict[str, object] = {
        name: _as_int(value) for name, value in item.items()
    }
    open_lifts = attributes.get("OpenLifts")
    if isinstance(open_lifts, (set, frozenset)):
        # A number set holds only numbers, so they order among themselves; the
        # sort runs before the conversion and a fractional member stays a
        # ``Decimal`` to be rejected by the model below.
        numbers: list[Decimal] = sorted(open_lifts)
        attributes["OpenLifts"] = [_as_int(number) for number in numbers]
    try:
        return model.model_validate(attributes)
    except ValidationError as error:
        raise UnreadableItem(f"{item.get('Metadata')} cannot be read") from error


def _start_key(
    token: str | None, expected_keys: frozenset[str], lift: str
) -> dict[str, str | int] | None:
    """Decode a ``nextToken`` into a start key, or ``None`` when none was sent.

    ``decode_token`` needs a token to work on, so an absent one never reaches it.
    """
    if token is None:
        return None
    return decode_token(token, expected_keys=expected_keys, lift=lift)


def _next_token(last_key: dict | None) -> str | None:
    """Encode a ``LastEvaluatedKey`` as a token, or ``None`` on a last page.

    A start key comes back with its numbers as ``Decimal``, which is not JSON, so
    the rider count is converted to ``int``.
    """
    if last_key is None:
        return None
    return encode_token(
        {
            name: value if isinstance(value, str) else int(value)
            for name, value in last_key.items()
        }
    )


class SkiLiftService:
    """The SkiLifts use cases, from a validated body to a stored item and back.

    The resort partition is not reachable through the lift routes: every method
    that takes a lift checks it first. Reads convert what boto3 stored into what
    the response models expect, and every failure of that conversion is an
    ``UnreadableItem`` rather than a wrong answer.
    """

    def __init__(self, repo: SkiLiftRepository) -> None:
        self._repo = repo

    @staticmethod
    def _reject_resort(lift: str) -> None:
        """Refuse the resort partition on a lift route, before any repository call."""
        if lift == RESORT_LIFT:
            raise BadRequest("Resort Data is served under /resort")

    def put_profile(self, lift: str, body: ProfileWrite) -> ProfileRead:
        """Write the profile of a lift, replacing whatever was stored there."""
        self._reject_resort(lift)
        item = {
            "Lift": lift,
            "Metadata": STATIC_METADATA,
            **body.model_dump(mode="json"),
        }
        self._repo.put_item(item)
        return _parse(item, ProfileRead)

    def get_profile(self, lift: str) -> ProfileRead:
        """Read the profile of a lift."""
        self._reject_resort(lift)
        item = self._repo.get_item(lift, STATIC_METADATA)
        if item is None:
            raise NotFound("Profile not found")
        return _parse(item, ProfileRead)

    def put_lift_day(self, lift: str, date: str, body: LiftDayWrite) -> LiftDayRead:
        """Write one day of a lift, replacing whatever was stored there."""
        self._reject_resort(lift)
        item = {
            "Lift": lift,
            "Metadata": path_date_to_metadata(date),
            **body.model_dump(mode="json"),
        }
        self._repo.put_item(item)
        return _parse(item, LiftDayRead)

    def get_lift_day(self, lift: str, date: str) -> LiftDayRead:
        """Read one day of a lift."""
        self._reject_resort(lift)
        item = self._repo.get_item(lift, path_date_to_metadata(date))
        if item is None:
            raise NotFound("Day not found")
        return _parse(item, LiftDayRead)

    def patch_lift_day(self, lift: str, date: str, body: LiftDayPatch) -> LiftDayRead:
        """Update only the sent fields of one lift day.

        A body that sets nothing is refused here, so ``UpdateItem`` is never
        called with an empty ``SET``.
        """
        self._reject_resort(lift)
        fields = body.model_dump(exclude_unset=True, mode="json")
        if not fields:
            raise BadRequest("No fields to update")
        item = self._repo.update_item(lift, path_date_to_metadata(date), fields)
        if item is None:
            raise NotFound("Day not found")
        return _parse(item, LiftDayRead)

    def delete_lift_day(self, lift: str, date: str) -> None:
        """Delete one day of a lift."""
        self._reject_resort(lift)
        if not self._repo.delete_item(lift, path_date_to_metadata(date)):
            raise NotFound("Day not found")

    def list_lift(self, lift: str, limit: int, token: str | None) -> LiftPage:
        """Read one page of a lift partition in sort key order.

        A partition holds profiles and lift days side by side, and the sort key
        tells them apart.
        """
        self._reject_resort(lift)
        items, last_key = self._repo.query_partition(
            lift, limit, _start_key(token, TABLE_TOKEN_KEYS, lift)
        )
        parsed = [
            _parse(
                item,
                ProfileRead if item["Metadata"] == STATIC_METADATA else LiftDayRead,
            )
            for item in items
        ]
        return LiftPage(
            items=parsed, count=len(parsed), next_token=_next_token(last_key)
        )

    def list_lift_rankings(
        self, lift: str, limit: int, token: str | None
    ) -> RankingPage:
        """Read one page of a lift's rider rankings, highest count first."""
        self._reject_resort(lift)
        items, last_key = self._repo.query_rankings(
            lift, limit, _start_key(token, RANKING_TOKEN_KEYS, lift)
        )
        parsed = [_parse(item, RankingRead) for item in items]
        return RankingPage(
            items=parsed, count=len(parsed), next_token=_next_token(last_key)
        )

    def put_resort_day(self, date: str, body: ResortDayWrite) -> ResortDayRead:
        """Write one resort-wide day, replacing whatever was stored there."""
        item = {
            "Lift": RESORT_LIFT,
            "Metadata": path_date_to_metadata(date),
            **body.model_dump(mode="json"),
        }
        self._repo.put_item(item)
        return _parse(item, ResortDayRead)

    def get_resort_day(self, date: str) -> ResortDayRead:
        """Read one resort-wide day."""
        item = self._repo.get_item(RESORT_LIFT, path_date_to_metadata(date))
        if item is None:
            raise NotFound("Resort day not found")
        return _parse(item, ResortDayRead)

    def patch_resort_day(self, date: str, body: ResortDayPatch) -> ResortDayRead:
        """Update only the sent fields of one resort-wide day."""
        fields = body.model_dump(exclude_unset=True, mode="json")
        if not fields:
            raise BadRequest("No fields to update")
        item = self._repo.update_item(RESORT_LIFT, path_date_to_metadata(date), fields)
        if item is None:
            raise NotFound("Resort day not found")
        return _parse(item, ResortDayRead)

    def delete_resort_day(self, date: str) -> None:
        """Delete one resort-wide day."""
        if not self._repo.delete_item(RESORT_LIFT, path_date_to_metadata(date)):
            raise NotFound("Resort day not found")

    def list_resort_days(self, limit: int, token: str | None) -> ResortPage:
        """Read one page of the resort partition in sort key order."""
        items, last_key = self._repo.query_partition(
            RESORT_LIFT, limit, _start_key(token, TABLE_TOKEN_KEYS, RESORT_LIFT)
        )
        parsed = [_parse(item, ResortDayRead) for item in items]
        return ResortPage(
            items=parsed, count=len(parsed), next_token=_next_token(last_key)
        )

    def list_resort_rankings(self, limit: int, token: str | None) -> RankingPage:
        """Read one page of the resort rider rankings, highest count first."""
        items, last_key = self._repo.query_rankings(
            RESORT_LIFT,
            limit,
            _start_key(token, RANKING_TOKEN_KEYS, RESORT_LIFT),
        )
        parsed = [_parse(item, RankingRead) for item in items]
        return RankingPage(
            items=parsed, count=len(parsed), next_token=_next_token(last_key)
        )
