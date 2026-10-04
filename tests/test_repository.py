from decimal import Decimal

from moto import mock_aws

from app.config import Settings
from app.db import GSI_NAME, create_skilifts_table, dynamodb_resource
from app.repositories.skilifts import SkiLiftRepository
from app.services.skilifts import GSI_NAME as SERVICE_GSI_NAME


def _repository():
    """Build a repository over a freshly created table inside moto."""
    settings = Settings(aws_access_key_id="testing", aws_secret_access_key="testing")
    resource = dynamodb_resource(settings)
    create_skilifts_table(resource, settings.dynamodb_table_name)
    return SkiLiftRepository(resource.Table(settings.dynamodb_table_name))


@mock_aws
def test_put_replaces_the_whole_item_and_queries_in_spec_order():
    settings = Settings(aws_access_key_id="testing", aws_secret_access_key="testing")
    resource = dynamodb_resource(settings)
    create_skilifts_table(resource, settings.dynamodb_table_name)
    repo = SkiLiftRepository(resource.Table(settings.dynamodb_table_name))
    repo.put_item(
        {
            "Lift": "Lift 3",
            "Metadata": "Static Data",
            "ExperiencedRidersOnly": False,
            "VerticalFeet": 1300,
            "LiftTime": "7:30",
            "LiftStatus": "Open",
        }
    )
    repo.put_item(
        {
            "Lift": "Lift 3",
            "Metadata": "Static Data",
            "ExperiencedRidersOnly": False,
            "VerticalFeet": 1300,
            "LiftTime": "7:30",
        }
    )
    assert "LiftStatus" not in repo.get_item("Lift 3", "Static Data")
    repo.put_item(
        {
            "Lift": "Lift 3",
            "Metadata": "02/01/20",
            "TotalUniqueLiftRiders": 6000,
            "AverageSnowCoverageInches": 35,
            "LiftStatus": "Open",
            "AvalancheDanger": "Low",
        }
    )
    repo.put_item(
        {
            "Lift": "Lift 3",
            "Metadata": "01/01/20",
            "TotalUniqueLiftRiders": 5000,
            "AverageSnowCoverageInches": 30,
            "LiftStatus": "Open",
            "AvalancheDanger": "Low",
        }
    )
    items, _ = repo.query_partition("Lift 3", limit=10, start_key=None)
    assert [item["Metadata"] for item in items] == [
        "01/01/20",
        "02/01/20",
        "Static Data",
    ]
    rankings, _ = repo.query_rankings("Lift 3", limit=10, start_key=None)
    assert [item["Metadata"] for item in rankings] == ["02/01/20", "01/01/20"]
    assert "LiftStatus" not in rankings[0]
    assert repo.delete_item("Lift 3", "01/01/20") is True
    assert repo.delete_item("Lift 3", "01/01/20") is False
    assert repo.update_item("Lift 3", "missing", {"LiftStatus": "Closed"}) is None
    updated = repo.update_item("Lift 3", "02/01/20", {"TotalUniqueLiftRiders": 7000})
    assert updated["TotalUniqueLiftRiders"] == Decimal("7000")
    assert updated["AverageSnowCoverageInches"] == Decimal("35")


@mock_aws
def test_update_sets_only_the_given_fields_and_delete_removes_the_item():
    repo = _repository()
    repo.put_item(
        {
            "Lift": "Lift 3",
            "Metadata": "01/01/20",
            "TotalUniqueLiftRiders": 5000,
            "AverageSnowCoverageInches": 30,
            "LiftStatus": "Open",
            "AvalancheDanger": "Low",
        }
    )
    updated = repo.update_item("Lift 3", "01/01/20", {"LiftStatus": "Closed"})
    assert updated == {
        "Lift": "Lift 3",
        "Metadata": "01/01/20",
        "TotalUniqueLiftRiders": Decimal("5000"),
        "AverageSnowCoverageInches": Decimal("30"),
        "LiftStatus": "Closed",
        "AvalancheDanger": "Low",
    }
    assert repo.delete_item("Lift 3", "01/01/20") is True
    assert repo.get_item("Lift 3", "01/01/20") is None


@mock_aws
def test_open_lifts_is_written_as_a_number_set():
    repo = _repository()
    repo.put_item(
        {
            "Lift": "Resort Data",
            "Metadata": "01/01/20",
            "TotalUniqueLiftRiders": 5500,
            "AverageSnowCoverageInches": 35,
            "AvalancheDanger": "Considerable",
            "OpenLifts": [3, 23, 16],
        }
    )
    item = repo.get_item("Resort Data", "01/01/20")
    assert item["OpenLifts"] == {Decimal("3"), Decimal("16"), Decimal("23")}
    rankings, _ = repo.query_rankings("Resort Data", limit=10, start_key=None)
    assert [entry["Metadata"] for entry in rankings] == ["01/01/20"]


@mock_aws
def test_an_update_replaces_open_lifts_with_a_number_set():
    repo = _repository()
    repo.put_item(
        {
            "Lift": "Resort Data",
            "Metadata": "01/01/20",
            "TotalUniqueLiftRiders": 5500,
            "AverageSnowCoverageInches": 35,
            "AvalancheDanger": "Considerable",
            "OpenLifts": [3, 23, 16],
        }
    )
    updated = repo.update_item("Resort Data", "01/01/20", {"OpenLifts": [16, 10]})
    assert updated["OpenLifts"] == {Decimal("10"), Decimal("16")}
    assert updated["TotalUniqueLiftRiders"] == Decimal("5500")


@mock_aws
def test_a_start_key_rider_count_from_a_token_paginates_the_rankings():
    repo = _repository()
    for metadata, riders in (
        ("01/01/20", 5000),
        ("02/01/20", 6000),
        ("03/01/20", 5500),
    ):
        repo.put_item(
            {"Lift": "Lift 3", "Metadata": metadata, "TotalUniqueLiftRiders": riders}
        )
    first, start_key = repo.query_rankings("Lift 3", limit=1, start_key=None)
    assert [item["Metadata"] for item in first] == ["02/01/20"]
    # A decoded token carries a JSON integer, which the repository converts.
    token_key = {
        name: int(value) if name == "TotalUniqueLiftRiders" else value
        for name, value in start_key.items()
    }
    second, _ = repo.query_rankings("Lift 3", limit=1, start_key=token_key)
    assert [item["Metadata"] for item in second] == ["03/01/20"]


@mock_aws
def test_a_table_start_key_paginates_the_partition_ascending():
    repo = _repository()
    for metadata in ("02/01/20", "01/01/20", "Static Data"):
        repo.put_item({"Lift": "Lift 3", "Metadata": metadata})
    first, start_key = repo.query_partition("Lift 3", limit=1, start_key=None)
    assert [item["Metadata"] for item in first] == ["01/01/20"]
    second, remaining = repo.query_partition("Lift 3", limit=1, start_key=start_key)
    assert [item["Metadata"] for item in second] == ["02/01/20"]
    # The start key is the last key read, so the third page starts after it.
    assert remaining == {"Lift": "Lift 3", "Metadata": "02/01/20"}
    third, last = repo.query_partition("Lift 3", limit=1, start_key=remaining)
    assert [item["Metadata"] for item in third] == ["Static Data"]
    assert last is None


@mock_aws
def test_creating_an_existing_table_leaves_it_unchanged():
    repo = _repository()
    repo.put_item(
        {"Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": 5000}
    )
    # A second call raises ResourceInUseException inside boto3, which is absorbed.
    settings = Settings(aws_access_key_id="testing", aws_secret_access_key="testing")
    create_skilifts_table(dynamodb_resource(settings), settings.dynamodb_table_name)
    assert repo.get_item("Lift 3", "01/01/20") is not None
    rankings, _ = repo.query_rankings("Lift 3", limit=10, start_key=None)
    assert [item["Metadata"] for item in rankings] == ["01/01/20"]


def test_the_index_name_matches_the_service_sentinel():
    assert GSI_NAME == SERVICE_GSI_NAME
