"""Sentinel keys, date conversion, pagination tokens, and domain errors.

The service layer knows the table's sentinels and the wire format of a
``nextToken``; it knows nothing about HTTP status codes, which ``app/errors.py``
maps from the errors raised here.
"""

import base64
import json

# Sentinel values the routes and the repository branch on.
STATIC_METADATA = "Static Data"
RESORT_LIFT = "Resort Data"
GSI_NAME = "SkiLiftsByRiders"

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
