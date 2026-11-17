import json
from types import SimpleNamespace as O

import httpx
import respx

from app import editor, keitaro

BASE = keitaro.client.base_url
CID, SID = 900, 9002
OFFERS = [{"id": i, "name": f"offer {i}", "state": "active"} for i in (1, 2, 3, 4, 5)]


def shares(*offers):
    editor.rebalance(list(offers))
    return [o.share for o in offers]


def a(share=0, pinned=False):
    return O(state="active", share=share, pinned=pinned)


def test_rebalance_even_split():
    assert shares(a()) == [100]
    assert shares(a(), a(), a()) == [33, 33, 34]
    assert shares(a(), a(), a(), a()) == [25, 25, 25, 25]
    assert shares(*[a() for _ in range(7)]) == [14, 14, 14, 14, 14, 15, 15]


def test_rebalance_keeps_pinned_and_zeroes_removed():
    removed = O(state="removed", share=40, pinned=False)
    assert shares(a(25, pinned=True), a(), a(), removed) == [25, 37, 38, 0]


def test_rebalance_all_pinned_left_as_is():
    assert shares(a(60, pinned=True), a(30, pinned=True)) == [60, 30]


def kt_streams(offers):
    return [
        {"id": 9001, "name": "AU -> Google", "position": 1, "schema": "redirect", "offers": []},
        {"id": SID, "name": "Offers", "position": 2, "schema": "landings", "offers": offers},
    ]


def mock_keitaro(offers, name="test_Zaitsev_c1"):
    """Keitaro с состоянием, как настоящий: PUT меняет офферы потока, GET отдаёт текущие. Правка kt — правка в админке."""
    kt = {"name": name, "offers": offers}

    def put(request):
        kt["offers"] = json.loads(request.content)["offers"]
        return httpx.Response(200, json={})

    respx.get(f"{BASE}campaigns/{CID}").mock(
        side_effect=lambda _: httpx.Response(200, json={"id": CID, "name": kt["name"], "alias": "abc"})
    )
    respx.get(f"{BASE}campaigns/{CID}/streams").mock(
        side_effect=lambda _: httpx.Response(200, json=kt_streams(kt["offers"]))
    )
    respx.get(f"{BASE}offers").respond(json=OFFERS)
    return kt, respx.put(f"{BASE}streams/{SID}").mock(side_effect=put)


def offers_of(campaign_json):
    s = next(s for s in campaign_json["streams"] if s["id"] == SID)
    return s, [(o["offer_id"], o["share"], o["state"]) for o in s["offers"]]


def so_id(campaign_json, offer_id):
    return next(o["id"] for o in offers_of(campaign_json)[0]["offers"] if o["offer_id"] == offer_id)


@respx.mock
def test_video_scenario(client):
    """Сценарий из видео: fetch → add → cancel → add+push → remove+push → bring back → pin."""
    three = [{"offer_id": i, "share": s, "state": "active"} for i, s in ((1, 33), (2, 33), (3, 34))]
    _, put = mock_keitaro(three)

    c = client.post(f"/api/campaigns/{CID}/fetch").json()
    google = c["streams"][0]
    assert (google["has_offers"], google["offers"]) == (False, [])  # поток без офферов — только имя
    stream, offers = offers_of(c)
    assert offers == [(1, 33, "active"), (2, 33, "active"), (3, 34, "active")] and not stream["dirty"]

    # добавили 4-й: всем по 25, поток жёлтый, в Keitaro ничего не ушло
    c = client.post(f"/api/streams/{SID}/offers", json={"offer_id": 4}).json()
    stream, offers = offers_of(c)
    assert [s for _, s, _ in offers] == [25, 25, 25, 25] and stream["dirty"] and not put.called

    # Cancel: добавленный до публикации оффер удалился, доли вернулись
    c = client.post(f"/api/streams/{SID}/cancel").json()
    stream, offers = offers_of(c)
    assert offers == [(1, 33, "active"), (2, 33, "active"), (3, 34, "active")] and not stream["dirty"]

    # добавили и опубликовали
    client.post(f"/api/streams/{SID}/offers", json={"offer_id": 4})
    c = client.post(f"/api/streams/{SID}/push").json()
    assert json.loads(put.calls.last.request.content)["offers"] == [
        {"offer_id": i, "share": 25, "state": "active"} for i in (1, 2, 3, 4)
    ]
    assert not offers_of(c)[0]["dirty"]

    # Remove: серый, 0%, остальные пересчитались; после Push в Keitaro его нет, у нас он в архиве
    c = client.post(f"/api/stream_offers/{so_id(c, 2)}/remove").json()
    assert offers_of(c)[1] == [(1, 33, "active"), (2, 0, "removed"), (3, 33, "active"), (4, 34, "active")]
    c = client.post(f"/api/streams/{SID}/push").json()
    assert [o["offer_id"] for o in json.loads(put.calls.last.request.content)["offers"]] == [1, 3, 4]
    assert not offers_of(c)[0]["dirty"]

    # Pin 25% у оффера 1, затем Bring back оффера 2: закреплённый не меняется
    client.post(f"/api/stream_offers/{so_id(c, 1)}/pin", json={"pinned": True})  # 33 закреплено как есть
    c = client.post(f"/api/stream_offers/{so_id(c, 2)}/restore").json()
    assert offers_of(c)[1] == [(1, 33, "active"), (2, 22, "active"), (3, 22, "active"), (4, 23, "active")]
    assert offers_of(c)[0]["dirty"] and offers_of(c)[0]["total"] == 100


@respx.mock
def test_fetch_marks_offers_missing_in_keitaro_as_removed(client):
    kt, _ = mock_keitaro([{"offer_id": i, "share": s, "state": "active"} for i, s in ((1, 50), (2, 50))])
    client.post(f"/api/campaigns/{CID}/fetch")

    kt["offers"] = [{"offer_id": 1, "share": 100}]
    c = client.post(f"/api/campaigns/{CID}/fetch").json()

    stream, offers = offers_of(c)
    assert offers == [(1, 100, "active"), (2, 0, "removed")] and not stream["dirty"]
    c = client.post(f"/api/stream_offers/{so_id(c, 2)}/restore").json()  # Bring back доступен
    assert offers_of(c)[1] == [(1, 50, "active"), (2, 50, "active")]


@respx.mock
def test_push_refused_for_foreign_campaign_and_bad_total(client):
    _, put = mock_keitaro([{"offer_id": 1, "share": 100}], name="test_ivanov_campaign1")
    c = client.post(f"/api/campaigns/{CID}/fetch").json()
    assert c["editable"] is False
    assert client.post(f"/api/streams/{SID}/push").status_code == 403
    assert not put.called


@respx.mock
def test_push_refused_when_pins_break_total(client):
    _, put = mock_keitaro([{"offer_id": i, "share": s} for i, s in ((1, 60), (2, 30), (3, 10))])
    c = client.post(f"/api/campaigns/{CID}/fetch").json()
    client.post(f"/api/stream_offers/{so_id(c, 1)}/pin", json={"pinned": True})
    client.post(f"/api/stream_offers/{so_id(c, 2)}/pin", json={"pinned": True})
    c = client.post(f"/api/stream_offers/{so_id(c, 3)}/remove").json()  # остались только закреплённые 60+30

    assert offers_of(c)[0]["total"] == 90
    r = client.post(f"/api/streams/{SID}/push")
    assert r.status_code == 422 and "100" in r.json()["detail"]
    assert not put.called


@respx.mock
def test_push_refused_when_keitaro_changed_after_fetch(client):
    kt, put = mock_keitaro([{"offer_id": 1, "share": 100, "state": "active"}])
    client.post(f"/api/campaigns/{CID}/fetch")
    client.post(f"/api/streams/{SID}/offers", json={"offer_id": 2})  # черновик 50/50

    # в админке добавили оффер 5: Push затёр бы его
    kt["offers"] = [{"offer_id": 1, "share": 50, "state": "active"}, {"offer_id": 5, "share": 50, "state": "active"}]
    r = client.post(f"/api/streams/{SID}/push")
    assert r.status_code == 409 and "Fetch" in r.json()["detail"]

    # в админке выключили оффер 1: Push включил бы его обратно
    kt["offers"] = [{"offer_id": 1, "share": 100, "state": "disabled"}]
    r = client.post(f"/api/streams/{SID}/push")
    assert r.status_code == 409 and "[1]" in r.json()["detail"]

    # кампанию переименовали без префикса: имя в нашей БД устарело, проверяем по Keitaro
    kt["offers"], kt["name"] = [{"offer_id": 1, "share": 100, "state": "active"}], "Prod campaign"
    assert client.post(f"/api/streams/{SID}/push").status_code == 403
    assert not put.called

    kt["name"] = "test_Zaitsev_c1"  # Keitaro снова совпадает с опубликованным: Push проходит
    assert client.post(f"/api/streams/{SID}/push").status_code == 200 and put.call_count == 1


def test_cross_site_post_rejected(client):
    r = client.post(f"/api/streams/{SID}/push", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post(f"/api/streams/{SID}/push", headers={"Origin": "http://localhost"}).status_code == 404


def test_dns_rebinding_host_rejected(client):
    # evil.example указывает на 127.0.0.1: Origin совпадает с Host, но Host не в allowed_hosts
    r = client.post(f"/api/streams/{SID}/push", headers={"Host": "evil.example", "Origin": "http://evil.example"})
    assert r.status_code == 400
