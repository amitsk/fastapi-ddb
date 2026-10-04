"""Map the domain and framework errors to the bodies the spec fixes.

``app/services/skilifts.py`` raises ``NotFound``, ``BadRequest``, and
``InvalidToken`` without knowing HTTP, and the framework raises
``RequestValidationError`` before a route is even called. This module is the
only place that knows which status each of them becomes, so the routes stay free
of status codes and of try/except noise.

``HTTPException`` is deliberately left alone: an unknown path and a wrong method
are Starlette's own errors, and FastAPI already renders them as a 404 and a 405.
Registering a handler for ``HTTPException`` here would swallow those, and
replacing them with a generic 500 would hide a wrong URL as a server fault.

The catch-all ``Exception`` handler is the last resort for everything else, and
it says nothing about the cause: the exception is logged with its traceback and
the response body is the fixed ``Internal server error`` message, so a DynamoDB
message, a missing table, or a stored item that cannot be parsed never reaches a
client.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.services.skilifts import BadRequest, NotFound

logger = logging.getLogger(__name__)


async def _not_found(_request: Request, exc: NotFound) -> JSONResponse:
    """Answer 404 with the message the service attached to the error."""
    return JSONResponse(status_code=404, content={"detail": exc.detail})


async def _bad_request(_request: Request, exc: BadRequest) -> JSONResponse:
    """Answer 400 with the message the service attached to the error.

    ``InvalidToken`` inherits ``BadRequest``, so one handler covers both and the
    token error keeps its ``Invalid nextToken`` detail.
    """
    return JSONResponse(status_code=400, content={"detail": exc.detail})


async def _validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Answer 422 with FastAPI's own list of field errors.

    The list is encoded rather than passed through because an error entry can
    hold a ``ValueError`` in its context, which is not JSON.
    """
    return JSONResponse(
        status_code=422, content={"detail": jsonable_encoder(exc.errors())}
    )


async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
    """Answer 500 with a fixed message, logging the real cause.

    Starlette installs this handler on its outermost middleware, so it only sees
    exceptions the router and its own handlers did not already answer.
    """
    logger.exception("Unhandled error while serving the request: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _register[ExcT: Exception](
    app: FastAPI,
    exc_type: type[ExcT],
    handler: Callable[[Request, ExcT], Awaitable[Response]],
) -> None:
    """Register ``handler`` as the handler for ``exc_type``, keeping its types.

    Starlette types an exception handler as taking any ``Exception``, but it
    looks one up by walking the bases of what was actually raised, so a handler
    that names the exception it answers is only ever called with that exception.
    The wrapper states that once in types rather than casting at every
    registration, and re-raises anything else rather than answering wrongly.
    """

    async def dispatch(request: Request, exc: Exception) -> Response:
        if isinstance(exc, exc_type):
            return await handler(request, exc)
        raise exc

    app.add_exception_handler(exc_type, dispatch)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the error handlers to ``app``.

    Each error is looked up by walking the raised exception's own bases, so the
    handlers registered for ``NotFound`` and ``BadRequest`` win over the
    catch-all whatever order they are added in.
    """
    _register(app, NotFound, _not_found)
    _register(app, BadRequest, _bad_request)
    _register(app, RequestValidationError, _validation_error)
    _register(app, Exception, _unhandled)
