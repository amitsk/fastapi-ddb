# fastify-ddb (Python / FastAPI port) — specification

Date: 2026-10-04 · Status: **spec only, not implemented**
Canonical contract anchor: `fastify-ddb` (TypeScript/Fastify) repo,
`docs/superpowers/specs/2026-10-04-skilifts-polyglot-ports-design.md`.
This repo's spec is self-contained; where it and the TS code disagree, the TS code wins and this spec must be amended.

## 1. Goal

A FastAPI service that is behavior-compatible with the TypeScript `fastify-ddb` SkiLifts API:
same routes, same validation rules, same error envelope, same DynamoDB access patterns,
runnable against local DynamoDB (`amazon/dynamodb-local`), with full repo parity
(API + Dockerfile + compose + table script + tests + native Python CDK stack).

Parity model: **behavioral parity proven by duplicated native tests** (no shared runner).
The fixture vectors in §8 must produce the same outcomes as the TS suite.

## 2. Runtime versions

- Python **3.13**, FastAPI (async), Pydantic **v2**, `pydantic-settings`, `boto3`/`botocore`,
  `slowapi` (rate limit), `pytest` + `httpx` for tests.
- Serve via `uvicorn` (production Dockerfile CMD).

## 3. Module map (TS → Python)

| TS (`src/…`)              | Python (`app/…`)                        |
|---------------------------|-----------------------------------------|
| `config/env.ts`           | `app/config.py` — pydantic-settings, §5 |
| `db/dynamodb.client.ts`   | `app/db/dynamodb.py` — boto3 factory, `GSI_NAME`, `get_table_name()` |
| `types/skilift.types.ts`  | `app/models/skilift.py` — domain shapes |
| `schemas/skilift.schemas.ts` | `app/schemas/skilift.py` — Pydantic request/response models, §6 |
| `repositories/skilift.repository.ts` | `app/repositories/skilift_repository.py`, §7 |
| `services/skilift.service.ts` | `app/services/skilift_service.py` — domain rules only |
| `routes/skilift.routes.ts` + health/ready/root in `server.ts` | `app/routes/skilift.py` (APIRouter) + `app/routes/health.py` |
| `utils/error-handler.ts`  | `app/errors.py` — hierarchy, handlers, `map_aws_error`, §9 |
| `utils/pagination.py` equiv | `app/pagination.py` — canonical tokens, §10 |
| `plugins/dynamodb.plugin.ts` | lifespan in `app/main.py` (build client + service, attach to `app.state`) |
| `server.ts`               | `app/main.py` — `create_app()` factory + middleware, §11 |
| `index.ts`                | `app/__main__.py` — dotenv load, uvicorn run, SIGINT/SIGTERM handling |

## 4. Route table (identical paths, methods, status codes)

| Method | Path | Success | Errors |
|---|---|---|---|
| POST | `/api/skilifts/static` | 201 static item | 400, 409 |
| POST | `/api/skilifts/dynamic` | 201 dynamic item | 400, 409 |
| POST | `/api/skilifts/resort` | 201 resort item | 400, 409 |
| GET | `/api/skilifts` | 200 paginated (Scan) | 400 |
| GET | `/api/skilifts/:lift/by-riders` | 200 paginated (GSI) | 400 |
| PUT | `/api/skilifts/:lift/static` | 200 static item | 400, 404 |
| GET | `/api/skilifts/:lift` | 200 paginated (Query PK) | 400 |
| GET | `/api/skilifts/:lift/:metadata` | 200 item | 404 |
| PUT | `/api/skilifts/:lift/:metadata` | 200 dynamic item | 400, 404 |
| DELETE | `/api/skilifts/:lift/:metadata` | 204 empty | 404 |
| GET | `/health` | 200 `{status,timestamp,uptime}` | — |
| GET | `/ready` | 200 `{status,timestamp}` or 503 `NOT_READY` | 503 |
| GET | `/` | 200 service info (same keys as TS) | — |
| GET | `/docs` | Swagger UI | — |

Static segments must be registered before `/:lift/:metadata` so `by-riders`/`static` are never captured as `:metadata`.

## 5. Environment (names and defaults identical to TS)

`NODE_ENV` (name kept for env-file compatibility), `PORT=3000`, `HOST=0.0.0.0`,
`LOG_LEVEL=info`, `CORS_ORIGIN=*`, `CORS_CREDENTIALS=false`,
`RATE_LIMIT_MAX=100`, `RATE_LIMIT_TIME_WINDOW="1 minute"` (same per-minute semantics),
`DYNAMODB_MODE=local`, `DYNAMODB_TABLE_NAME=SkiLifts`,
`DYNAMODB_LOCAL_ENDPOINT=http://localhost:8000`, `DYNAMODB_LOCAL_REGION=us-east-1`,
`AWS_REGION=us-east-1`, optional `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
(only set explicit creds when **both** present; local mode uses dummy creds).
Invalid env → fail fast at startup with a joined `path: message` error.

## 6. Validation rules (mirror Zod semantics exactly)

- `Lift`: non-empty string. `Metadata` (dynamic/resort): `^\d{2}\/\d{2}\/\d{2}$`.
- `ExperiencedRidersOnly`: strict boolean. `VerticalFeet`: positive number.
  `LiftTime`: `^\d{1,2}:\d{2}$`.
- `TotalUniqueLiftRiders`, `AverageSnowCoverageInches`: non-negative numbers.
- `LiftStatus` ∈ `Open|Closed|Pending`.
  `AvalancheDanger` ∈ `Low|Moderate|Considerable|High|Extreme`.
- `OpenLifts`: list of numbers.
- `limit`: coerce → positive → max 100 → default 20. (Documented divergence: JS-style
  coercions like `0x10` are NOT reproduced; decimal integers only.)
- `nextToken`: opaque string; present-but-malformed → 400 `Invalid nextToken`.
- `lastEvaluatedLift` + `lastEvaluatedMetadata`: both-or-neither, else 400.
- Update bodies with zero defined fields → 400 `No fields to update`.
- `minRiders > maxRiders` → 400.
- Bodies are strict: Pydantic validation failures → 400 envelope with per-field details.

## 7. Repository (table I/O only; domain rules stay in the service)

Table `SkiLifts`: PK `Lift` (S) + SK `Metadata` (S).
GSI `SkiLiftsByRiders`: PK `Lift` (S) + SK `TotalUniqueLiftRiders` (N), projection `ALL`.

- `put_item(..., fail_if_exists=True)` → `attribute_not_exists(Lift) AND attribute_not_exists(Metadata)`;
  `ConditionalCheckFailedException` → **409** `CONFLICT`.
- `get_item` → absent → service raises 404.
- `query_by_lift(lift, limit, next_token)` → `KeyCondition Lift=:lift`.
- `update_item` builds `SET #a=:a` with name placeholders, condition
  `attribute_exists(Lift) AND attribute_exists(Metadata)`, `ReturnValues=ALL_NEW`;
  empty field set → 400; condition failure → 404 (via `map_aws_error`).
- `delete_item` with exists-condition; condition failure → 404.
- `scan_all` (list), `query_by_riders` (GSI, `ScanIndexForward=False`,
  BETWEEN/`>=`/`<=` branches identical to TS), `ping` (`Scan Limit=1 ProjectionExpression=Lift`).
- **Numbers:** boto3 returns `Decimal`. Responses must serialize integral values as JSON
  integers (`2500`, never `2500.0`); `OpenLifts` serializes as a JSON number list.

## 8. Shared fixture vectors (must pass identically here and in TS)

Create-then-read round trips for static/dynamic/resort using:
`Lift="Summit Express"`, `Metadata="01/15/24"`, riders `1250`, snow `48`,
`Open`, `Low`; static `ExperiencedRidersOnly=false, VerticalFeet=2500, LiftTime="8:00"`;
resort `Metadata="01/15/24"`, riders `8500`, snow `42`, `Moderate`, `OpenLifts=[1..12]`;
plus negative cases: invalid bodies → 400 with `details`; double-create → 409;
update/delete absent → 404; empty update → 400; malformed `nextToken` → 400;
`minRiders>maxRiders` → 400; delete → 204 with empty body; `limit` default 20 / cap 100.

## 9. Error envelope (identical)

`{error:{message, code, statusCode, details?}}`, codes:
`NOT_FOUND` 404 · `VALIDATION_ERROR` 400 · `CONFLICT` 409 · `THROTTLED` 503 ·
`DYNAMODB_ERROR` 500 · `INTERNAL_ERROR` 500 (message always `Internal server error`) ·
`REQUEST_ERROR` (4xx framework errors, client message) · `NOT_READY` 503 (`/ready` only).
AWS mapping: `ConditionalCheckFailedException` → 404 except create path → 409;
`ResourceNotFoundException` → 404; throttling pair → 503 `THROTTLED`; else 500.
Unknown errors never leak internals. Unknown routes → 404 `NOT_FOUND` envelope.

## 10. Pagination tokens (canonical)

`nextToken` = base64url (**no padding**) of compact JSON of the DynamoDB
`LastEvaluatedKey` with **keys sorted alphabetically**, UTF-8.
Responses keep the deprecated `lastEvaluatedKey: {Lift, Metadata}` alongside `nextToken`,
plus `count`. Conformance compares tokens by **decoded equivalence**, not raw string.

## 11. App behavior

- `x-request-id`: honor incoming, else uuid4; echo on **all** responses incl. errors.
- CORS: `*` origin forces credentials off (mirror the TS guard).
- GZip for responses ≥ 1024 bytes; security headers equivalent to the TS helmet set
  (conformance asserts at least `x-content-type-options: nosniff` and the configured CSP);
  rate limit 100/min/IP, **disabled** when `NODE_ENV=test`; structured logging at `LOG_LEVEL`
  (JSON in production); native OpenAPI at `/docs`; graceful shutdown on SIGINT/SIGTERM.

## 12. Local run, Docker, CDK

- `docker-compose.yml`: `dynamodb-local` (same image/flags/healthcheck as TS) + `app`
  (uvicorn, `DYNAMODB_LOCAL_ENDPOINT=http://dynamodb-local:8000`, `/health` healthcheck).
- `scripts/create_table.py`: same keys/GSI/throughput as TS `scripts/create-table.ts`;
  idempotent on `ResourceInUse`.
- `Dockerfile`: multi-stage `python:3.13-slim`, non-root user, `EXPOSE`/env parity.
- `cdk/` (native Python `aws-cdk-lib`): mirror `fargate-stack.ts` resource-for-resource —
  table+GSI (`ALL`), VPC lookup, cluster, log group, task def, task-role grant, container env
  (same names), `/health` container check, ALB (`/ready` target check), CPU/memory autoscaling,
  CPU-85 and 5xx alarms + SNS, same outputs.

## 13. Tests

`tests/unit` (schemas, service with stubbed repo/client, error mapping, tokens incl.
malformed, env parsing) + `tests/integration` (HTTP-level via `TestClient` with stubbed
boto3 client: every row of §4/§8). Stub at the botocore layer (`Stubber`), not HTTP.
Coverage thresholds 80% (lines/functions/branches/statements), same as TS.

## 14. Non-goals

No auth, no pagination redesign, no seed script (TS has none), no TS behavior changes
beyond token canonicalization (tracked TS-side prerequisite), no shared-runner harness.

## 15. Acceptance

All suites green at 80%+ coverage; `compose up` + create-table + §8 smoke passes;
`cdk synth` succeeds; header/token/envelope assertions in §§9–11 hold.
