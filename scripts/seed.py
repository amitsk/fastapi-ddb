"""Write the sample items into the ``SkiLifts`` table.

Only the sample keys are written, and each one is replaced in place, so the
script is safe to run repeatedly: it never removes an item it did not write.

Local run:

    make db-seed
"""

from typing import Any

from app.config import Settings
from app.db import dynamodb_resource
from app.repositories.skilifts import SkiLiftRepository
from app.sample import ITEMS


def main() -> None:
    """Put every sample item, leaving every other key in the table alone."""
    settings = Settings()
    # The table class is built by boto3's resource factory at runtime, so
    # ``ServiceResource`` itself carries no ``Table``.
    resource: Any = dynamodb_resource(settings)
    repository = SkiLiftRepository(resource.Table(settings.dynamodb_table_name))
    for item in ITEMS:
        repository.put_item(item)


if __name__ == "__main__":
    main()
