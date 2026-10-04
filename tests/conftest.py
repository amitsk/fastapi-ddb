import pytest

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
