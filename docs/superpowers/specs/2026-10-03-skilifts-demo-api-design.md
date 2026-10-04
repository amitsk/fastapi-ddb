# SkiLifts demo API — design

Date: 2026-10-03 · Status: **spec only, not implemented**

This document is the source of truth for the repo. It describes a demo CRUD API for the `SkiLifts` DynamoDB table.

## 1. Goal

A small FastAPI service that creates, reads, updates, and deletes the three item kinds stored in `SkiLifts`, and that serves the table's documented reads:

- all items for one lift, in one `Query`
- the static profile of one lift
- one day's stats for a lift or for the resort
- a lift's or the resort's days ordered by rider count, through `SkiLiftsByRiders`

Someone can run it against DynamoDB Local, load the 19 sample items in §5, and exercise every route from `/docs`.

Success means the tests in §12 pass and the local run in §11 returns those sample items.

## 2. Runtime

- Python **3.14**
- FastAPI, Pydantic v2, pydantic-settings, boto3, uvicorn
- Tests: pytest, moto, and FastAPI `TestClient`. `TestClient` depends on the `httpx2` package.

The app listens on port **3000**. DynamoDB Local listens on port **8000**.

## 3. Modules

| Module | Responsibility |
|---|---|
| `app/main.py` | `create_app()` factory, also bound as module-level `app` for uvicorn. Startup builds the table handle, repository, and service and stores them on `app.state`. |
| `app/config.py` | Settings in §11. |
| `app/db.py` | boto3 DynamoDB resource and table handle from settings. |
| `app/schemas/` | One Pydantic model per item kind, plus the page model. Extra fields are forbidden. |
| `app/services/skilifts.py` | Sentinel keys, date conversion, pagination tokens, `Decimal` conversion, domain errors. |
| `app/repositories/skilifts.py` | DynamoDB calls in §8. No HTTP status codes. |
| `app/routes/lifts.py` | `/lifts/...` routes. |
| `app/routes/resort.py` | `/resort/...` routes. |
| `app/errors.py` | Map domain errors, request-validation errors, and unexpected failures to the bodies in §10. |
| `app/sample.py` | The 19 items in §5. |
| `scripts/create_table.py` | Create the table and index in §4. |
| `scripts/seed.py` | `PutItem` every item in `app/sample.py`. |

Routes depend on the service. The service depends on the repository. The repository depends on the table handle. Schemas depend on nothing else in the app. Routes do not import boto3.

Sentinel constants live in the service module:

- `STATIC_METADATA = "Static Data"`
- `RESORT_LIFT = "Resort Data"`
- `GSI_NAME = "SkiLiftsByRiders"`

## 4. Table

One table, `SkiLifts`. Billing mode is on-demand (`PAY_PER_REQUEST`).

| Role | Attribute | Type |
|---|---|---|
| Partition key | `Lift` | `S` |
| Sort key | `Metadata` | `S` |

Non-key attributes:

| Attribute | Type | Used by |
|---|---|---|
| `ExperiencedRidersOnly` | `BOOL` | profile |
| `VerticalFeet` | `N` | profile |
| `LiftTime` | `S` | profile |
| `TotalUniqueLiftRiders` | `N` | lift day, resort day |
| `AverageSnowCoverageInches` | `N` | lift day, resort day |
| `LiftStatus` | `S` | lift day |
| `AvalancheDanger` | `S` | lift day, resort day |
| `OpenLifts` | `NS` | resort day |

Global secondary index `SkiLiftsByRiders`:

- Partition key `Lift` (`S`), sort key `TotalUniqueLiftRiders` (`N`)
- Projection `INCLUDE`, non-key attribute `Metadata`
- A query returns `Lift`, `TotalUniqueLiftRiders`, and `Metadata`
- A profile has no `TotalUniqueLiftRiders`, so a profile never appears in this index
- Updating `TotalUniqueLiftRiders` moves that day within the index
- Deleting a day removes it from the index

`scripts/create_table.py` creates the table and the index. When the table already exists (`ResourceInUseException`), the script exits 0 and leaves the table unchanged.

## 5. Item kinds and sample data

Three kinds. Attribute names in JSON are the table attribute names.

A **profile** is one item per lift. Its sort key is the literal `Static Data`.

| Lift | ExperiencedRidersOnly | VerticalFeet | LiftTime |
|---|---|---|---|
| Lift 3 | false | 1300 | 7:30 |
| Lift 23 | true | 900 | 5:45 |
| Lift 16 | false | 1500 | 9:00 |
| Lift 10 | true | 1000 | 6:00 |

A **lift day** is one item per lift per date. `Metadata` is `MM/DD/YY`.

| Lift | Metadata | TotalUniqueLiftRiders | AverageSnowCoverageInches | LiftStatus | AvalancheDanger |
|---|---|---|---|---|---|
| Lift 3 | 01/01/20 | 5000 | 30 | Open | Low |
| Lift 23 | 01/01/20 | 1000 | 45 | Open | Considerable |
| Lift 16 | 01/01/20 | 4500 | 35 | Open | Low |
| Lift 10 | 01/01/20 | 0 | 40 | Pending | High |
| Lift 3 | 02/01/20 | 6000 | 35 | Open | Low |
| Lift 23 | 02/01/20 | 0 | 50 | Closed | Extreme |
| Lift 16 | 02/01/20 | 5500 | 40 | Open | Low |
| Lift 10 | 02/01/20 | 3500 | 45 | Open | Moderate |
| Lift 3 | 03/01/20 | 5500 | 35 | Open | Low |
| Lift 23 | 03/01/20 | 1500 | 45 | Open | Moderate |
| Lift 16 | 03/01/20 | 4000 | 40 | Open | Low |
| Lift 10 | 03/01/20 | 2500 | 45 | Open | Moderate |

A **resort day** uses partition key `Resort Data`. It has no `LiftStatus`. `OpenLifts` is a number set.

| Metadata | TotalUniqueLiftRiders | AverageSnowCoverageInches | AvalancheDanger | OpenLifts |
|---|---|---|---|---|
| 01/01/20 | 5500 | 35 | Considerable | 3, 23, 16 |
| 02/01/20 | 6500 | 45 | Moderate | 3, 16, 10 |
| 03/01/20 | 6000 | 40 | Low | 3, 23, 16, 10 |

`scripts/seed.py` writes these 19 items with `PutItem`. Running it again replaces those keys. It does not delete other items.

These 19 items are the demo data. Workbench-generated rows that set every attribute at once, use a non-date `Metadata`, or put decimals into `OpenLifts` are outside this API. A read that finds a stored item it cannot parse as the expected kind returns `500` (§10).

## 6. HTTP API

A date in a URL is one path segment, `MM-DD-YY`. The service stores and returns the sort key as `MM/DD/YY`. `01-01-20` in the path is `01/01/20` in the table and in JSON.

`{lift}` is the decoded path string, used as the partition key. It contains at least one character. On every `/lifts/...` route, a lift equal to `Resort Data` returns `400` with `{"detail": "Resort Data is served under /resort"}`.

Request bodies carry facet fields only. Keys come from the path and are echoed in the response. `PUT` requires every facet field and replaces the item. `PUT` returns `200` and the stored item for both a new item and a replacement. `PATCH` accepts one or more daily fields and leaves the others in place. There is no profile `PATCH` and no profile `DELETE`.

`limit` defaults to 20 and is an integer from 1 to 100. `nextToken` is optional. A list response is:

```json
{ "items": [], "count": 0 }
```

`count` is the number of items in this page. `nextToken` is present only when DynamoDB returns a `LastEvaluatedKey`. A lift or resort partition with no items returns `200` and an empty page.

| Method | Path | Success | Other |
|---|---|---|---|
| `PUT` | `/lifts/{lift}/profile` | `200` profile | `400` when `{lift}` is `Resort Data`, `422` |
| `GET` | `/lifts/{lift}/profile` | `200` profile | `404` |
| `PUT` | `/lifts/{lift}/days/{date}` | `200` lift day | `400`, `422` |
| `GET` | `/lifts/{lift}/days/{date}` | `200` lift day | `404` |
| `PATCH` | `/lifts/{lift}/days/{date}` | `200` lift day | `400` empty body, `404`, `422` |
| `DELETE` | `/lifts/{lift}/days/{date}` | `204` empty body | `404` |
| `GET` | `/lifts/{lift}` | `200` page of profiles and lift days, sort-key order | `400` bad token |
| `GET` | `/lifts/{lift}/rankings` | `200` rankings page, highest rider count first | `400` bad token |
| `PUT` | `/resort/days/{date}` | `200` resort day | `422` |
| `GET` | `/resort/days/{date}` | `200` resort day | `404` |
| `PATCH` | `/resort/days/{date}` | `200` resort day | `400` empty body, `404`, `422` |
| `DELETE` | `/resort/days/{date}` | `204` empty body | `404` |
| `GET` | `/resort/days` | `200` page of resort days, sort-key order | `400` bad token |
| `GET` | `/resort/rankings` | `200` rankings page for `Lift = "Resort Data"` | `400` bad token |

Date keys sort before `Static Data`. The seeded partition `Lift 3` returns `01/01/20`, `02/01/20`, `03/01/20`, then the profile.

A rankings item is `{ "Lift", "Metadata", "TotalUniqueLiftRiders" }`. For the seeded resort, the order is `02/01/20` (6500), `03/01/20` (6000), `01/01/20` (5500). Equal rider counts keep DynamoDB's order among those ties. Rankings have no minimum or maximum rider filter.

Profile response:

```json
{
  "Lift": "Lift 3",
  "Metadata": "Static Data",
  "ExperiencedRidersOnly": false,
  "VerticalFeet": 1300,
  "LiftTime": "7:30"
}
```

Lift-day response:

```json
{
  "Lift": "Lift 3",
  "Metadata": "01/01/20",
  "TotalUniqueLiftRiders": 5000,
  "AverageSnowCoverageInches": 30,
  "LiftStatus": "Open",
  "AvalancheDanger": "Low"
}
```

Resort-day response. `OpenLifts` is sorted ascending, so the seeded `03/01/20` set is returned as `[3, 10, 16, 23]`.

```json
{
  "Lift": "Resort Data",
  "Metadata": "03/01/20",
  "TotalUniqueLiftRiders": 6000,
  "AverageSnowCoverageInches": 40,
  "AvalancheDanger": "Low",
  "OpenLifts": [3, 10, 16, 23]
}
```

OpenAPI is served at `/docs`.

## 7. Validation

Bodies forbid extra fields. JSON `null` is rejected. Numbers are integers, serialized as JSON integers (`5000`, never `5000.0`).

| Field | Rule |
|---|---|
| `ExperiencedRidersOnly` | boolean |
| `VerticalFeet` | integer ≥ 1 |
| `LiftTime` | `^\d{1,2}:\d{2}$` |
| `TotalUniqueLiftRiders` | integer ≥ 0 |
| `AverageSnowCoverageInches` | integer ≥ 0 |
| `LiftStatus` | `Open`, `Closed`, or `Pending` |
| `AvalancheDanger` | `Low`, `Moderate`, `Considerable`, `High`, or `Extreme` |
| `OpenLifts` | one or more integers, each ≥ 0 |

`OpenLifts` is stored as a number set, which collapses duplicates. Responses return the values sorted ascending. An empty list is invalid because DynamoDB rejects an empty number set; the API returns `422`.

`{date}` matches month `01`–`12`, day `01`–`31`, and a two-digit year: `^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])-[0-9]{2}$`. The pattern does not reject impossible calendar days such as `02-31-20`.

A profile `PUT` requires `ExperiencedRidersOnly`, `VerticalFeet`, and `LiftTime`. A lift-day `PUT` requires the four lift-day fields. A resort-day `PUT` requires `TotalUniqueLiftRiders`, `AverageSnowCoverageInches`, `AvalancheDanger`, and `OpenLifts`. A `PATCH` body uses the same field rules, with every field optional, and the service rejects a body that sets nothing.

A bad body, `{date}`, or `limit` returns `422` with FastAPI's `detail` list (`loc`, `msg`, `type`). Tests assert the status code and the `loc` entry. They do not assert the Pydantic message text.

## 8. DynamoDB operations

| Call | Operation | Rule |
|---|---|---|
| Profile, lift-day, or resort-day `PUT` | `PutItem` of the key plus every facet field | Replaces the whole item. Attributes that belong to another kind are removed. |
| `GET` one item | `GetItem` | A missing item becomes `404`. |
| `PATCH` | `UpdateItem` with `SET` of the sent fields only, `ReturnValues=ALL_NEW` | Condition `attribute_exists(Lift) AND attribute_exists(Metadata)`. A failed condition becomes `404`. |
| `DELETE` | `DeleteItem` with the same condition | A failed condition becomes `404`. |
| `GET /lifts/{lift}` and `GET /resort/days` | `Query` `Lift = :lift`, ascending sort key | No filter. |
| Rankings | `Query` on `SkiLiftsByRiders`, `ScanIndexForward=false` | `GET /resort/rankings` queries `Lift = "Resort Data"`. |

The service converts a path date to a slash date before the repository call. A `PATCH` with no fields raises in the service and does not call DynamoDB.

boto3 returns numbers as `Decimal`. The service converts a whole number to `int` before building the response. A profile, lift-day, or resort-day read whose stored item is missing a required field, or whose number is not a whole number, fails the request with `500`. A rankings item needs only a string `Metadata` and a whole-number `TotalUniqueLiftRiders`, which is the shape the index projects.

`GET /lifts/{lift}` parses an item with `Metadata = "Static Data"` as a profile and every other item in that partition as a lift day. `GET /resort/days` parses every item as a resort day.

## 9. Pagination tokens

`nextToken` is unpadded base64url of the UTF-8 JSON object for `LastEvaluatedKey`. Object keys are sorted alphabetically. JSON uses compact separators (`,` and `:`) and integers for numbers.

A table page encodes `Lift` and `Metadata`. A rankings page encodes `Lift`, `Metadata`, and `TotalUniqueLiftRiders`.

Example table key `{"Lift":"Lift 3","Metadata":"01/01/20"}`.

The service accepts a token only when it decodes to an object whose keys are exactly the set required by that route, `Lift` and `Metadata` are strings, `TotalUniqueLiftRiders` is a JSON integer when present, and `Lift` equals the partition being queried. Any other token raises an invalid-token error. The repository receives `Lift` and `Metadata` as strings and `TotalUniqueLiftRiders` as an integer, and it converts that integer to `Decimal` for `ExclusiveStartKey`.

## 10. Errors

Error bodies use FastAPI's `detail` field.

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

The `500` handler logs the exception. The response body is only the message above.

The service raises `NotFound`, `BadRequest`, and `InvalidToken`. The repository reports a missing item or a failed existence condition as an empty result. `app/errors.py` turns `RequestValidationError` into the `422` body, the domain errors into `400` and `404`, and any other exception into the `500` body.

## 11. Configuration and local run

| Setting | Default | Meaning |
|---|---|---|
| `DYNAMODB_TABLE_NAME` | `SkiLifts` | Table name |
| `AWS_REGION` | `us-east-1` | Region passed to boto3 |
| `DYNAMODB_ENDPOINT_URL` | unset | When set, boto3 uses this endpoint |

When `DYNAMODB_ENDPOINT_URL` is set, the client uses `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` if both are present. If either is absent, it uses the access key `local` and the secret key `local`. When the endpoint is unset, the client uses the default AWS credential chain and does not inject dummy keys.

`docker-compose.yml` runs `amazon/dynamodb-local` only. It publishes host port 8000, uses `-sharedDb`, and stores the database files on a persisted volume so a container restart keeps the table and the seed.

Local run:

1. `docker compose up -d`
2. `DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/create_table.py`
3. `DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/seed.py`
4. `DYNAMODB_ENDPOINT_URL=http://localhost:8000 uvicorn app.main:app --port 3000`
5. Open `http://localhost:3000/docs`

The API process runs on the host. The README states these steps and describes this demo.

## 12. Tests

Tests use `TestClient` and moto. The test environment installs `httpx2`, which is the HTTP library `TestClient` imports. `create_app()` runs inside the moto context, so the suite does not need Docker. The fixture loads `app/sample.py` through the API or the repository.

Required cases:

- Each route's success status and body, using the sample items.
- Profile, lift-day, and resort-day `PUT` creates an item, and a second `PUT` replaces it.
- `422` for an extra field, a non-integer, a bad enum, an empty `OpenLifts`, a bad `{date}`, and a `limit` outside 1–100. Assert the status and the field `loc`.
- `400` for `Resort Data` on a lift route, an empty `PATCH`, and a malformed, mismatched, or wrong-lift `nextToken`, with the messages in §10.
- `404` for a missing profile, lift day, and resort day, including `PATCH` and `DELETE`.
- `DELETE` of an existing day returns `204` with an empty body, and a following `GET` returns `404`.
- `GET /lifts/Lift%203` returns `01/01/20`, `02/01/20`, `03/01/20`, then `Metadata = "Static Data"`, in that order.
- `GET /resort/rankings` returns `02/01/20` (6500), `03/01/20` (6000), `01/01/20` (5500).
- `GET /lifts/Lift%203/days/01-01-20` returns `Metadata` `01/01/20`.
- Seeded resort `OpenLifts` are returned sorted ascending.
- `limit=1` on `GET /lifts/Lift%203` returns one item and a `nextToken`. The following page continues in order and does not repeat that item.
- `PATCH /lifts/Lift%2023/days/02-01-20` with `{"TotalUniqueLiftRiders": 2000}` makes `GET /lifts/Lift%2023/rankings` return `02/01/20` (2000), `03/01/20` (1500), `01/01/20` (1000).

There is no coverage percentage gate.

## 13. Out of scope

Auth, a deploy stack, rate limiting, security-header middleware, request ids, CORS middleware, response compression, profile `PATCH`, profile `DELETE`, a rider-range filter on rankings, a custom error envelope, and importing Workbench-generated rows.

## 14. Acceptance

The implementation matches this document. `pytest` passes the cases in §12. The local run in §11 serves the 19 sample items, including the `Lift 3` partition order and the resort rankings order in §6.
