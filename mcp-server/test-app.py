import os
os.environ["AZURE_SUBSCRIPTION_ID"] = "fff58e80-f555-4e48-bdc3-e1628e91f1fd"

import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))

import app as app_module  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app_module.app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200, r.text
    assert r.json()["subscription_configured"] is True
    print("healthz: OK ->", r.json())


def test_invalid_name_format():
    r = client.post("/api/check-name", json={"resource_type": "storage_account", "name": "AB"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is False
    assert body["reason"] == "InvalidName"
    print("invalid format: OK ->", body)


def test_invalid_resource_type():
    r = client.post("/api/check-name", json={"resource_type": "not_a_real_type", "name": "abc"})
    assert r.status_code == 422, r.text
    print("invalid resource_type: OK -> 422 as expected")


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json


async def fake_post(self, url, params=None, json=None, headers=None):
    return FakeResponse(200, {"nameAvailable": True, "reason": None, "message": None})


async def fake_post_taken(self, url, params=None, json=None, headers=None):
    return FakeResponse(200, {"nameAvailable": False, "reason": "AlreadyExists", "message": "Name is already in use."})


async def fake_get_404(self, url, params=None, headers=None):
    return FakeResponse(404)


def test_storage_account_available(monkeypatch):
    with patch.object(app_module, "get_arm_token", return_value="fake-token"):
        with patch("httpx.AsyncClient.post", new=fake_post):
            r = client.post("/api/check-name", json={"resource_type": "storage_account", "name": "stmyapp01"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    print("storage available: OK ->", body)


def test_storage_account_taken():
    with patch.object(app_module, "get_arm_token", return_value="fake-token"):
        with patch("httpx.AsyncClient.post", new=fake_post_taken):
            r = client.post("/api/check-name", json={"resource_type": "storage_account", "name": "stmyapp02"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is False
    assert body["reason"] == "AlreadyExists"
    print("storage taken: OK ->", body)


def test_cosmos_db_available():
    with patch.object(app_module, "get_arm_token", return_value="fake-token"):
        with patch("httpx.AsyncClient.get", new=fake_get_404):
            r = client.post("/api/check-name", json={"resource_type": "cosmos_db", "name": "cosmos-myapp"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    print("cosmos available: OK ->", body)


def test_missing_subscription_id():
    original = app_module.SUBSCRIPTION_ID
    app_module.SUBSCRIPTION_ID = ""
    try:
        r = client.post("/api/check-name", json={"resource_type": "storage_account", "name": "stmyapp01"})
        assert r.status_code == 500, r.text
        print("missing subscription id: OK -> 500 as expected")
    finally:
        app_module.SUBSCRIPTION_ID = original


if __name__ == "__main__":
    test_healthz()
    test_invalid_name_format()
    test_invalid_resource_type()
    test_storage_account_available(None)
    test_storage_account_taken()
    test_cosmos_db_available()
    test_missing_subscription_id()
    print("\nALL TESTS PASSED")
