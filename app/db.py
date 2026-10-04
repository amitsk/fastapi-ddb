import boto3
from boto3.resources.base import ServiceResource

from app.config import Settings

# Credentials DynamoDB Local accepts when the settings do not supply both keys.
LOCAL_CREDENTIAL = "local"


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
