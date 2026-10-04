"""The DynamoDB calls for the SkiLifts table.

The repository is the only layer that speaks boto3. It stores and returns the
table's own attribute names, converts nothing, and knows nothing about HTTP or
the pagination token format: a start key arrives as the key ``app.services``
decoded, and the boto3 ``LastEvaluatedKey`` leaves as-is for it to encode.
"""

from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from boto3.resources.base import ServiceResource
from botocore.exceptions import ClientError

from app.db import GSI_NAME

# The condition that makes a write fail instead of creating the item.
ITEM_EXISTS = "attribute_exists(Lift) AND attribute_exists(Metadata)"


def _stored(attributes: dict) -> dict:
    """Return a copy of the attributes as DynamoDB should store them.

    ``OpenLifts`` is a number set, so a list of lift numbers becomes a set; the
    caller's dict is left alone.
    """
    stored = dict(attributes)
    if isinstance(stored.get("OpenLifts"), list):
        stored["OpenLifts"] = set(stored["OpenLifts"])
    return stored


def _start_key(start_key: dict) -> dict:
    """Return a token key with its numbers in the type boto3 reads and writes.

    A decoded token carries a JSON integer rider count, while boto3 hands every
    number back as a ``Decimal``, so the count is converted before it goes into
    ``ExclusiveStartKey``.
    """
    return {
        name: value if isinstance(value, str) else Decimal(value)
        for name, value in start_key.items()
    }


def _is_conditional_failure(error: ClientError) -> bool:
    """Report whether the error is the ``ITEM_EXISTS`` condition refusing a write."""
    return error.response["Error"]["Code"] == "ConditionalCheckFailedException"


class SkiLiftRepository:
    """Reads and writes the three item kinds of the ``SkiLifts`` table."""

    def __init__(self, table: ServiceResource) -> None:
        # The table class is built by boto3's resource factory at runtime, so it
        # has no importable type; every call below is a plain table action.
        self._table: Any = table

    def put_item(self, item: dict) -> dict:
        """Write the item at its key, replacing whatever was stored there.

        ``PutItem`` replaces the whole item, so attributes of another kind that
        the caller omitted are removed.

        The stored attributes are returned, which is not always the dict that was
        handed in: ``OpenLifts`` is a number set, so it comes back deduplicated.
        Returning them is what lets a ``PUT`` answer with the item as stored
        without a second call. ``PutItem`` cannot be asked for the new item --
        its ``ReturnValues`` takes only ``NONE`` or ``ALL_OLD`` -- so the answer is
        the attributes about to be written rather than a re-read. A re-read would
        have been both an extra call and eventually consistent, so a replacing
        write could answer with the item as it was before it.
        """
        stored = _stored(item)
        self._table.put_item(Item=stored)
        return stored

    def get_item(self, lift: str, metadata: str) -> dict | None:
        """Read one item, or ``None`` when the key holds none."""
        response = self._table.get_item(Key={"Lift": lift, "Metadata": metadata})
        return response.get("Item")

    def update_item(self, lift: str, metadata: str, fields: dict) -> dict | None:
        """Set only the given attributes and return the item as stored now.

        Returns ``None`` when the key holds no item, which the same condition
        expression makes a failure rather than a create.
        """
        names = {f"#field{index}": name for index, name in enumerate(fields)}
        values = {
            f":value{index}": value
            for index, value in enumerate(_stored(fields).values())
        }
        assignments = ", ".join(
            f"{name} = {value}" for name, value in zip(names, values, strict=True)
        )
        try:
            response = self._table.update_item(
                Key={"Lift": lift, "Metadata": metadata},
                UpdateExpression=f"SET {assignments}",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression=ITEM_EXISTS,
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            if _is_conditional_failure(error):
                return None
            raise
        return response.get("Attributes")

    def delete_item(self, lift: str, metadata: str) -> bool:
        """Delete one item, returning ``False`` when there was none."""
        try:
            self._table.delete_item(
                Key={"Lift": lift, "Metadata": metadata},
                ConditionExpression=ITEM_EXISTS,
            )
        except ClientError as error:
            if _is_conditional_failure(error):
                return False
            raise
        return True

    def query_partition(
        self, lift: str, limit: int, start_key: dict | None
    ) -> tuple[list[dict], dict | None]:
        """Read one page of a lift partition, oldest sort key first.

        There is no filter: a partition holds profiles and lift days, and the
        service decides which is which. The returned start key is ``None`` on a
        last page.
        """
        return self._query(
            lift=lift,
            limit=limit,
            start_key=start_key,
            scan_forward=True,
        )

    def query_rankings(
        self, lift: str, limit: int, start_key: dict | None
    ) -> tuple[list[dict], dict | None]:
        """Read one page of the riders index for a lift, highest count first.

        A profile has no rider count and so is not in the index at all.
        """
        return self._query(
            index_name=GSI_NAME,
            lift=lift,
            limit=limit,
            start_key=start_key,
            scan_forward=False,
        )

    def _query(
        self,
        *,
        lift: str,
        limit: int,
        start_key: dict | None,
        scan_forward: bool,
        index_name: str | None = None,
    ) -> tuple[list[dict], dict | None]:
        """Run one page of a partition query and split items from the start key."""
        arguments: dict[str, Any] = {
            "KeyConditionExpression": Key("Lift").eq(lift),
            "Limit": limit,
            "ScanIndexForward": scan_forward,
        }
        if index_name is not None:
            arguments["IndexName"] = index_name
        if start_key is not None:
            arguments["ExclusiveStartKey"] = _start_key(start_key)
        response = self._table.query(**arguments)
        return list(response["Items"]), response.get("LastEvaluatedKey")
