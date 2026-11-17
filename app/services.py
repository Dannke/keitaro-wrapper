import re
import secrets
import string

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import keitaro
from app.config import settings
from app.models import Campaign, Offer

GOOGLE_URL = "https://google.com"
_ALNUM = string.ascii_letters + string.digits


def full_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(422, "Пустое имя кампании")
    return name if name.startswith(settings.name_prefix) else settings.name_prefix + name


def ensure_ours(name: str) -> None:
    """Keitaro общий: менять можно только свои кампании."""
    if not name.startswith(settings.name_prefix):
        raise HTTPException(403, f"Можно менять только кампании с префиксом {settings.name_prefix}")


def parse_geo(geo: str) -> list[str]:
    codes = list(dict.fromkeys(c.strip().upper() for c in geo.split(",") if c.strip()))
    bad = [c for c in codes if not re.fullmatch(r"[A-Z]{2}", c)]
    if not codes or bad:
        raise HTTPException(422, f"Geo: нужны двухбуквенные коды стран через запятую, неверно: {bad or geo!r}")
    return codes


def campaign_payload(name: str, alias: str) -> dict:
    return {
        "name": name,
        "alias": alias,
        "type": "position",
        "state": "active",
        "domain_id": settings.default_domain_id,
        "group_id": settings.default_group_id,
        "traffic_source_id": settings.default_source_id,
    }


def stream_payloads(campaign_id: int, countries: list[str], offer_id: int) -> list[dict]:
    common = {"campaign_id": campaign_id, "type": "regular", "action_type": "http", "state": "active"}
    return [
        common
        | {
            "name": f"{','.join(countries)} -> Google",
            "position": 1,
            "schema": "redirect",
            "action_payload": GOOGLE_URL,
            "filters": [{"name": "country", "mode": "accept", "payload": countries}],
        },
        common
        | {
            "name": "Offers",
            "position": 2,
            "schema": "landings",
            "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        },
    ]


def search_offers(q: str = "", limit: int = 20) -> list[dict]:
    q = q.strip().lower()
    offers = [{"id": o["id"], "name": o["name"]} for o in keitaro.get("/offers") if o.get("state") == "active"]
    return [o for o in offers if q in str(o["id"]) or q in o["name"].lower()][:limit]


def create_campaign(db: Session, name: str, geo: str, offer_id: int) -> Campaign:
    name, countries = full_name(name), parse_geo(geo)
    missing = [
        env
        for env, value in (
            ("DEFAULT_DOMAIN_ID", settings.default_domain_id),
            ("DEFAULT_GROUP_ID", settings.default_group_id),
            ("DEFAULT_SOURCE_ID", settings.default_source_id),
        )
        if value is None
    ]
    if missing:
        raise HTTPException(500, f"Не заданы {', '.join(missing)} в .env: id выводит python scripts/recon.py")
    offer = next((o for o in keitaro.get("/offers") if o["id"] == offer_id), None)
    if offer is None:
        raise HTTPException(422, f"Оффер {offer_id} не найден в Keitaro")

    alias = "".join(secrets.choice(_ALNUM) for _ in range(8))
    camp = keitaro.post("/campaigns", campaign_payload(name, alias))
    try:
        for payload in stream_payloads(camp["id"], countries, offer_id):
            keitaro.post("/streams", payload)
    except HTTPException as e:
        # не оставляем в общем Keitaro кампанию без потоков; DELETE переносит её в архив
        try:
            keitaro.delete(f"/campaigns/{camp['id']}")
        except HTTPException as rollback:
            e.detail += f"; откат не удался, кампания {camp['id']} осталась в Keitaro: {rollback.detail}"
        raise

    campaign = Campaign(id=camp["id"], name=camp["name"], alias=camp["alias"], geo=",".join(countries))
    db.add(campaign)
    upsert_offer(db, offer)
    db.commit()
    return campaign


def upsert_offer(db: Session, offer: dict) -> Offer:
    """Обновляет справочник оффером из ответа Keitaro (вызывать при создании, Fetch и Add offer)."""
    return db.merge(Offer(id=offer["id"], name=offer["name"]))
