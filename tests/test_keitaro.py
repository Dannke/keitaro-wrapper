import httpx
import pytest
import respx
from fastapi import HTTPException

from app import keitaro

BASE = keitaro.client.base_url


@respx.mock
def test_get_sends_api_key_and_params():
    route = respx.get(f"{BASE}groups", params={"type": "campaigns"}).respond(json=[{"id": 1}])
    assert keitaro.get("/groups", type="campaigns") == [{"id": 1}]
    assert "api-key" in route.calls.last.request.headers


@respx.mock
def test_keitaro_error_becomes_502_with_body():
    respx.post(f"{BASE}campaigns").respond(422, json={"error": "alias is required"})
    with pytest.raises(HTTPException) as e:
        keitaro.post("/campaigns", {"name": "x"})
    assert e.value.status_code == 502
    assert "alias is required" in e.value.detail


@respx.mock
def test_network_error_becomes_502():
    respx.get(f"{BASE}offers").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(HTTPException) as e:
        keitaro.get("/offers")
    assert e.value.status_code == 502
