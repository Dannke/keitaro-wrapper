import json

import pytest
import respx
from fastapi import HTTPException

from app import keitaro, services
from app.models import Campaign, Offer

BASE = keitaro.client.base_url
OFFERS = [{"id": 25327, "name": "Mixflow AU", "state": "active"}, {"id": 19958, "name": "Other", "state": "active"}]


def test_full_name_adds_prefix_once():
    assert services.full_name(" campaign1 ") == "test_Zaitsev_campaign1"
    assert services.full_name("test_Zaitsev_x") == "test_Zaitsev_x"
    with pytest.raises(HTTPException):
        services.full_name("  ")


def test_parse_geo():
    assert services.parse_geo("au, mx,AU") == ["AU", "MX"]
    assert services.parse_geo("gb,xk") == ["GB", "XK"]
    for bad in ("", "AUS", "A1", ",,", "XX", "AU,ZZ"):  # формат верный, но таких стран нет: фильтр не сработал бы
        with pytest.raises(HTTPException):
            services.parse_geo(bad)
    with pytest.raises(HTTPException) as e:
        services.parse_geo("UK")
    assert "GB" in e.value.detail


def test_country_list_is_iso_3166():
    assert len(services.COUNTRIES) == 250  # 249 кодов ISO 3166-1 alpha-2 и XK
    assert all(len(c) == 2 and c.isupper() for c in services.COUNTRIES)


def test_ensure_ours():
    services.ensure_ours("test_Zaitsev_x")
    with pytest.raises(HTTPException) as e:
        services.ensure_ours("test_ivanov_campaign1")
    assert e.value.status_code == 403


def test_stream_payloads_match_keitaro_format():
    google, offers = services.stream_payloads(7, ["AU", "MX"], 25327)
    assert google["position"] == 1 and google["schema"] == "redirect" and google["action_type"] == "http"
    assert google["action_payload"] == "https://google.com"
    assert google["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU", "MX"]}]
    assert offers["position"] == 2 and offers["schema"] == "landings"
    assert offers["offers"] == [{"offer_id": 25327, "share": 100, "state": "active"}]


@respx.mock
def test_create_campaign_end_to_end(client, db):
    respx.get(f"{BASE}offers").respond(json=OFFERS)
    camp = respx.post(f"{BASE}campaigns").mock(
        side_effect=lambda req: respx.MockResponse(
            200, json={"id": 500, "name": json.loads(req.content)["name"], "alias": json.loads(req.content)["alias"]}
        )
    )
    streams = respx.post(f"{BASE}streams").respond(json={"id": 1})

    r = client.post("/api/campaigns", json={"name": "campaign1", "geo": "au", "offer_id": 25327})

    assert r.status_code == 201, r.text
    assert r.json()["name"] == "test_Zaitsev_campaign1"
    assert r.json()["offer"] == {"id": 25327, "name": "Mixflow AU"}  # UI показывает, какой оффер ушёл в поток
    sent = json.loads(camp.calls.last.request.content)
    assert (sent["domain_id"], sent["group_id"], sent["traffic_source_id"]) == (1, "2", 3)  # из conftest
    assert len(sent["alias"]) == 8
    assert streams.call_count == 2
    assert db.get(Campaign, 500).geo == "AU"
    assert db.get(Offer, 25327).name == "Mixflow AU"


@respx.mock
def test_missing_defaults_rejected_before_any_request(client, monkeypatch):
    monkeypatch.setattr(services.settings, "default_group_id", None)
    r = client.post("/api/campaigns", json={"name": "x", "geo": "AU", "offer_id": 25327})
    assert r.status_code == 500 and "DEFAULT_GROUP_ID" in r.json()["detail"]  # respx не замокан: запросов не было


def test_missing_keitaro_url_gives_clear_error(monkeypatch):
    monkeypatch.setattr(keitaro.settings, "keitaro_url", "")
    with pytest.raises(HTTPException) as e:
        keitaro.get("/offers")
    assert e.value.status_code == 500 and "KEITARO_URL" in e.value.detail


def test_upsert_offer_updates_name(db):
    services.upsert_offer(db, {"id": 1, "name": "old"})
    services.upsert_offer(db, {"id": 1, "name": "new"})
    db.commit()
    assert db.get(Offer, 1).name == "new"


@respx.mock
def test_failed_stream_rolls_back_campaign(client, db):
    respx.get(f"{BASE}offers").respond(json=OFFERS)
    respx.post(f"{BASE}campaigns").respond(json={"id": 501, "name": "test_Zaitsev_x", "alias": "abc"})
    respx.post(f"{BASE}streams").respond(422, json={"error": "bad filter"})
    rollback = respx.delete(f"{BASE}campaigns/501").respond(json={})

    r = client.post("/api/campaigns", json={"name": "x", "geo": "AU", "offer_id": 25327})

    assert r.status_code == 502 and "bad filter" in r.json()["detail"]
    assert rollback.called
    assert db.get(Campaign, 501) is None


@respx.mock
def test_unknown_offer_rejected_before_any_write(client):
    respx.get(f"{BASE}offers").respond(json=OFFERS)
    r = client.post("/api/campaigns", json={"name": "x", "geo": "AU", "offer_id": 1})
    assert r.status_code == 422  # respx упал бы на любой POST: он не замокан


@respx.mock
def test_offer_search_and_index_page(client):
    respx.get(f"{BASE}offers").respond(json=OFFERS)
    assert client.get("/api/offers?q=mix").json() == [{"id": 25327, "name": "Mixflow AU"}]
    assert client.get("/api/offers?q=1995").json() == [{"id": 19958, "name": "Other"}]
    assert "New campaign" in client.get("/").text
