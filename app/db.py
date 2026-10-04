from typing import Any

import boto3
from boto3.resources.base import ServiceResource
from botocore.exceptions import ClientError

from app.config import Settings

# Credentials DynamoDB Local accepts when the settings do not supply both keys.
LOCAL_CREDENTIAL = "local"

# The name of the riders index. It lives here because this module creates the
# index; ``app.services.skilifts`` re-exports it, so both import paths name the
# same string.
GSI_NAME = "SkiLiftsByRiders"

# DynamoDB only accepts attribute definitions for attributes used as keys, so
# these three are the whole list: the two table keys and the index sort key.
ATTRIBUTE_DEFINITIONS = [
    {"AttributeName": "Lift", "AttributeType": "S"},
    {"AttributeName": "Metadata", "AttributeType": "S"},
    {"AttributeName": "TotalUniqueLiftRiders", "AttributeType": "N"},
]

RIDERS_INDEX = {
    "IndexName": GSI_NAME,
    "KeySchema": [
        {"AttributeName": "Lift", "KeyType": "HASH"},
        {"AttributeName": "TotalUniqueLiftRiders", "KeyType": "RANGE"},
    ],
    # Only the sort key is projected: a rankings row is the lift, the date, and
    # the rider count, so the day's facets never reach the index.
    "Projection": {"ProjectionType": "INCLUDE", "NonKeyAttributes": ["Metadata"]},
}


def client_kwargs(settings: Settings) -> dict[str, str]:
    """Build the boto3 client arguments for the configured DynamoDB target.

    A custom endpoint (DynamoDB Local) always needs credentials, so they default
    to ``local``/``local`` when the settings do not carry both of them. Without a
    custom endpoint no keys are injected and the default AWS credential chain
    applies.
    """
    kwargs: dict[str, str] = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint_url is not None:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
        if (
            settings.aws_access_key_id is not None
            and settings.aws_secret_access_key is not None
        ):
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        else:
            kwargs["aws_access_key_id"] = LOCAL_CREDENTIAL
            kwargs["aws_secret_access_key"] = LOCAL_CREDENTIAL
    return kwargs


def dynamodb_resource(settings: Settings) -> ServiceResource:
    """Create a boto3 DynamoDB service resource for the given settings."""
    return boto3.resource("dynamodb", **client_kwargs(settings))


def create_skilifts_table(resource: ServiceResource, table_name: str) -> None:
    """Create the ``SkiLifts`` table and its riders index, on demand billing.

    An existing table is left exactly as it is: ``ResourceInUseException`` is
    absorbed so the creator is safe to run on every start. Any other failure is
    raised.
    """
    # The service actions are built by boto3's resource factory at runtime, so
    # ``ServiceResource`` itself carries no ``create_table``.
    service: Any = resource
    try:
        service.create_table(
            TableName=table_name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=ATTRIBUTE_DEFINITIONS,
            KeySchema=[
                {"AttributeName": "Lift", "KeyType": "HASH"},
                {"AttributeName": "Metadata", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[RIDERS_INDEX],
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ResourceInUseException":
            return
        raise
