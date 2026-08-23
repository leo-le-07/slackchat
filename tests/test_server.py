import pytest
from fastapi.testclient import TestClient

from slackchat import service as svc
from slackchat.config import CliConfig, Config, ServerConfig
from slackchat.server.app import create_app
from slackchat.server.token import TOKEN_HEADER
from slackchat.store import sqlite as store

TOKEN = "test-token"


@pytest.fixture
def client(isolated_paths, fake_provider):
    def _client(replies, *, error=None, origins=()):
        provider = fake_provider(replies, error=error)
        config = Config(server=ServerConfig(port=8765, token=TOKEN, allowed_origins=tuple(origins)))
        service = svc.build_service(config, provider=provider)
        app = create_app(service=service, config=config, token=TOKEN)
        return TestClient(app), provider

    return _client


def _headers():
    return {TOKEN_HEADER: TOKEN}


def test_health_needs_no_token(client):
    api, _ = client([])
    response = api.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_process_returns_the_result_as_json(client):
    api, _ = client(["I finished the task we discussed yesterday."])
    response = api.post(
        "/process",
        json={"text": "I has finish the task we discussed yesterday."},
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == "I finished the task we discussed yesterday."
    assert body["mode"] == "correction"
    assert body["forced"] is False
    assert body["changed_ratio"] == 0.25
    assert body["flags"] == []
    assert body["error"] is None
    assert body["prompt_version"] == "1"
    assert len(body["prompt_hash"]) == 12
    assert body["cost_usd"] == pytest.approx(0.0002)


def test_the_json_carries_the_diff_segments(client):
    api, _ = client(["I finished the task we discussed yesterday."])
    body = api.post(
        "/process",
        json={"text": "I has finish the task we discussed yesterday."},
        headers=_headers(),
    ).json()
    kinds = [c["kind"] for c in body["changes"]]
    assert kinds == ["equal", "replace", "equal"]
    assert body["changes"][1]["before"] == "has finish"
    assert body["changes"][1]["after"] == "finished"


def test_the_json_shape_matches_what_the_cli_saw(client):
    api, provider = client(["I finished the task we discussed yesterday."] * 2)
    body = api.post(
        "/process",
        json={"text": "I has finish the task we discussed yesterday."},
        headers=_headers(),
    ).json()
    direct = svc.build_service(
        Config(server=ServerConfig(token=TOKEN)), provider=provider
    ).run("I has finish the task we discussed yesterday.", client="cli")
    assert set(body) == {f.name for f in direct.__dataclass_fields__.values()}


def test_an_explicit_mode_is_honoured(client):
    api, _ = client(["I am done.", "I am done."])
    body = api.post(
        "/process", json={"text": "Tôi đã xong", "mode": "correction"}, headers=_headers()
    ).json()
    assert body["mode"] == "correction"
    assert body["forced"] is True


def test_a_missing_token_is_rejected(client):
    api, provider = client(["never used"])
    response = api.post("/process", json={"text": "hello"})
    assert response.status_code == 401
    assert provider.calls == []


def test_a_wrong_token_is_rejected(client):
    api, provider = client(["never used"])
    response = api.post("/process", json={"text": "hello"}, headers={TOKEN_HEADER: "nope"})
    assert response.status_code == 401
    assert provider.calls == []


def test_empty_text_is_a_400_and_costs_nothing(client):
    api, provider = client(["never used"])
    response = api.post("/process", json={"text": "   "}, headers=_headers())
    assert response.status_code == 400
    assert provider.calls == []
    conn = store.connect()
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_a_bad_mode_value_is_a_422(client):
    api, _ = client([])
    response = api.post("/process", json={"text": "hi", "mode": "rewrite"}, headers=_headers())
    assert response.status_code == 422


def test_a_provider_error_is_a_200_with_the_error_in_the_body(client):
    api, _ = client([], error="rate limited")
    response = api.post("/process", json={"text": "hello there"}, headers=_headers())
    assert response.status_code == 200
    assert response.json()["error"] == "rate limited"


def test_runs_are_logged_with_the_server_client(client):
    api, _ = client(["I finished the task we discussed yesterday."])
    api.post(
        "/process",
        json={"text": "I has finish the task we discussed yesterday."},
        headers=_headers(),
    )
    conn = store.connect()
    assert conn.execute("SELECT client FROM runs").fetchone()[0] == "server"


def test_no_cors_headers_without_an_allowlist(client):
    api, _ = client(["hello"])
    response = api.post(
        "/process",
        json={"text": "hello"},
        headers={**_headers(), "Origin": "https://evil.example"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_an_allowlisted_origin_gets_the_cors_header(client):
    api, _ = client(["hello"], origins=["chrome-extension://abcd"])
    response = api.post(
        "/process",
        json={"text": "hello"},
        headers={**_headers(), "Origin": "chrome-extension://abcd"},
    )
    assert response.headers["access-control-allow-origin"] == "chrome-extension://abcd"


def test_a_non_allowlisted_origin_gets_no_cors_header(client):
    api, _ = client(["hello"], origins=["chrome-extension://abcd"])
    response = api.post(
        "/process",
        json={"text": "hello"},
        headers={**_headers(), "Origin": "chrome-extension://evil"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_the_server_module_contains_no_pipeline_logic():
    import inspect

    from slackchat.server import app as module

    source = inspect.getsource(module)
    for forbidden in ("difflib", "sanitize", "detect(", "mechanical_replace", "find_violations"):
        assert forbidden not in source, forbidden
