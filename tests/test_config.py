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


def test_scrubbing_ambient_env_restores_the_defaults(
    monkeypatch, isolated_settings_env
):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "Other")

    # The seeded variables really do reach Settings, so this test is not vacuous.
    seeded = Settings()
    assert seeded.aws_region == "eu-west-1"
    assert seeded.dynamodb_endpoint_url == "http://localhost:8000"
    assert seeded.aws_access_key_id == "AKID"
    assert seeded.aws_secret_access_key == "SECRET"
    assert seeded.dynamodb_table_name == "Other"

    isolated_settings_env()

    scrubbed = Settings()
    assert scrubbed.aws_region == "us-east-1"
    assert scrubbed.dynamodb_endpoint_url is None
    assert scrubbed.aws_access_key_id is None
    assert scrubbed.aws_secret_access_key is None
    assert scrubbed.dynamodb_table_name == "SkiLifts"
