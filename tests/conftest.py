from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import Settings
from app.db import create_skilifts_table, dynamodb_resource
from app.main import create_app
from app.repositories.skilifts import SkiLiftRepository
from app.sample import ITEMS

# Every environment variable app.config.Settings reads, with no env prefix.
SETTINGS_ENV_NAMES = (
    "DYNAMODB_TABLE_NAME",
    "AWS_REGION",
    "DYNAMODB_ENDPOINT_URL",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch):
    """Keep ambient settings variables out of every test.

    ``AWS_REGION`` is injected automatically by EC2/ECS-hosted dev boxes and the
    documented local workflow exports ``DYNAMODB_ENDPOINT_URL``, so tests must not
    depend on what happens to be in the environment.

    Returns the scrub callable so a test can re-apply it after seeding variables.
    """

    def scrub() -> None:
        for name in SETTINGS_ENV_NAMES:
            monkeypatch.delenv(name, raising=False)

    scrub()
    return scrub


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A ``TestClient`` over a moto table holding the sample items.

    The fixture is function-scoped and reseeds the table for every test, so no
    test can see another's writes. ``mock_aws`` wraps the whole yield: the app is
    built and every request runs inside it, which is what lets a test open its
    own client against the same mock.

    ``DYNAMODB_ENDPOINT_URL`` stays unset, so ``dynamodb_resource`` injects no
    dummy keys and moto's own credentials are the ones in play. The two keys are
    set anyway because a stray endpoint in the environment would otherwise reach
    the client as a real HTTP target.

    ``raise_server_exceptions=False`` is what makes the 500 body observable:
    Starlette's outermost handler answers it and then re-raises, and only the
    non-raising client returns that response instead of propagating the error.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        settings = Settings()
        resource = dynamodb_resource(settings)
        create_skilifts_table(resource, settings.dynamodb_table_name)
        repository = SkiLiftRepository(resource.Table(settings.dynamodb_table_name))
        for item in ITEMS:
            repository.put_item(item)
        with TestClient(
            create_app(settings), raise_server_exceptions=False
        ) as test_client:
            yield test_client
