from app.config import Settings
from app.db import client_kwargs


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.dynamodb_table_name == "SkiLifts"
    assert settings.aws_region == "us-east-1"
    assert settings.dynamodb_endpoint_url is None


def test_endpoint_with_both_keys_uses_those_keys():
    settings = Settings(
        dynamodb_endpoint_url="http://localhost:8000",
        aws_access_key_id="AKID",
        aws_secret_access_key="SECRET",
    )
    assert client_kwargs(settings) == {
        "region_name": "us-east-1",
        "endpoint_url": "http://localhost:8000",
        "aws_access_key_id": "AKID",
        "aws_secret_access_key": "SECRET",
    }


def test_endpoint_with_one_key_uses_local_credentials():
    settings = Settings(
        dynamodb_endpoint_url="http://localhost:8000",
        aws_access_key_id="AKID",
        aws_secret_access_key=None,
    )
    kwargs = client_kwargs(settings)
    assert kwargs["aws_access_key_id"] == "local"
    assert kwargs["aws_secret_access_key"] == "local"


def test_without_endpoint_does_not_inject_keys():
    settings = Settings(aws_access_key_id="AKID", aws_secret_access_key="SECRET")
    kwargs = client_kwargs(settings)
    assert kwargs == {"region_name": "us-east-1"}
    assert "aws_access_key_id" not in kwargs
