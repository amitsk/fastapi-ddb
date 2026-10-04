from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings read from the environment.

    Environment variable names are the uppercase field names, with no prefix.
    """

    dynamodb_table_name: str = "SkiLifts"
    aws_region: str = "us-east-1"
    dynamodb_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
