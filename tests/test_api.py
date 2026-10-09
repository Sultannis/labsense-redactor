"""The HTTP contract, as the backend's `HttpRedactor` reads it."""

import hashlib

import pymupdf
import pytest
from fastapi.testclient import TestClient

from labsense_redactor.app import create_app
from labsense_redactor.config import Settings
from labsense_redactor.detect.names import NameFinder
from labsense_redactor.storage import MemoryStorage

from . import reports

TOKEN = "test-token-0123456789"
AUTH = {"authorization": f"Bearer {TOKEN}"}
KEY = "acc/0192f0a3-0000-7000-8000-000000000001/0192f0a3-0000-7000-8000-000000000002"


@pytest.fixture
def storage() -> MemoryStorage:
    storage = MemoryStorage()
    storage.write(KEY, reports.english().pdf, "application/pdf")
    return storage


@pytest.fixture
def client(storage: MemoryStorage, names: NameFinder) -> TestClient:
    settings = Settings(token=TOKEN, s3_bucket="test", s3_region="eu-central-1")
    return TestClient(create_app(settings, storage, names))


def _known() -> dict[str, list]:
    return {"names": ["Anna Example"], "emails": ["anna.example@example.com"], "birthYears": [1988]}


def test_health_needs_no_token(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("endpoint", ["/detect", "/words", "/apply", "/rasterize"])
def test_every_endpoint_needs_the_token(client: TestClient, endpoint: str) -> None:
    for headers in ({}, {"authorization": "Bearer wrong"}, {"authorization": TOKEN}):
        response = client.post(endpoint, json={}, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"error": "unauthorized"}


def test_detect(client: TestClient) -> None:
    response = client.post("/detect", json={"key": KEY, "pageCount": 2, "known": _known()}, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"regions", "summary", "scanned"}
    assert body["scanned"] is False
    assert body["summary"]["name"] == 3
    for region in body["regions"]:
        assert set(region) == {"page", "x0", "y0", "x1", "y1", "type"}
        assert region["page"] in (1, 2) and region["type"] != "manual"
        assert 0 <= region["x0"] < region["x1"] <= 1 and 0 <= region["y0"] < region["y1"] <= 1


def test_detect_refuses_a_page_count_that_doesnt_match(client: TestClient) -> None:
    response = client.post("/detect", json={"key": KEY, "pageCount": 1, "known": _known()}, headers=AUTH)
    assert response.status_code == 422
    assert response.json() == {"error": "page_count_mismatch"}


def test_a_missing_key_is_refused(client: TestClient) -> None:
    response = client.post("/words", json={"key": "acc/x/missing", "pageCount": 1}, headers=AUTH)
    assert (response.status_code, response.json()) == (422, {"error": "not_found"})


def test_an_invalid_request_doesnt_echo_its_input(client: TestClient) -> None:
    response = client.post(
        "/detect", json={"key": KEY, "pageCount": 0, "known": {"names": ["Anna Example"]}}, headers=AUTH
    )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}
    assert "Anna" not in response.text


def test_words(client: TestClient) -> None:
    response = client.post("/words", json={"key": KEY, "pageCount": 2}, headers=AUTH)
    pages = response.json()["pages"]
    assert [p["page"] for p in pages] == [1, 2]
    texts = [w["text"] for w in pages[0]["words"]]
    assert "Hemoglobin" in texts and "Anna" in texts
    word = pages[0]["words"][0]
    assert set(word) == {"text", "x0", "y0", "x1", "y1"}


def test_apply_writes_the_verified_copy(client: TestClient, storage: MemoryStorage) -> None:
    regions = client.post(
        "/detect", json={"key": KEY, "pageCount": 2, "known": _known()}, headers=AUTH
    ).json()["regions"]
    manual = {"page": 1, "x0": 0.9, "y0": 0.9, "x1": 0.95, "y1": 0.92, "type": "manual"}
    out = KEY + "-redacted"
    response = client.post(
        "/apply", json={"key": KEY, "regions": [*regions, manual], "outputKey": out}, headers=AUTH
    )
    body = response.json()
    assert body["verified"] is True
    written, content_type = storage.objects[out]
    assert content_type == "application/pdf"
    assert body["byteSize"] == len(written)
    assert body["sha256"] == hashlib.sha256(written).hexdigest()
    assert "Anna" not in "".join(page.get_text() for page in pymupdf.open(stream=written))


def test_outputs_stay_beside_the_input(client: TestClient) -> None:
    other = "acc/0192f0a3-0000-7000-8000-000000000099/file"
    response = client.post("/apply", json={"key": KEY, "regions": [], "outputKey": other}, headers=AUTH)
    assert (response.status_code, response.json()) == (422, {"error": "output_key_elsewhere"})
    response = client.post(
        "/rasterize", json={"key": KEY, "regions": [], "outputs": [{"page": 1, "key": other}]}, headers=AUTH
    )
    assert response.status_code == 422


def test_rasterize(client: TestClient, storage: MemoryStorage) -> None:
    outputs = [{"page": 2, "key": KEY + "-p2"}, {"page": 1, "key": KEY + "-p1"}]
    response = client.post("/rasterize", json={"key": KEY, "regions": [], "outputs": outputs}, headers=AUTH)
    pages = response.json()["pages"]
    assert [p["page"] for p in pages] == [2, 1]
    for page, output in zip(pages, outputs, strict=True):
        written, content_type = storage.objects[output["key"]]
        assert content_type == "image/jpeg" and written[:2] == b"\xff\xd8"
        assert page["byteSize"] == len(written)
        assert page["sha256"] == hashlib.sha256(written).hexdigest()


def test_logs_hold_no_document_text(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    client.post("/detect", json={"key": KEY, "pageCount": 2, "known": _known()}, headers=AUTH)
    client.post("/words", json={"key": KEY, "pageCount": 2}, headers=AUTH)
    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    for secret in ("Anna", "Example", "1988", "anna.example", KEY, TOKEN):
        assert secret not in logged
