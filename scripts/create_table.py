"""Create the ``SkiLifts`` table on the configured DynamoDB target.

An existing table is left as it is, so the script is safe to run on every
local start: ``app.db.create_skilifts_table`` absorbs
``ResourceInUseException``.

Local run:

    make db-create-table
"""

from app.config import Settings
from app.db import create_skilifts_table, dynamodb_resource


def main() -> None:
    """Create the table named by the settings, with its riders index."""
    settings = Settings()
    create_skilifts_table(dynamodb_resource(settings), settings.dynamodb_table_name)


if __name__ == "__main__":
    main()
