import pathlib
import re
import runpy

from moto import mock_aws

from app.config import Settings
from app.db import dynamodb_resource
from app.repositories.skilifts import SkiLiftRepository
from app.sample import ITEMS
from scripts.create_table import main as create_main
from scripts.seed import main as seed_main


@mock_aws
def test_create_table_is_idempotent_and_seed_keeps_extra_items(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)
    create_main()
    create_main()
    settings = Settings()
    repo = SkiLiftRepository(
        dynamodb_resource(settings).Table(settings.dynamodb_table_name)
    )
    repo.put_item(
        {
            "Lift": "Extra",
            "Metadata": "Static Data",
            "ExperiencedRidersOnly": False,
            "VerticalFeet": 1,
            "LiftTime": "1:00",
        }
    )
    seed_main()
    seed_main()
    assert repo.get_item("Extra", "Static Data")["VerticalFeet"] == 1
    assert repo.get_item("Lift 3", "Static Data")["LiftTime"] == "7:30"
    assert repo.get_item("Resort Data", "03/01/20") is not None
    assert len(ITEMS) == 19


@mock_aws
def test_scripts_run_main_when_executed_as_scripts(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)
    runpy.run_path("scripts/create_table.py", run_name="__main__")
    runpy.run_path("scripts/seed.py", run_name="__main__")
    settings = Settings()
    repo = SkiLiftRepository(
        dynamodb_resource(settings).Table(settings.dynamodb_table_name)
    )
    assert repo.get_item("Lift 3", "Static Data") is not None


def test_compose_and_run_targets_match_the_local_run():
    compose = pathlib.Path("docker-compose.yml").read_text()
    assert "amazon/dynamodb-local" in compose
    assert "8000:8000" in compose
    assert "-sharedDb" in compose
    makefile = pathlib.Path("Makefile").read_text()
    for target in ("db-up", "db-down", "db-create-table", "db-seed", "run"):
        assert re.search(rf"^{target}:.*## ", makefile, re.MULTILINE), target
    assert "uvicorn app.main:app --port 3000" in makefile
