"""Tests for the error handlers: spec bodies, and a body that hides the cause."""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import register_exception_handlers
from app.services.skilifts import BadRequest, InvalidToken, NotFound, UnreadableItem


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
        raise InvalidToken

    with TestClient(app) as client:
        assert client.get("/missing").status_code == 404
        assert client.get("/missing").json() == {"detail": "Profile not found"}
        assert client.get("/resort").status_code == 400
        assert client.get("/resort").json() == {
            "detail": "Resort Data is served under /resort"
        }
        assert client.get("/token").status_code == 400
        assert client.get("/token").json() == {"detail": "Invalid nextToken"}


def test_validation_error_keeps_the_field_loc():
    app = FastAPI()
    register_exception_handlers(app)

    class Body(BaseModel):
        VerticalFeet: int

    @app.post("/feet")
    def feet(_body: Body):
        return {}

    with TestClient(app) as client:
        response = client.post("/feet", json={})
    assert response.status_code == 422
    assert ["body", "VerticalFeet"] in [
        list(err["loc"]) for err in response.json()["detail"]
    ]


def test_unexpected_error_hides_the_message(caplog):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("table is gone")

    with (
        TestClient(app, raise_server_exceptions=False) as client,
        caplog.at_level(logging.ERROR),
    ):
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "table is gone" not in response.text
    assert "table is gone" in caplog.text


def test_unreadable_item_is_an_internal_error(caplog):
    """A stored item that cannot be parsed is a 500, not a 404.

    ``UnreadableItem`` reaches the 500 only because it inherits ``Exception`` and
    no handler is registered for it, so this pins that base class as well: were
    it made a ``NotFound``, or given a handler of its own, a parse failure would
    start answering 404 with an internal message in the body and no other test in
    this file would notice.
    """
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/lifts/{lift}")
    def lift_day(lift: str):
        raise UnreadableItem(f"{lift} cannot be read")

    with (
        TestClient(app, raise_server_exceptions=False) as client,
        caplog.at_level(logging.ERROR),
    ):
        response = client.get("/lifts/Base")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "Base cannot be read" not in response.text
    assert "Base cannot be read" in caplog.text


def test_routing_errors_keep_their_own_status():
    """The catch-all handler must not answer for the router's own errors.

    Starlette raises an ``HTTPException`` for an unknown path and for a wrong
    method, and FastAPI already renders both. A catch-all ``Exception`` handler
    that saw them would turn a 404 and a 405 into 500s and hide real mistakes, so
    a route and an unrouted path are asked for the wrong way round. The bodies
    are asserted as well as the statuses, because only Starlette's own wording
    proves the catch-all left them alone.
    """
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/lifts")
    def lifts():
        return {}

    with TestClient(app) as client:
        wrong_method = client.post("/lifts")
        unknown_path = client.get("/nowhere")
    assert wrong_method.status_code == 405
    assert wrong_method.json() == {"detail": "Method Not Allowed"}
    assert unknown_path.status_code == 404
    assert unknown_path.json() == {"detail": "Not Found"}
