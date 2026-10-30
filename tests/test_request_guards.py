"""The Host, Origin and content type guards in front of every route."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.request_guards import RequestGuardMiddleware, host_name

UI_ORIGIN = "http://localhost:5173"
JSON_HEADERS = {"Content-Type": "application/json"}
FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


def make_client(base_url: str = "http://localhost:8000") -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RequestGuardMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "crawl.example"],
        allowed_origins=[UI_ORIGIN],
        allowed_origin_pattern=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    )

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/stop")
    def stop() -> dict[str, bool]:
        return {"stopped": True}

    @app.delete("/thing")
    def delete_thing() -> dict[str, bool]:
        return {"deleted": True}

    return TestClient(app, base_url=base_url)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("localhost", "localhost"),
        ("LocalHost:8000", "localhost"),
        ("127.0.0.1:8000", "127.0.0.1"),
        ("[::1]:8000", "[::1]"),
        ("[::1]", "[::1]"),
        ("evil.example:8000", "evil.example"),
        ("", ""),
    ],
)
def test_host_name_drops_the_port_and_keeps_ipv6_brackets(header, expected):
    assert host_name(header) == expected


@pytest.mark.parametrize(
    "base_url",
    ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000", "http://crawl.example"],
)
def test_local_and_configured_hosts_are_answered(base_url):
    assert make_client(base_url).get("/ping").status_code == 200


@pytest.mark.parametrize(
    "base_url",
    ["http://evil.example:8000", "http://localhost.evil.example", "http://10.0.0.5:8000"],
)
def test_other_hosts_get_421_even_for_a_read(base_url):
    reply = make_client(base_url).get("/ping")
    assert reply.status_code == 421
    assert "localhost" in reply.json()["detail"]


def test_a_cross_site_form_post_to_stop_is_refused_by_origin():
    reply = make_client().post(
        "/stop", headers={**FORM_HEADERS, "Origin": "https://evil.example"}
    )
    assert reply.status_code == 403


def test_a_null_origin_is_refused():
    reply = make_client().post("/stop", headers={**JSON_HEADERS, "Origin": "null"})
    assert reply.status_code == 403


def test_a_cross_origin_read_is_refused():
    reply = make_client().get("/ping", headers={"Origin": "https://evil.example"})
    assert reply.status_code == 403


@pytest.mark.parametrize("origin", [UI_ORIGIN, "http://localhost:5174", "http://127.0.0.1:5173"])
def test_ui_origins_may_post_json(origin):
    reply = make_client().post("/stop", headers={**JSON_HEADERS, "Origin": origin})
    assert reply.status_code == 200


def test_a_script_without_an_origin_may_post_json():
    assert make_client().post("/stop", headers=JSON_HEADERS).status_code == 200


@pytest.mark.parametrize("headers", [{}, FORM_HEADERS, {"Content-Type": "text/plain"}])
def test_a_bodyless_post_without_json_content_type_gets_415(headers):
    assert make_client().post("/stop", headers=headers).status_code == 415


def test_delete_needs_json_content_type_too():
    client = make_client()
    assert client.delete("/thing").status_code == 415
    assert client.delete("/thing", headers=JSON_HEADERS).status_code == 200


def test_json_content_type_with_a_charset_is_accepted():
    headers = {"Content-Type": "application/json; charset=utf-8"}
    assert make_client().post("/stop", headers=headers).status_code == 200


def test_a_read_needs_no_content_type():
    assert make_client().get("/ping").status_code == 200


def test_the_real_app_refuses_an_unknown_host():
    from main import app

    reply = TestClient(app, base_url="http://evil.example:8000").get("/templates")
    assert reply.status_code == 421


def test_the_real_app_refuses_a_cross_site_stop():
    from main import app

    reply = TestClient(app, base_url="http://localhost:8000").post(
        "/stop", headers={**FORM_HEADERS, "Origin": "https://evil.example"}
    )
    assert reply.status_code == 403
