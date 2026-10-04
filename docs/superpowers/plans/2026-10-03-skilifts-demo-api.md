# SkiLifts Demo API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI demo that creates, reads, updates, and deletes the three `SkiLifts` item kinds and serves the table's partition and rankings reads.

**Architecture:** Pydantic models validate facet bodies. A repository performs the DynamoDB calls. A service applies sentinel keys, date conversion, pagination tokens, and `Decimal` conversion. Routes call the service and `app/errors.py` maps failures to the spec's `detail` bodies. `create_app()` builds the boto3 table, repository, and service on startup.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, pydantic-settings, boto3, uvicorn, pytest, moto, httpx2. Tooling: uv (bootstrap, lock, run), hatchling, ruff (lint and format), ty (type check), pre-commit, GNU Make.

**Spec:** `docs/superpowers/specs/2026-10-03-skilifts-demo-api-design.md`

**Tooling guide:** The tooling requirements come from the user's instruction, not from the spec (spec §2 is silent on them). The guide is the cookiecutter checkout at `/home/amit/projects/python/cookiecutter-python-library/{{cookiecutter.project_slug}}/` (`Makefile`, `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/python-tests.yml`, `README.md`) and its `.mise.toml`. Where the cookiecutter and the spec disagree, the spec wins. Task 1 lists every deliberate difference.

## Global Constraints

- Everything is bootstrapped and run with uv: `uv sync` installs, `uv run <cmd>` executes, `uv.lock` is committed. Never `pip install`, never a hand-made venv.
- Tests are pytest. Lint and format are ruff (`ruff check`, `ruff format`). Type check is ty (`ty check`). The gate for every task is `make fix_format && make check`, which must exit 0 before each commit. Fix findings in the code; do not shrink the rule set. A per-line `# noqa: <code>` or `# ty: ignore[<rule>]` is allowed only with the rule code and only where the spec fixes the value or shape that trips it.
- Checked directories are `app`, `scripts`, and `tests` for ruff; `app` and `scripts` for ty.
- Python 3.14 (`requires-python >= 3.14`).
- The app is started with `uvicorn app.main:app --port 3000`. DynamoDB Local listens on port 8000.
- Table `SkiLifts`, billing `PAY_PER_REQUEST`, partition key `Lift` (`S`), sort key `Metadata` (`S`).
- GSI `SkiLiftsByRiders`, partition key `Lift` (`S`), sort key `TotalUniqueLiftRiders` (`N`), projection `INCLUDE` of `Metadata`.
- `STATIC_METADATA = "Static Data"`, `RESORT_LIFT = "Resort Data"`, `GSI_NAME = "SkiLiftsByRiders"`.
- A URL date is `MM-DD-YY`. The stored and returned sort key is `MM/DD/YY` (`01-01-20` → `01/01/20`).
- `limit` defaults to 20 and is an integer from 1 to 100.
- `OpenLifts` has at least one integer ≥ 0, is stored as a number set, and is returned sorted ascending.
- JSON numbers are integers (`5000`, never `5000.0`).
- Error bodies are `{"detail": ...}` with the exact messages in spec §10.
- `nextToken` is unpadded base64url of compact UTF-8 JSON with alphabetically sorted keys.
- Tests use FastAPI `TestClient`, which depends on the `httpx2` package. The suite uses moto and does not need Docker.
- There is no coverage percentage gate (spec §12). The cookiecutter's `--cov-fail-under` is not copied.
- Out of scope: auth, a deploy stack, rate limiting, security-header middleware, request ids, CORS middleware, response compression, profile `PATCH`, profile `DELETE`, a rider-range filter, a custom error envelope, and importing Workbench-generated rows.

## Review Focus

- A `PATCH` that sends one field leaves every omitted day field unchanged. A client who sets only `LiftStatus` still sees the same rider count, snow, and avalanche danger.
- `GET /lifts/{lift}/rankings` omits the static profile. A profile has no rider count, so it must not appear beside that lift's days.
- `GET /lifts/{unknown}` returns `200` with `count` 0 and no `nextToken` key. An empty partition is an empty page.
- `python scripts/create_table.py` and `python scripts/seed.py`, run as scripts, execute `main()`. A module that only defines `main` exits 0 and does nothing.
- With `DYNAMODB_ENDPOINT_URL` set and only one of the two AWS keys present, boto3 receives the access key `local` and the secret key `local`.

## File Map

- `pyproject.toml`, `uv.lock` — package metadata, dependency groups, ruff/ty/pytest/coverage config.
- `Makefile` — dev, check, and local-run targets.
- `.mise.toml`, `.pre-commit-config.yaml`, `.github/workflows/python-tests.yml` — toolchain pin, hooks, CI.
- `app/config.py` — `Settings`.
- `app/db.py` — boto3 kwargs, resource, and `create_skilifts_table`.
- `app/sample.py` — the 19 spec §5 items.
- `app/schemas/skilifts.py` — facet models, page models, `DATE_PATTERN`.
- `app/services/skilifts.py` — sentinels, tokens, dates, domain errors, `SkiLiftService`.
- `app/repositories/skilifts.py` — DynamoDB calls.
- `app/errors.py` — status mapping.
- `app/main.py` — `create_app()` and module-level `app`.
- `app/routes/lifts.py`, `app/routes/resort.py` — HTTP routes.
- `scripts/create_table.py`, `scripts/seed.py` — local-run scripts.
- `docker-compose.yml` — DynamoDB Local.
- `README.md` — comprehensive project documentation.
- `tests/conftest.py` and `tests/test_*.py` — the cases below.

---

### Task 1: uv Bootstrap and Tooling

**Files:**
- Create: `pyproject.toml`, `uv.lock` (generated by `uv lock`)
- Create: `Makefile`
- Create: `.mise.toml`, `.pre-commit-config.yaml`, `.github/workflows/python-tests.yml`
- Create: `app/__init__.py` and `scripts/__init__.py` (both empty, so ruff and ty have both directories to check)
- Modify: `.gitignore` (add `.ruff_cache/`)
- Test: `tests/test_tooling.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - Importable package `app` installed into the uv venv (hatchling, `[tool.hatch.build.targets.wheel] packages = ["app"]`).
  - Make targets: `help` (default), `install`, `build`, `clean`, `lint`, `type_check`, `test`, `coverage`, `check`, `check_format`, `fix_format`, `format`. Every target has a `## ` help comment. Task 10 adds the local-run targets.
  - `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and `pythonpath = ["."]` so tests can import `scripts.*`.

Deliberate differences from the cookiecutter (everything else follows it):
- Layout is root `app/` and `scripts/` (spec §3), not `src/`.
- Runtime dependencies: `fastapi`, `pydantic-settings`, `boto3`, `uvicorn`. Dependency group `dev`: `pytest`, `pytest-cov`, `moto[dynamodb]`, `httpx2`, `ruff`, `ty`, `pre-commit`. No loguru, more-itertools, faker, pytest-html, pytest-mock, pytest-datadir, pytest-print, analytics extra, notebooks, or cookiecutter hook.
- `requires-python = ">=3.14"`, ruff `target-version = "py314"`, `.mise.toml` `python = "3.14"`.
- Ruff rule set is the cookiecutter's `lint.select` verbatim. `lint.ignore` is `E501` plus `N815` (the spec fixes PascalCase attribute names such as `VerticalFeet`), `EM101`, `EM102`, and `TRY003` (domain errors carry the spec's literal messages). Test per-file ignores are the cookiecutter's plus `S105` and `S106` (dummy AWS keys).
- `make test` is `uv run pytest tests/ -v` with no `--cov-fail-under`. `make coverage` is the cookiecutter's report with no gate.
- `lint` and `check_format` run on `app scripts tests`; `type_check` runs `uv run ty check app scripts`.
- Coverage config uses `source = ["app"]`.
- The CI workflow runs `make install` then `make check`.

- [ ] **Step 1: Write the failing test**

```python
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_declares_uv_toolchain():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.14"
    assert data["build-system"]["build-backend"] == "hatchling.build"
    assert data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["app"]
    dev = " ".join(data["dependency-groups"]["dev"])
    for name in ("pytest", "moto", "httpx2", "ruff", "ty"):
        assert name in dev
    assert data["tool"]["pytest"]["ini_options"]["pythonpath"] == ["."]
    assert (ROOT / "uv.lock").exists()


def test_makefile_has_the_dev_targets_and_no_coverage_gate():
    makefile = (ROOT / "Makefile").read_text()
    for target in ("help", "install", "lint", "type_check", "test", "coverage", "check", "check_format", "fix_format"):
        assert re.search(rf"^{target}:.*## ", makefile, re.MULTILINE), target
    assert "uv run ty check app scripts" in makefile
    assert "cov-fail-under" not in makefile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tooling.py -v` (install `uv` first if absent: https://docs.astral.sh/uv/getting-started/installation/)
Expected: FAIL (no `pyproject.toml`, so `uv run` errors or `FileNotFoundError`)

- [ ] **Step 3: Create the project files**

Write `pyproject.toml` per the differences list above, then `uv lock` and `uv sync`. Adapt `Makefile`, `.pre-commit-config.yaml`, `.github/workflows/python-tests.yml`, and `.mise.toml` from the cookiecutter, applying the differences above and the project name `skilifts-demo-api`. Create the two empty `__init__.py` files.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tooling.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0
Then run: `make help`
Expected: lists every target from the Produces block with its help text

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock Makefile .mise.toml .pre-commit-config.yaml .github .gitignore app/__init__.py scripts/__init__.py tests/test_tooling.py
git commit -m "Bootstrap the project with uv, ruff, ty, and a Makefile."
```

---

### Task 2: Settings and Client Kwargs

**Files:**
- Create: `app/config.py`
- Create: `app/db.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: the uv environment and `make` targets from Task 1
- Produces:
  - `Settings` with fields `dynamodb_table_name: str = "SkiLifts"`, `aws_region: str = "us-east-1"`, `dynamodb_endpoint_url: str | None = None`, `aws_access_key_id: str | None = None`, `aws_secret_access_key: str | None = None`. Env names are the uppercase field names. No env prefix.
  - `client_kwargs(settings: Settings) -> dict[str, str]`
  - `dynamodb_resource(settings: Settings)` returns `boto3.resource("dynamodb", **client_kwargs(settings))`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.config`

- [ ] **Step 3: Implement settings and the boto3 client kwargs**

`Settings` is a `pydantic_settings.BaseSettings` with no env prefix. `client_kwargs` follows the four tests exactly. `dynamodb_resource` passes that dict to `boto3.resource`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/db.py tests/test_config.py
git commit -m "Add settings and DynamoDB client kwargs."
```

---

### Task 3: Schemas and Sample Data

**Files:**
- Create: `app/sample.py`
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/skilifts.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `ITEMS: list[dict]` — the 19 rows in spec §5. `OpenLifts` values are lists of ints in the table's written order.
  - `DATE_PATTERN = r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])-[0-9]{2}$"`
  - `LiftStatus` (`Open`, `Closed`, `Pending`) and `AvalancheDanger` (`Low`, `Moderate`, `Considerable`, `High`, `Extreme`)
  - Write models exclude keys. Read models include `Lift` and `Metadata`. `extra="forbid"` on every model.
  - `ProfileWrite`, `ProfileRead`
  - `LiftDayWrite`, `LiftDayPatch` (every field optional), `LiftDayRead`
  - `ResortDayWrite`, `ResortDayPatch` (every field optional), `ResortDayRead`
  - `RankingRead` with `Lift`, `Metadata`, `TotalUniqueLiftRiders`
  - `LiftPage`, `ResortPage`, `RankingPage`, each with `items`, `count: int`, and `next_token: str | None = None` serialized as `nextToken` and omitted when `None`
  - Field rules from spec §7, including `LiftTime` pattern `^\d{1,2}:\d{2}$` and `OpenLifts` `min_length=1`

- [ ] **Step 1: Write the failing test**

```python
import re
import pytest
from pydantic import ValidationError
from app.sample import ITEMS
from app.schemas.skilifts import DATE_PATTERN, LiftDayRead, LiftDayWrite, ProfileRead, ResortDayWrite

def test_sample_has_the_nineteen_spec_items():
    assert len(ITEMS) == 19
    profile = next(item for item in ITEMS if item["Lift"] == "Lift 3" and item["Metadata"] == "Static Data")
    assert ProfileRead.model_validate(profile).VerticalFeet == 1300
    day = next(item for item in ITEMS if item["Lift"] == "Lift 3" and item["Metadata"] == "01/01/20")
    assert LiftDayRead.model_validate(day).TotalUniqueLiftRiders == 5000
    resort = next(item for item in ITEMS if item["Lift"] == "Resort Data" and item["Metadata"] == "03/01/20")
    assert resort["OpenLifts"] == [3, 23, 16, 10]

def test_date_pattern_accepts_an_impossible_calendar_day():
    assert re.fullmatch(DATE_PATTERN, "02-31-20")
    assert re.fullmatch(DATE_PATTERN, "13-01-20") is None

def test_write_models_reject_bad_facet_values():
    with pytest.raises(ValidationError) as extra:
        LiftDayWrite.model_validate({"TotalUniqueLiftRiders": 1, "AverageSnowCoverageInches": 1, "LiftStatus": "Open", "AvalancheDanger": "Low", "Nope": 1})
    assert extra.value.errors()[0]["loc"] == ("Nope",)
    with pytest.raises(ValidationError) as riders:
        LiftDayWrite(TotalUniqueLiftRiders=1.5, AverageSnowCoverageInches=1, LiftStatus="Open", AvalancheDanger="Low")
    assert any(err["loc"] == ("TotalUniqueLiftRiders",) for err in riders.value.errors())
    with pytest.raises(ValidationError) as status:
        LiftDayWrite(TotalUniqueLiftRiders=1, AverageSnowCoverageInches=1, LiftStatus="Shut", AvalancheDanger="Low")
    assert any(err["loc"] == ("LiftStatus",) for err in status.value.errors())
    with pytest.raises(ValidationError):
        ResortDayWrite(TotalUniqueLiftRiders=1, AverageSnowCoverageInches=1, AvalancheDanger="Low", OpenLifts=[])
```

Import `pytest` in the test module.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.sample` or `app.schemas`

- [ ] **Step 3: Implement the models and copy the 19 items from spec §5**

Copy each spec row into `ITEMS` without renaming attributes. Read models accept those dicts. `next_token` uses `serialization_alias="nextToken"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/sample.py app/schemas tests/test_schemas.py
git commit -m "Add SkiLifts schemas and the 19 sample items."
```

---

### Task 4: Tokens, Dates, and Domain Errors

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/skilifts.py`
- Test: `tests/test_tokens.py`

**Interfaces:**
- Consumes: nothing from Tasks 2–3
- Produces:
  - `STATIC_METADATA`, `RESORT_LIFT`, `GSI_NAME` with the values in Global Constraints
  - `NotFound(detail: str)`, `BadRequest(detail: str)`, `InvalidToken(BadRequest)` whose detail is `"Invalid nextToken"`, `UnreadableItem(Exception)`
  - `path_date_to_metadata(date: str) -> str` replaces `-` with `/`
  - `encode_token(key: dict[str, str | int]) -> str`
  - `decode_token(token: str, *, expected_keys: frozenset[str], lift: str) -> dict[str, str | int]`
  - `TABLE_TOKEN_KEYS = frozenset({"Lift", "Metadata"})`
  - `RANKING_TOKEN_KEYS = frozenset({"Lift", "Metadata", "TotalUniqueLiftRiders"})`

- [ ] **Step 1: Write the failing test**

```python
import base64
import pytest
from app.services.skilifts import (
    RANKING_TOKEN_KEYS, TABLE_TOKEN_KEYS, InvalidToken,
    decode_token, encode_token, path_date_to_metadata,
)

def test_path_date_becomes_the_stored_sort_key():
    assert path_date_to_metadata("01-01-20") == "01/01/20"

def test_token_is_canonical_unpadded_base64url():
    token = encode_token({"Metadata": "01/01/20", "Lift": "Lift 3"})
    assert "=" not in token
    padded = token + "=" * (-len(token) % 4)
    assert base64.urlsafe_b64decode(padded) == b'{"Lift":"Lift 3","Metadata":"01/01/20"}'

def test_decode_table_token_round_trips():
    token = encode_token({"Lift": "Lift 3", "Metadata": "01/01/20"})
    assert decode_token(token, expected_keys=TABLE_TOKEN_KEYS, lift="Lift 3") == {
        "Lift": "Lift 3", "Metadata": "01/01/20",
    }

def test_decode_rejects_wrong_shape():
    table_token = encode_token({"Lift": "Lift 3", "Metadata": "01/01/20"})
    ranking_token = encode_token({"Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": 5000})
    other_lift = encode_token({"Lift": "Lift 10", "Metadata": "01/01/20"})
    for token, keys, lift in (
        ("%%%", TABLE_TOKEN_KEYS, "Lift 3"),
        (ranking_token, TABLE_TOKEN_KEYS, "Lift 3"),
        (table_token, RANKING_TOKEN_KEYS, "Lift 3"),
        (other_lift, TABLE_TOKEN_KEYS, "Lift 3"),
    ):
        with pytest.raises(InvalidToken) as caught:
            decode_token(token, expected_keys=keys, lift=lift)
        assert str(caught.value) == "Invalid nextToken"
        assert caught.value.detail == "Invalid nextToken"
    boolean_riders = encode_token({"Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": True})
    with pytest.raises(InvalidToken):
        decode_token(boolean_riders, expected_keys=RANKING_TOKEN_KEYS, lift="Lift 3")
```

`NotFound`, `BadRequest`, and `InvalidToken` store the message on `detail` and pass that same string to `Exception`. `InvalidToken()` uses `"Invalid nextToken"`. `encode_token` JSON-encodes its dict. `decode_token` rejects a boolean `TotalUniqueLiftRiders` with `isinstance(value, bool)` after `json.loads`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tokens.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.services`

- [ ] **Step 3: Implement the token and date functions**

`encode_token` uses `json.dumps(key, sort_keys=True, separators=(",", ":"))`, UTF-8, and unpadded urlsafe base64. `decode_token` restores padding, requires a JSON object, requires `expected_keys` as the exact key set, requires `Lift` and `Metadata` to be strings, requires `TotalUniqueLiftRiders` to be an `int` with no boolean and no fraction when that key is expected, and requires `Lift == lift`. Any failure raises `InvalidToken`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tokens.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/services tests/test_tokens.py
git commit -m "Add pagination tokens and domain errors."
```

---

### Task 5: Repository and Table Creation

**Files:**
- Modify: `app/db.py`
- Create: `app/repositories/__init__.py`
- Create: `app/repositories/skilifts.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `dynamodb_resource`, `GSI_NAME`
- Produces:
  - `create_skilifts_table(resource, table_name: str) -> None`. On `ResourceInUseException`, return without changing the table.
  - `SkiLiftRepository(table)`
  - `put_item(self, item: dict) -> None`
  - `get_item(self, lift: str, metadata: str) -> dict | None`
  - `update_item(self, lift: str, metadata: str, fields: dict) -> dict | None`
  - `delete_item(self, lift: str, metadata: str) -> bool`
  - `query_partition(self, lift: str, limit: int, start_key: dict | None) -> tuple[list[dict], dict | None]`
  - `query_rankings(self, lift: str, limit: int, start_key: dict | None) -> tuple[list[dict], dict | None]`

A missing item or a failed `attribute_exists(Lift) AND attribute_exists(Metadata)` condition returns `None` or `False`. `update_item` returns `ALL_NEW`. `query_partition` is ascending and has no filter. `query_rankings` queries `GSI_NAME` with `ScanIndexForward=False`. Lists stored as `OpenLifts` are written as sets. An integer `TotalUniqueLiftRiders` in `start_key` is converted to `Decimal` before `ExclusiveStartKey`. Returned items keep boto3's `Decimal` values.

- [ ] **Step 1: Write the failing test**

```python
from decimal import Decimal
from moto import mock_aws
from app.config import Settings
from app.db import create_skilifts_table, dynamodb_resource
from app.repositories.skilifts import SkiLiftRepository

@mock_aws
def test_put_replaces_the_whole_item_and_queries_in_spec_order():
    settings = Settings(aws_access_key_id="testing", aws_secret_access_key="testing")
    resource = dynamodb_resource(settings)
    create_skilifts_table(resource, settings.dynamodb_table_name)
    repo = SkiLiftRepository(resource.Table(settings.dynamodb_table_name))
    repo.put_item({"Lift": "Lift 3", "Metadata": "Static Data", "ExperiencedRidersOnly": False, "VerticalFeet": 1300, "LiftTime": "7:30", "LiftStatus": "Open"})
    repo.put_item({"Lift": "Lift 3", "Metadata": "Static Data", "ExperiencedRidersOnly": False, "VerticalFeet": 1300, "LiftTime": "7:30"})
    assert "LiftStatus" not in repo.get_item("Lift 3", "Static Data")
    repo.put_item({"Lift": "Lift 3", "Metadata": "02/01/20", "TotalUniqueLiftRiders": 6000, "AverageSnowCoverageInches": 35, "LiftStatus": "Open", "AvalancheDanger": "Low"})
    repo.put_item({"Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": 5000, "AverageSnowCoverageInches": 30, "LiftStatus": "Open", "AvalancheDanger": "Low"})
    items, _ = repo.query_partition("Lift 3", limit=10, start_key=None)
    assert [item["Metadata"] for item in items] == ["01/01/20", "02/01/20", "Static Data"]
    rankings, _ = repo.query_rankings("Lift 3", limit=10, start_key=None)
    assert [item["Metadata"] for item in rankings] == ["02/01/20", "01/01/20"]
    assert "LiftStatus" not in rankings[0]
    assert repo.delete_item("Lift 3", "01/01/20") is True
    assert repo.delete_item("Lift 3", "01/01/20") is False
    assert repo.update_item("Lift 3", "missing", {"LiftStatus": "Closed"}) is None
    updated = repo.update_item("Lift 3", "02/01/20", {"TotalUniqueLiftRiders": 7000})
    assert updated["TotalUniqueLiftRiders"] == Decimal("7000")
    assert updated["AverageSnowCoverageInches"] == Decimal("35")
```

Pass `aws_access_key_id="testing"` and `aws_secret_access_key="testing"` to `Settings`. Leave the endpoint unset so `client_kwargs` does not inject `local`. `Settings.aws_region` supplies `region_name`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repository.py -v`
Expected: FAIL with `ImportError` for `create_skilifts_table` or `SkiLiftRepository`

- [ ] **Step 3: Implement `create_skilifts_table` and `SkiLiftRepository`**

Attribute definitions are `Lift` (`S`), `Metadata` (`S`), and `TotalUniqueLiftRiders` (`N`) only. Key schema and the GSI match Global Constraints. `update_item` sets only the fields in `fields`, using expression attribute names.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/db.py app/repositories tests/test_repository.py
git commit -m "Add the SkiLifts repository and table creator."
```

---

### Task 6: Service

**Files:**
- Modify: `app/services/skilifts.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: repository methods from Task 5, models from Task 3, token and error types from Task 4
- Produces `SkiLiftService(repo: SkiLiftRepository)`:
  - `put_profile(self, lift: str, body: ProfileWrite) -> ProfileRead`
  - `get_profile(self, lift: str) -> ProfileRead`
  - `put_lift_day(self, lift: str, date: str, body: LiftDayWrite) -> LiftDayRead`
  - `get_lift_day(self, lift: str, date: str) -> LiftDayRead`
  - `patch_lift_day(self, lift: str, date: str, body: LiftDayPatch) -> LiftDayRead`
  - `delete_lift_day(self, lift: str, date: str) -> None`
  - `list_lift(self, lift: str, limit: int, token: str | None) -> LiftPage`
  - `list_lift_rankings(self, lift: str, limit: int, token: str | None) -> RankingPage`
  - `put_resort_day(self, date: str, body: ResortDayWrite) -> ResortDayRead`
  - `get_resort_day(self, date: str) -> ResortDayRead`
  - `patch_resort_day(self, date: str, body: ResortDayPatch) -> ResortDayRead`
  - `delete_resort_day(self, date: str) -> None`
  - `list_resort_days(self, limit: int, token: str | None) -> ResortPage`
  - `list_resort_rankings(self, limit: int, token: str | None) -> RankingPage`

Every `/lifts` method calls the resort check first and raises `BadRequest("Resort Data is served under /resort")` when `lift == RESORT_LIFT`. A `PATCH` whose `model_dump(exclude_unset=True)` is empty raises `BadRequest("No fields to update")` and does not call `update_item`. Missing profile → `NotFound("Profile not found")`. Missing lift day → `NotFound("Day not found")`. Missing resort day → `NotFound("Resort day not found")`. `Metadata == STATIC_METADATA` parses as a profile; every other partition item parses as a lift day. Whole `Decimal` values become `int`. A missing required field or a non-whole number raises `UnreadableItem`. `OpenLifts` is sorted ascending in the returned model. `count` is `len(items)`. `next_token` is set only when the repository returns a start key. List methods pass `TABLE_TOKEN_KEYS` or `RANKING_TOKEN_KEYS` to `decode_token`.

- [ ] **Step 1: Write the failing test**

```python
from decimal import Decimal
from app.schemas.skilifts import LiftDayPatch, ProfileWrite
from app.services.skilifts import RESORT_LIFT, BadRequest, NotFound, SkiLiftService, UnreadableItem

class FakeRepo:
    def __init__(self, item=None):
        self.item = item
        self.updated = False
    def get_item(self, lift, metadata):
        return self.item
    def update_item(self, lift, metadata, fields):
        self.updated = True
        return self.item
    def put_item(self, item):
        self.item = item
    def delete_item(self, lift, metadata):
        return self.item is not None
    def query_partition(self, lift, limit, start_key):
        return [], None
    def query_rankings(self, lift, limit, start_key):
        return [], None

def test_resort_lift_is_rejected_before_a_write():
    repo = FakeRepo()
    service = SkiLiftService(repo)
    with pytest.raises(BadRequest) as caught:
        service.put_profile(RESORT_LIFT, ProfileWrite(ExperiencedRidersOnly=False, VerticalFeet=1, LiftTime="7:30"))
    assert caught.value.detail == "Resort Data is served under /resort"
    assert repo.item is None

def test_empty_patch_does_not_call_the_repository():
    repo = FakeRepo()
    service = SkiLiftService(repo)
    with pytest.raises(BadRequest) as caught:
        service.patch_lift_day("Lift 3", "01-01-20", LiftDayPatch())
    assert caught.value.detail == "No fields to update"
    assert repo.updated is False

def test_missing_profile_names_the_profile():
    service = SkiLiftService(FakeRepo())
    with pytest.raises(NotFound) as caught:
        service.get_profile("Lift 3")
    assert caught.value.detail == "Profile not found"

def test_decimal_and_open_lifts_become_sorted_ints():
    item = {"Lift": "Resort Data", "Metadata": "03/01/20", "TotalUniqueLiftRiders": Decimal("6000"),
            "AverageSnowCoverageInches": Decimal("40"), "AvalancheDanger": "Low", "OpenLifts": {16, 3, 10, 23}}
    read = SkiLiftService(FakeRepo(item)).get_resort_day("03-01-20")
    assert read.TotalUniqueLiftRiders == 6000
    assert read.OpenLifts == [3, 10, 16, 23]

def test_fractional_number_is_unreadable():
    item = {"Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": Decimal("1.5"),
            "AverageSnowCoverageInches": Decimal("30"), "LiftStatus": "Open", "AvalancheDanger": "Low"}
    with pytest.raises(UnreadableItem):
        SkiLiftService(FakeRepo(item)).get_lift_day("Lift 3", "01-01-20")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_service.py -v`
Expected: FAIL with `ImportError` for `SkiLiftService`

- [ ] **Step 3: Implement `SkiLiftService`**

`PUT` writes the key plus `body.model_dump()`. `PATCH` writes only `exclude_unset` fields. Build read models with `model_validate` after converting numbers, and catch `ValidationError` as `UnreadableItem`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_service.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/services/skilifts.py tests/test_service.py
git commit -m "Add the SkiLifts service."
```

---

### Task 7: Error Handlers

**Files:**
- Create: `app/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: `NotFound`, `BadRequest`, `InvalidToken`
- Produces: `register_exception_handlers(app: FastAPI) -> None`

`NotFound` → 404 with `{"detail": exc.detail}`. `BadRequest` and `InvalidToken` → 400 with `{"detail": exc.detail}`. `RequestValidationError` → 422 with FastAPI's `detail` list (`exc.errors()`). Any other `Exception` → 500 `{"detail": "Internal server error"}`, and the handler logs the exception with `logger.exception`. The response does not include the exception text. Register the specific handlers so they win over the `Exception` handler.

- [ ] **Step 1: Write the failing test**

```python
import logging
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from app.errors import register_exception_handlers
from app.services.skilifts import BadRequest, InvalidToken, NotFound

def test_domain_errors_use_the_spec_bodies():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/missing")
    def missing():
        raise NotFound("Profile not found")

    @app.get("/resort")
    def resort():
        raise BadRequest("Resort Data is served under /resort")

    @app.get("/token")
    def token():
        raise InvalidToken()

    with TestClient(app) as client:
        assert client.get("/missing").status_code == 404
        assert client.get("/missing").json() == {"detail": "Profile not found"}
        assert client.get("/resort").status_code == 400
        assert client.get("/resort").json() == {"detail": "Resort Data is served under /resort"}
        assert client.get("/token").status_code == 400
        assert client.get("/token").json() == {"detail": "Invalid nextToken"}

def test_validation_error_keeps_the_field_loc():
    app = FastAPI()
    register_exception_handlers(app)

    class Body(BaseModel):
        VerticalFeet: int

    @app.post("/feet")
    def feet(body: Body):
        return {}

    with TestClient(app) as client:
        response = client.post("/feet", json={})
    assert response.status_code == 422
    assert ["body", "VerticalFeet"] in [list(err["loc"]) for err in response.json()["detail"]]

def test_unexpected_error_hides_the_message(caplog):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("table is gone")

    with TestClient(app, raise_server_exceptions=False) as client:
        with caplog.at_level(logging.ERROR):
            response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "table is gone" not in response.text
    assert "table is gone" in caplog.text
```

Register `BadRequest` once. `InvalidToken` inherits it. Do not register a handler for `HTTPException`; a missing method must still return 405.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.errors`

- [ ] **Step 3: Implement `register_exception_handlers`**

Return `JSONResponse` for each handler. Do not add routes in this task. Handlers take `(request: Request, exc: <type>)`; name an unused `request` `_request` so ruff `ARG001` passes.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_errors.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/errors.py tests/test_errors.py
git commit -m "Map domain errors to the spec detail bodies."
```

---

### Task 8: App and Lift Routes

**Files:**
- Create: `app/main.py`
- Create: `app/routes/__init__.py`
- Create: `app/routes/lifts.py`
- Create: `tests/conftest.py`
- Test: `tests/test_lifts_api.py`

**Interfaces:**
- Consumes: `create_skilifts_table`, `dynamodb_resource`, `Settings`, `SkiLiftRepository`, `SkiLiftService`, `register_exception_handlers`, `ITEMS`, `DATE_PATTERN`, lift page models
- Produces:
  - `create_app(settings: Settings | None = None) -> FastAPI`
  - module-level `app = create_app()`
  - `router` in `app/routes/lifts.py`, included by `create_app`
  - pytest fixture `client` in `tests/conftest.py`

`create_app` stores settings on `app.state` and, in the lifespan, builds the resource, repository, and `SkiLiftService` on `app.state.service`. Routes read `request.app.state.service` and do not import boto3. `{date}` is `Annotated[str, Path(pattern=DATE_PATTERN)]`. `limit` is `Annotated[int, Query(ge=1, le=100)] = 20` (the `Annotated` form keeps ruff `B008` quiet without an ignore). List responses set `response_model_exclude_none=True`. The function-scoped `client` fixture enters `mock_aws`, sets `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to `testing`, leaves `DYNAMODB_ENDPOINT_URL` unset, creates the table, writes `ITEMS` through `SkiLiftRepository.put_item`, and yields `TestClient` as a context manager. It reseeds `ITEMS` for every test. The `mock_aws` context stays active for the whole test body.

- [ ] **Step 1: Write the failing test**

```python
def test_get_profile_and_day(client):
    profile = client.get("/lifts/Lift%203/profile")
    assert profile.status_code == 200
    assert profile.json() == {
        "Lift": "Lift 3", "Metadata": "Static Data",
        "ExperiencedRidersOnly": False, "VerticalFeet": 1300, "LiftTime": "7:30",
    }
    day = client.get("/lifts/Lift%203/days/01-01-20")
    assert day.status_code == 200
    assert day.json() == {
        "Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": 5000,
        "AverageSnowCoverageInches": 30, "LiftStatus": "Open", "AvalancheDanger": "Low",
    }
    assert isinstance(day.json()["TotalUniqueLiftRiders"], int)
    assert "5000.0" not in day.text
    assert client.get("/lifts/Lift%2010/days/01-01-20").json()["TotalUniqueLiftRiders"] == 0

def test_put_lift_day_replaces(client):
    body = {"TotalUniqueLiftRiders": 1, "AverageSnowCoverageInches": 2, "LiftStatus": "Open", "AvalancheDanger": "Low"}
    created = client.put("/lifts/New%20Lift/days/01-02-20", json=body)
    assert created.status_code == 200
    replaced = client.put("/lifts/New%20Lift/days/01-02-20", json={**body, "LiftStatus": "Closed", "TotalUniqueLiftRiders": 9})
    assert replaced.status_code == 200
    assert replaced.json()["LiftStatus"] == "Closed"
    assert replaced.json()["TotalUniqueLiftRiders"] == 9
    assert client.get("/lifts/New%20Lift/days/01-02-20").json()["LiftStatus"] == "Closed"

def test_put_profile_replaces(client):
    created = client.put("/lifts/New%20Lift/profile", json={"ExperiencedRidersOnly": False, "VerticalFeet": 100, "LiftTime": "4:00"})
    assert created.status_code == 200
    replaced = client.put("/lifts/New%20Lift/profile", json={"ExperiencedRidersOnly": True, "VerticalFeet": 200, "LiftTime": "5:00"})
    assert replaced.status_code == 200
    assert client.get("/lifts/New%20Lift/profile").json()["VerticalFeet"] == 200

def test_lift_partition_order_and_rankings_omit_profile(client):
    page = client.get("/lifts/Lift%203")
    assert [item["Metadata"] for item in page.json()["items"]] == ["01/01/20", "02/01/20", "03/01/20", "Static Data"]
    assert "nextToken" not in page.json()
    rankings = client.get("/lifts/Lift%203/rankings")
    assert [(item["Metadata"], item["TotalUniqueLiftRiders"]) for item in rankings.json()["items"]] == [
        ("02/01/20", 6000), ("03/01/20", 5500), ("01/01/20", 5000),
    ]

def test_unknown_lift_is_an_empty_page(client):
    response = client.get("/lifts/No%20Such")
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}
    assert "nextToken" not in response.json()

def test_limit_one_paginates_without_repeating(client):
    first = client.get("/lifts/Lift%203", params={"limit": 1})
    assert first.json()["count"] == 1
    assert first.json()["items"][0]["Metadata"] == "01/01/20"
    second = client.get("/lifts/Lift%203", params={"limit": 1, "nextToken": first.json()["nextToken"]})
    assert second.json()["items"][0]["Metadata"] == "02/01/20"

def test_limit_defaults_to_20(client):
    for day in range(1, 22):
        response = client.put(
            f"/lifts/Limit%20Lift/days/01-{day:02d}-20",
            json={"TotalUniqueLiftRiders": day, "AverageSnowCoverageInches": 1, "LiftStatus": "Open", "AvalancheDanger": "Low"},
        )
        assert response.status_code == 200
    page = client.get("/lifts/Limit%20Lift")
    assert page.json()["count"] == 20
    assert "nextToken" in page.json()

def test_patch_one_field_preserves_the_others_and_reorders_rankings(client):
    patched = client.patch("/lifts/Lift%203/days/01-01-20", json={"LiftStatus": "Closed"})
    assert patched.status_code == 200
    body = patched.json()
    assert body["LiftStatus"] == "Closed"
    assert body["TotalUniqueLiftRiders"] == 5000
    assert body["AverageSnowCoverageInches"] == 30
    assert body["AvalancheDanger"] == "Low"
    moved = client.patch("/lifts/Lift%2023/days/02-01-20", json={"TotalUniqueLiftRiders": 2000})
    assert moved.status_code == 200
    rankings = client.get("/lifts/Lift%2023/rankings")
    assert [(item["Metadata"], item["TotalUniqueLiftRiders"]) for item in rankings.json()["items"]] == [
        ("02/01/20", 2000), ("03/01/20", 1500), ("01/01/20", 1000),
    ]

def test_lift_errors(client):
    assert client.get("/lifts/Resort%20Data/profile").json() == {"detail": "Resort Data is served under /resort"}
    assert client.get("/lifts/Resort%20Data/profile").status_code == 400
    assert client.patch("/lifts/Lift%203/days/01-01-20", json={}).status_code == 400
    assert client.patch("/lifts/Lift%203/days/01-01-20", json={}).json()["detail"] == "No fields to update"
    missing = client.get("/lifts/Lift%203/days/04-01-20")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Day not found"}
    assert client.get("/lifts/Lift%203/profile").status_code == 200
    assert client.get("/lifts/Missing/profile").status_code == 404
    assert client.get("/lifts/Missing/profile").json() == {"detail": "Profile not found"}
    assert client.patch("/lifts/Lift%203/days/04-01-20", json={"LiftStatus": "Open"}).status_code == 404
    assert client.delete("/lifts/Lift%203/days/04-01-20").status_code == 404
    deleted = client.delete("/lifts/Lift%203/days/02-01-20")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get("/lifts/Lift%203/days/02-01-20").status_code == 404
    assert all(item["Metadata"] != "02/01/20" for item in client.get("/lifts/Lift%203/rankings").json()["items"])
    assert client.patch("/lifts/Lift%203/profile", json={"VerticalFeet": 1}).status_code == 405
    assert client.delete("/lifts/Lift%203/profile").status_code == 405
    feet = client.put("/lifts/Lift%203/profile", json={"ExperiencedRidersOnly": False, "VerticalFeet": 0, "LiftTime": "7:30"})
    assert feet.status_code == 422
    assert ["body", "VerticalFeet"] in [list(err["loc"]) for err in feet.json()["detail"]]

def test_lift_validation_locs(client):
    extra = client.put("/lifts/Lift%203/profile", json={"ExperiencedRidersOnly": False, "VerticalFeet": 1, "LiftTime": "7:30", "Nope": 1})
    assert extra.status_code == 422
    assert ["body", "Nope"] in [list(err["loc"]) for err in extra.json()["detail"]]
    fractional = client.put("/lifts/Lift%203/days/01-01-20", json={"TotalUniqueLiftRiders": 1.5, "AverageSnowCoverageInches": 1, "LiftStatus": "Open", "AvalancheDanger": "Low"})
    assert ["body", "TotalUniqueLiftRiders"] in [list(err["loc"]) for err in fractional.json()["detail"]]
    status = client.put("/lifts/Lift%203/days/01-01-20", json={"TotalUniqueLiftRiders": 1, "AverageSnowCoverageInches": 1, "LiftStatus": "Shut", "AvalancheDanger": "Low"})
    assert ["body", "LiftStatus"] in [list(err["loc"]) for err in status.json()["detail"]]
    bad_date = client.get("/lifts/Lift%203/days/13-01-20")
    assert bad_date.status_code == 422
    assert ["path", "date"] in [list(err["loc"]) for err in bad_date.json()["detail"]]
    bad_limit = client.get("/lifts/Lift%203", params={"limit": 101})
    assert bad_limit.status_code == 422
    assert ["query", "limit"] in [list(err["loc"]) for err in bad_limit.json()["detail"]]
    impossible = client.put("/lifts/Lift%203/days/02-31-20", json={"TotalUniqueLiftRiders": 1, "AverageSnowCoverageInches": 1, "LiftStatus": "Open", "AvalancheDanger": "Low"})
    assert impossible.status_code == 200
    assert impossible.json()["Metadata"] == "02/31/20"

def test_bad_tokens(client):
    ranking = client.get("/lifts/Lift%203/rankings", params={"limit": 1}).json()["nextToken"]
    wrong_route = client.get("/lifts/Lift%203", params={"nextToken": ranking})
    assert wrong_route.status_code == 400
    assert wrong_route.json() == {"detail": "Invalid nextToken"}
    table = client.get("/lifts/Lift%203", params={"limit": 1}).json()["nextToken"]
    wrong_lift = client.get("/lifts/Lift%2010", params={"nextToken": table})
    assert wrong_lift.status_code == 400
    malformed = client.get("/lifts/Lift%203", params={"nextToken": "%%%"})
    assert malformed.status_code == 400

def test_unreadable_stored_day_is_internal_error(client):
    from app.config import Settings
    from app.db import dynamodb_resource
    from app.repositories.skilifts import SkiLiftRepository
    settings = Settings()
    repo = SkiLiftRepository(dynamodb_resource(settings).Table(settings.dynamodb_table_name))
    repo.put_item({"Lift": "Lift 3", "Metadata": "04/01/20", "TotalUniqueLiftRiders": 1})
    response = client.get("/lifts/Lift%203/days/04-01-20")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "TotalUniqueLiftRiders" not in response.text

def test_docs_are_served(client):
    assert client.get("/docs").status_code == 200
```

`Missing` has no seeded profile. The unreadable-item test writes through a second repository while the fixture's `mock_aws` context is still active.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lifts_api.py -v`
Expected: FAIL with `ImportError` for `create_app` or a 404 from missing routes

- [ ] **Step 3: Implement `create_app`, the lift router, and the `client` fixture**

Wire each lift route in spec §6 to the matching service method. `PUT` returns the service model with status 200. `DELETE` returns `Response(status_code=204)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lifts_api.py tests/test_errors.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/routes tests/conftest.py tests/test_lifts_api.py
git commit -m "Serve the lift routes."
```

---

### Task 9: Resort Routes

**Files:**
- Create: `app/routes/resort.py`
- Modify: `app/main.py`
- Test: `tests/test_resort_api.py`

**Interfaces:**
- Consumes: `client` fixture, `SkiLiftService` resort methods, `ResortPage`, `RankingPage`
- Produces: `router` in `app/routes/resort.py`, included from `create_app`

- [ ] **Step 1: Write the failing test**

```python
def test_resort_day_and_sorted_open_lifts(client):
    day = client.get("/resort/days/03-01-20")
    assert day.status_code == 200
    assert day.json() == {
        "Lift": "Resort Data", "Metadata": "03/01/20", "TotalUniqueLiftRiders": 6000,
        "AverageSnowCoverageInches": 40, "AvalancheDanger": "Low", "OpenLifts": [3, 10, 16, 23],
    }
    patched = client.patch("/resort/days/03-01-20", json={"AvalancheDanger": "High"})
    assert patched.status_code == 200
    assert patched.json()["AvalancheDanger"] == "High"
    assert patched.json()["TotalUniqueLiftRiders"] == 6000
    assert patched.json()["AverageSnowCoverageInches"] == 40
    assert patched.json()["OpenLifts"] == [3, 10, 16, 23]
    created = client.put("/resort/days/04-01-20", json={
        "TotalUniqueLiftRiders": 10, "AverageSnowCoverageInches": 2,
        "AvalancheDanger": "Low", "OpenLifts": [3, 3, 10],
    })
    assert created.status_code == 200
    assert created.json()["OpenLifts"] == [3, 10]
    replaced = client.put("/resort/days/04-01-20", json={
        "TotalUniqueLiftRiders": 11, "AverageSnowCoverageInches": 2,
        "AvalancheDanger": "High", "OpenLifts": [1],
    })
    assert replaced.json()["TotalUniqueLiftRiders"] == 11
    assert replaced.json()["AvalancheDanger"] == "High"

def test_resort_rankings_order_and_pagination(client):
    page = client.get("/resort/rankings")
    assert [(item["Metadata"], item["TotalUniqueLiftRiders"]) for item in page.json()["items"]] == [
        ("02/01/20", 6500), ("03/01/20", 6000), ("01/01/20", 5500),
    ]
    first = client.get("/resort/rankings", params={"limit": 1})
    second = client.get("/resort/rankings", params={"limit": 1, "nextToken": first.json()["nextToken"]})
    assert second.status_code == 200
    assert second.json()["items"][0]["Metadata"] == "03/01/20"

def test_resort_days_sort_by_metadata(client):
    page = client.get("/resort/days")
    assert [item["Metadata"] for item in page.json()["items"]] == ["01/01/20", "02/01/20", "03/01/20"]

def test_resort_errors(client):
    assert client.get("/resort/days/04-04-20").status_code == 404
    assert client.get("/resort/days/04-04-20").json() == {"detail": "Resort day not found"}
    assert client.patch("/resort/days/04-04-20", json={"AverageSnowCoverageInches": 1}).status_code == 404
    assert client.delete("/resort/days/04-04-20").status_code == 404
    empty = client.patch("/resort/days/01-01-20", json={})
    assert empty.status_code == 400
    assert empty.json() == {"detail": "No fields to update"}
    blank = client.put("/resort/days/05-01-20", json={
        "TotalUniqueLiftRiders": 1, "AverageSnowCoverageInches": 1,
        "AvalancheDanger": "Low", "OpenLifts": [],
    })
    assert blank.status_code == 422
    assert ["body", "OpenLifts"] in [list(err["loc"]) for err in blank.json()["detail"]]
    deleted = client.delete("/resort/days/01-01-20")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get("/resort/days/01-01-20").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resort_api.py -v`
Expected: FAIL with 404 because the resort routes are not registered

- [ ] **Step 3: Implement the resort router and include it from `create_app`**

Match the lift route status codes. `DELETE` returns an empty 204. List routes use the same `limit` and `nextToken` query parameters as the lift lists.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resort_api.py tests/test_lifts_api.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0 (format, ruff, ty, and the full suite pass)

- [ ] **Step 5: Commit**

```bash
git add app/routes/resort.py app/main.py tests/test_resort_api.py
git commit -m "Serve the resort routes."
```

---

### Task 10: Local Run Tooling

**Files:**
- Create: `scripts/create_table.py`
- Create: `scripts/seed.py`
- Create: `docker-compose.yml`
- Modify: `Makefile`
- Test: `tests/test_scripts.py`

**Interfaces:**
- Consumes: `Settings`, `dynamodb_resource`, `create_skilifts_table`, `SkiLiftRepository`, `ITEMS`, the Makefile from Task 1
- Produces:
  - `main() -> None` in each script, each guarded by `if __name__ == "__main__": main()`
  - Make targets `db-up`, `db-down`, `db-create-table`, `db-seed`, `run`, each with a `## ` help comment. `db-create-table`, `db-seed`, and `run` set `DYNAMODB_ENDPOINT_URL=http://localhost:8000`; `run` is `uv run uvicorn app.main:app --port 3000`.

`create_table.main` creates the table from `Settings`. `seed.main` calls `put_item` for every entry in `ITEMS` and does not delete other keys. `docker-compose.yml` runs `amazon/dynamodb-local`, publishes `8000:8000`, passes `-sharedDb`, and mounts a named volume at the DynamoDB Local data directory. The scripts log nothing noisy; do not use `print` (ruff `T20`).

- [ ] **Step 1: Write the failing test**

```python
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
    repo = SkiLiftRepository(dynamodb_resource(settings).Table(settings.dynamodb_table_name))
    repo.put_item({"Lift": "Extra", "Metadata": "Static Data", "ExperiencedRidersOnly": False, "VerticalFeet": 1, "LiftTime": "1:00"})
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
    repo = SkiLiftRepository(dynamodb_resource(settings).Table(settings.dynamodb_table_name))
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scripts.py -v`
Expected: FAIL with `ModuleNotFoundError` for `scripts.create_table`

- [ ] **Step 3: Implement the scripts, compose file, and Make targets**

Use this compose file:

```yaml
services:
  dynamodb-local:
    image: amazon/dynamodb-local
    ports:
      - "8000:8000"
    working_dir: /home/dynamodblocal
    command: "-jar DynamoDBLocal.jar -sharedDb -dbPath ./data"
    volumes:
      - dynamodb-data:/home/dynamodblocal/data
volumes:
  dynamodb-data:
```

Add the new targets to `.PHONY` in `Makefile`. `db-up` is `docker compose up -d`; `db-down` is `docker compose down`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scripts.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0

- [ ] **Step 5: Commit**

```bash
git add scripts docker-compose.yml Makefile tests/test_scripts.py
git commit -m "Add the local DynamoDB run scripts and Make targets."
```

---

### Task 11: README

**Files:**
- Modify: `README.md`
- Test: `tests/test_readme.py`

**Interfaces:**
- Consumes: `app.main.app` (route table), the `Makefile` targets from Tasks 1 and 10, the settings table in spec §11
- Produces: a README that a new developer can follow from clone to a running API without reading the spec

The README replaces the "spec only" status line. It keeps the link to `docs/superpowers/specs/2026-10-03-skilifts-demo-api-design.md` as the source of truth. Required `##` sections, in order: `Overview`, `Prerequisites`, `Quick start`, `Make targets`, `Configuration`, `API`, `Data model`, `Testing`, `Development`, `Project layout`, `Out of scope`.

Section content:
- **Overview:** what the service is, the three item kinds, the four documented reads, tech stack with links (uv, FastAPI, boto3, pytest, ruff, ty).
- **Prerequisites:** uv, Python 3.14 (uv installs it), Docker for DynamoDB Local only.
- **Quick start:** the five spec §11 commands verbatim, with a note that they assume the project venv is active (`source .venv/bin/activate`) or are prefixed with `uv run`, then the equivalent `make` flow (`make install`, `make db-up`, `make db-create-table`, `make db-seed`, `make run`) and `http://localhost:3000/docs`.
- **Make targets:** a table of every target in the `Makefile` with its help text.
- **Configuration:** the spec §11 settings table plus the credential rule for `DYNAMODB_ENDPOINT_URL`.
- **API:** the route table from spec §6, URL date format, `limit` and `nextToken`, a `curl` example for a `PUT`, a `GET /lifts/Lift%203`, and `GET /resort/rankings`, and the error table from spec §10.
- **Data model:** table and `SkiLiftsByRiders` index, sentinels, the 19 sample items summarized.
- **Testing:** `make test`, `make coverage`, that no Docker or AWS credentials are needed (moto), and that there is no coverage gate.
- **Development:** `make fix_format`, `make lint`, `make type_check`, `make check`, `uv run pre-commit install`, and the CI workflow.
- **Project layout:** a tree of `app/`, `scripts/`, `tests/`, and the top-level files, one line per entry.
- **Out of scope:** spec §13.

- [ ] **Step 1: Write the failing test**

```python
import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
SECTIONS = ["Overview", "Prerequisites", "Quick start", "Make targets", "Configuration", "API", "Data model", "Testing", "Development", "Project layout", "Out of scope"]
SPEC_COMMANDS = [
    "docker compose up -d",
    "DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/create_table.py",
    "DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/seed.py",
    "DYNAMODB_ENDPOINT_URL=http://localhost:8000 uvicorn app.main:app --port 3000",
    "http://localhost:3000/docs",
]


def test_readme_has_every_section_in_order():
    headings = re.findall(r"^## (.+)$", README, re.MULTILINE)
    assert [h for h in headings if h in SECTIONS] == SECTIONS


def test_readme_links_the_spec_and_states_the_spec_commands():
    assert "docs/superpowers/specs/2026-10-03-skilifts-demo-api-design.md" in README
    for command in SPEC_COMMANDS:
        assert command in README
    assert "spec only" not in README.lower()


def test_readme_documents_every_route():
    documented = {(method, route.path) for route in app.routes if route.path.startswith(("/lifts", "/resort")) for method in route.methods}
    assert len(documented) == 14
    for method, path in documented:
        assert f"{method} {path}" in README, (method, path)


def test_readme_documents_every_make_target_and_setting():
    makefile = (ROOT / "Makefile").read_text()
    for target in re.findall(r"^([a-zA-Z_-]+):.*## ", makefile, re.MULTILINE):
        assert f"make {target}" in README or f"`{target}`" in README, target
    for setting in ("DYNAMODB_TABLE_NAME", "AWS_REGION", "DYNAMODB_ENDPOINT_URL", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        assert setting in README
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_readme.py -v`
Expected: FAIL on the section and spec-command assertions

- [ ] **Step 3: Write `README.md`**

Follow the section list above. Take routes, settings, errors, and sample data from the spec; do not restate rules the spec owns beyond what a reader needs to use the API.

- [ ] **Step 4: Run test to verify it passes, then verify from a clean clone**

Run: `uv run pytest tests/test_readme.py -v`
Expected: PASS
Then run: `make fix_format && make check`
Expected: exit 0
Then run: `git clone . /tmp/opencode/skilifts-clean && cd /tmp/opencode/skilifts-clean && uv sync && make check`
Expected: exit 0 with no Docker, no AWS credentials, and no files that are not committed

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_readme.py
git commit -m "Write the project README."
```
