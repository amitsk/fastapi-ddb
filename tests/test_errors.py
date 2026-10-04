"""Tests for the error handlers: spec bodies, and a body that hides the cause."""

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


def test_routing_errors_keep_their_own_status():
    """The catch-all handler must not answer for the router's own errors.

    Starlette raises an ``HTTPException`` for an unknown path and for a wrong
    method, and FastAPI already renders both. A catch-all ``Exception`` handler
    that saw them would turn a 404 and a 405 into 500s and hide real mistakes, so
    a route and an unrouted path are asked for the wrong way round.
    """
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/lifts")
    def lifts():
        return {}

    with TestClient(app) as client:
        assert client.post("/lifts").status_code == 405
        assert client.get("/nowhere").status_code == 404
