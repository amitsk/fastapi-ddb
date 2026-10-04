# SkiLifts demo API

A small FastAPI service that does CRUD over the `SkiLifts` DynamoDB table and
serves the table's four documented reads. The API process runs on the host and
talks to [DynamoDB Local](https://hub.docker.com/r/amazon/dynamodb-local) in a
container; the test suite needs neither Docker nor AWS credentials.

- **Spec:** `docs/superpowers/specs/2026-10-03-skilifts-demo-api-design.md` (source of truth)

## Overview

Three kinds of item live in the one `SkiLifts` table:

- **profile** — one item per lift, sort key `Static Data`, holding
  `ExperiencedRidersOnly`, `VerticalFeet`, and `LiftTime`
- **lift day** — one item per lift per date, sort key `MM/DD/YY`, holding
  `TotalUniqueLiftRiders`, `AverageSnowCoverageInches`, `LiftStatus`, and
  `AvalancheDanger`
- **resort day** — one item per date in the `Resort Data` partition, the same
  facets minus `LiftStatus` plus the `OpenLifts` number set

Four reads are documented and served:

- all items for one lift, in a single `Query` (`GET /lifts/{lift}`)
- the static profile of one lift (`GET /lifts/{lift}/profile`)
- one day's stats for a lift or for the resort (`GET /lifts/{lift}/days/{date}`,
  `GET /resort/days/{date}`)
- a lift's or the resort's days ordered by rider count, through the
  `SkiLiftsByRiders` index (`GET /lifts/{lift}/rankings`,
  `GET /resort/rankings`)

Stack:

- [uv](https://docs.astral.sh/uv/) — environment and dependency manager
- [FastAPI](https://fastapi.tiangolo.com/) with Pydantic v2 and
  [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) for DynamoDB
- [pytest](https://docs.pytest.org/) with [moto](https://docs.getmoto.org/) and
  FastAPI `TestClient`
- [ruff](https://docs.astral.sh/ruff/) for lint and format
  ([ty](https://github.com/astral-sh/ty) for type checks)

## Prerequisites

- [uv](https://docs.astral.sh/uv/). `uv sync` installs Python **3.14** itself if
  the machine does not have it, so Python is not a separate step.
- Docker, and only for DynamoDB Local. The tests need neither Docker nor AWS
  credentials.

## Quick start

The design spec's local run, verbatim. These five commands assume the project
virtualenv is active (`source .venv/bin/activate`) and that DynamoDB Local is
running:

1. `docker compose up -d`
2. `DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/create_table.py`
3. `DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/seed.py`
4. `DYNAMODB_ENDPOINT_URL=http://localhost:8000 uvicorn app.main:app --port 3000`
5. Open `http://localhost:3000/docs`

The uv-native path needs no activated venv: prefix a command with `uv run`
(`uv run python scripts/seed.py`). The `make` targets in the next section do
exactly that, so the same five steps are:

```console
$ make install          # uv sync
$ make db-up            # docker compose up -d
$ make db-create-table  # DYNAMODB_ENDPOINT_URL=... uv run python scripts/create_table.py
$ make db-seed          # DYNAMODB_ENDPOINT_URL=... uv run python scripts/seed.py
$ make run              # DYNAMODB_ENDPOINT_URL=... uv run uvicorn app.main:app --port 3000
```

Then browse the API at http://localhost:3000/docs. The API process itself runs
on the host and talks to the container through `DYNAMODB_ENDPOINT_URL`.

## Make targets

Every target in the `Makefile`, with the help text `make help` prints.

| Target | What it does |
|---|---|
| `help` | show this help |
| `install` | install the package and dev dependencies |
| `build` | install, lint, type check and test |
| `lint` | Check code with ruff |
| `type_check` | Check type hints with ty |
| `test` | run tests quickly with the default Python |
| `coverage` | check code coverage quickly with the default Python |
| `check` | run all checks without installing |
| `check_format` | check formatting with ruff |
| `fix_format` | format code with ruff |
| `format` | alias for fix_format |
| `clean` | remove all build, test, coverage and Python artifacts |
| `clean-build` | remove build artifacts |
| `clean-pyc` | remove Python file artifacts |
| `clean-test` | remove test and coverage artifacts |
| `db-up` | start DynamoDB Local in the background |
| `db-down` | stop DynamoDB Local and remove the container |
| `db-create-table` | create the configured table on DynamoDB Local |
| `db-seed` | write the sample items into the local table |
| `run` | serve the API on port 3000 against DynamoDB Local |

`check` runs `check_format`, `lint`, `type_check`, and `test`. `make help` is the
default goal, so a bare `make` lists this table.

## Configuration

Settings are read from the environment once, at app creation.

| Setting | Default | Meaning |
|---|---|---|
| `DYNAMODB_TABLE_NAME` | `SkiLifts` | Table name |
| `AWS_REGION` | `us-east-1` | Region passed to boto3 |
| `DYNAMODB_ENDPOINT_URL` | unset | When set, boto3 uses this endpoint |

Credentials:

- When `DYNAMODB_ENDPOINT_URL` is set, the client uses `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY` if both are present, and the access key `local` with
  the secret key `local` if either is absent. That is what lets DynamoDB Local
  run with no AWS setup.
- When `DYNAMODB_ENDPOINT_URL` is unset, the client uses the default AWS
  credential chain and injects no dummy keys.

## API

OpenAPI, with a try-it-out UI, is served at `/docs`. The API listens on port
**3000**.

A date in a URL is one path segment in `MM-DD-YY` form. The service stores and
returns the sort key as `MM/DD/YY`, so `01-01-20` in the path is `01/01/20` in
the table and in JSON. `{lift}` is the decoded path string and becomes the
partition key; a lift of `Resort Data` on a `/lifts/...` route is a `400`.

| Route | Success | Other |
|---|---|---|
| `PUT /lifts/{lift}/profile` | `200` profile | `400` when `{lift}` is `Resort Data`, `422` |
| `GET /lifts/{lift}/profile` | `200` profile | `404` |
| `PUT /lifts/{lift}/days/{date}` | `200` lift day | `400`, `422` |
| `GET /lifts/{lift}/days/{date}` | `200` lift day | `404` |
| `PATCH /lifts/{lift}/days/{date}` | `200` lift day | `400` empty body, `404`, `422` |
| `DELETE /lifts/{lift}/days/{date}` | `204` empty body | `404` |
| `GET /lifts/{lift}` | `200` page of profiles and lift days, sort-key order | `400` bad token |
| `GET /lifts/{lift}/rankings` | `200` rankings page, highest rider count first | `400` bad token |
| `PUT /resort/days/{date}` | `200` resort day | `422` |
| `GET /resort/days/{date}` | `200` resort day | `404` |
| `PATCH /resort/days/{date}` | `200` resort day | `400` empty body, `404`, `422` |
| `DELETE /resort/days/{date}` | `204` empty body | `404` |
| `GET /resort/days` | `200` page of resort days, sort-key order | `400` bad token |
| `GET /resort/rankings` | `200` rankings page for `Lift = "Resort Data"` | `400` bad token |

Bodies carry facet fields only; the keys come from the path and are echoed in
the response. `PUT` requires every facet field and replaces the item, returning
`200` and the stored item for both a new item and a replacement. `PATCH` takes
one or more daily fields and leaves the rest in place. There is no profile
`PATCH` and no profile `DELETE`.

The three list routes take `limit`, an integer from 1 to 100 that defaults to
20, and an optional `nextToken`. A list response is `{"items": [...], "count": n}`
where `count` is the size of this page, and `nextToken` is present only when
DynamoDB returned a `LastEvaluatedKey`. An empty partition returns `200` and an
empty page.

Date sort keys sort before `Static Data`, so the seeded `Lift 3` partition reads
`01/01/20`, `02/01/20`, `03/01/20`, then the profile. Rankings items are
`{"Lift", "Metadata", "TotalUniqueLiftRiders"}`.

Examples, against a seeded local table:

```console
$ curl -X PUT http://localhost:3000/lifts/Lift%203/days/01-01-20 \
    -H 'Content-Type: application/json' \
    -d '{"TotalUniqueLiftRiders": 5000, "AverageSnowCoverageInches": 30, "LiftStatus": "Open", "AvalancheDanger": "Low"}'
$ curl 'http://localhost:3000/lifts/Lift%203?limit=2'
$ curl 'http://localhost:3000/resort/rankings'
```

Errors use FastAPI's `detail` field.

| Status | When | Body |
|---|---|---|
| `422` | A field, `{date}`, or `limit` fails validation | FastAPI `detail` list |
| `400` | `{lift}` is `Resort Data` | `{"detail": "Resort Data is served under /resort"}` |
| `400` | `PATCH` sets no fields | `{"detail": "No fields to update"}` |
| `400` | `nextToken` is present and unusable | `{"detail": "Invalid nextToken"}` |
| `404` | Profile is absent | `{"detail": "Profile not found"}` |
| `404` | Lift day is absent, including `PATCH` and `DELETE` | `{"detail": "Day not found"}` |
| `404` | Resort day is absent, including `PATCH` and `DELETE` | `{"detail": "Resort day not found"}` |
| `500` | Unexpected failure, a DynamoDB client error, a missing table, or a stored item that cannot be parsed as the expected kind | `{"detail": "Internal server error"}` |

## Data model

One table, `SkiLifts`, billing mode on-demand (`PAY_PER_REQUEST`).

| Role | Attribute | Type |
|---|---|---|
| Partition key | `Lift` | `S` |
| Sort key | `Metadata` | `S` |

Global secondary index `SkiLiftsByRiders`: partition key `Lift` (`S`), sort key
`TotalUniqueLiftRiders` (`N`), projection `INCLUDE` with the non-key attribute
`Metadata`. A query therefore returns `Lift`, `TotalUniqueLiftRiders`, and
`Metadata` only. A profile has no `TotalUniqueLiftRiders`, so it never appears
in the index; updating a day's rider count moves that day within the index, and
deleting the day removes it.

Two sentinel values live in the service module and drive the whole model:

- `STATIC_METADATA = "Static Data"` — the sort key of a profile
- `RESORT_LIFT = "Resort Data"` — the partition key of the resort days

`make db-seed` writes the 19 sample items from `app/data/sample.py` with `PutItem`:
4 profiles (Lift 3, Lift 23, Lift 16, Lift 10), 12 lift days (those four lifts
across `01/01/20`, `02/01/20`, and `03/01/20`), and 3 resort days (the same
three dates). Seeding again replaces those keys and leaves other items alone.
With that data, `GET /resort/rankings` returns `02/01/20` (6500), `03/01/20`
(6000), then `01/01/20` (5500).

Rows generated outside this API — one that sets every attribute at once, uses a
non-date `Metadata`, or puts decimals into `OpenLifts` — are not part of the
demo data. A read that finds such a stored item fails with `500`.

## Testing

```console
$ make test       # uv run pytest tests/ -v
$ make coverage   # coverage report plus HTML in coverage_html_report/
```

The suite needs neither Docker nor AWS credentials: `moto` provides DynamoDB, and
each test builds its own app inside the moto context. There is no coverage
percentage gate, so a drop in coverage does not fail the build.

## Development

```console
$ make fix_format   # format code with ruff
$ make lint         # ruff check
$ make type_check   # ty check app scripts
$ make check        # check_format + lint + type_check + test
$ uv run pre-commit install
```

CI runs the same gate: `.github/workflows/python-tests.yml` installs uv with
Python 3.14 on every push and pull request, runs `make install`, then
`make check`.

## Project layout

```text
app/main.py                       create_app() factory and the uvicorn entry point
app/config.py                     environment settings
app/db.py                         boto3 resource, table creation, index definition
app/errors.py                     domain, validation, and unexpected-error handlers
app/data/__init__.py              data package marker
app/data/sample.py                the 19 demo items
app/schemas/__init__.py           schema package marker
app/schemas/skilifts.py           Pydantic models, one per item kind, plus the page
app/services/__init__.py          service package marker
app/services/skilifts.py          sentinels, dates, tokens, Decimal handling, domain errors
app/repositories/__init__.py      repository package marker
app/repositories/skilifts.py      DynamoDB calls, no HTTP status codes
app/routes/__init__.py            route package marker
app/routes/lifts.py               /lifts/... routes
app/routes/resort.py              /resort/... routes
scripts/__init__.py               scripts package marker
scripts/create_table.py           create the table and the index on DynamoDB Local
scripts/seed.py                   write the sample items
tests/conftest.py                 moto-backed app and seeded-table fixtures
tests/test_config.py              settings defaults and the credential rule
tests/test_errors.py              error mapping for domain, validation, and other failures
tests/test_lifts_api.py           the /lifts/... routes end to end
tests/test_readme.py              asserts this README stays complete
tests/test_repository.py          DynamoDB calls and the table and index definition
tests/test_resort_api.py          the /resort/... routes end to end
tests/test_schemas.py             field rules and the 19 sample items
tests/test_scripts.py             create_table and seed, plus the compose and run targets
tests/test_service.py             sentinels, conversions, and domain errors
tests/test_tokens.py              pagination token encoding and validation
tests/test_tooling.py             toolchain expectations for the Makefile and pyproject
Makefile                          install, checks, and the local DynamoDB run
docker-compose.yml                amazon/dynamodb-local on port 8000
pyproject.toml                    dependencies and the ruff, pytest, coverage config
uv.lock                           pinned dependency versions
.pre-commit-config.yaml           pre-commit hooks
.mise.toml                        pins Python 3.14 for mise users
.gitignore                        ignores .venv, __pycache__, .coverage, and .worktrees
.github/workflows/python-tests.yml  CI: make install then make check
docs/superpowers/specs/2026-10-03-skilifts-demo-api-design.md  the spec, source of truth
```

## Out of scope

Auth, a deploy stack, rate limiting, security-header middleware, request ids,
CORS middleware, response compression, profile `PATCH`, profile `DELETE`, a
rider-range filter on rankings, a custom error envelope, and importing
Workbench-generated rows.