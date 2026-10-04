"""The FastAPI application factory and the ASGI entry point.

``create_app`` wires the layers together once and the routes read the result
from ``app.state``: the router never imports boto3 and never builds a client of
its own, so the transport is the app's decision and a test can swap the settings
by passing them in.

The DynamoDB resource is built in the lifespan rather than at import time, so
importing this module does not open a client. That is what lets the module-level
``app`` below exist for ``uvicorn app.main:app`` while the test suite builds its
own app inside the moto context.

The table is not created here. A table outlives a process, so it is created by
``scripts/create_table.py`` and then reused; creating it on every start would hide
a table that was seeded but is not reachable.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.config import Settings
from app.db import dynamodb_resource
from app.errors import register_exception_handlers
from app.repositories.skilifts import SkiLiftRepository
from app.routes.lifts import router as lifts_router
from app.routes.resort import router as resort_router
from app.services.skilifts import SkiLiftService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the service the routes read, for as long as the app is serving."""
    settings: Settings = app.state.settings
    # ``ServiceResource`` itself carries no ``Table``: boto3's resource factory
    # builds the action at runtime, so the resource is widened once here.
    resource: Any = dynamodb_resource(settings)
    repository = SkiLiftRepository(resource.Table(settings.dynamodb_table_name))
    app.state.service = SkiLiftService(repository)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the SkiLifts app.

    The settings are read once here and stored on ``app.state``; the lifespan
    reads them back from there. Passing them in is how a test or a second app
    gets its own table without touching the environment.
    """
    app = FastAPI(title="SkiLifts API", lifespan=lifespan)
    app.state.settings = Settings() if settings is None else settings
    register_exception_handlers(app)
    app.include_router(lifts_router)
    app.include_router(resort_router)
    return app


app = create_app()
