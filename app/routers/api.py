from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import editor, services
from app.db import get_db
from app.models import Offer

router = APIRouter(prefix="/api")


class CampaignIn(BaseModel):
    name: str
    geo: str
    offer_id: int


@router.get("/offers")
def offers(q: str = ""):
    return services.search_offers(q)


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignIn, db: Session = Depends(get_db)):
    c = services.create_campaign(db, body.name, body.geo, body.offer_id)
    offer = db.get_one(Offer, body.offer_id)  # UI показывает, какой оффер реально ушёл в поток
    return {"id": c.id, "name": c.name, "alias": c.alias, "geo": c.geo, "offer": {"id": offer.id, "name": offer.name}}


# Редактор: каждая операция возвращает кампанию целиком, UI просто перерисовывается.


class OfferIn(BaseModel):
    offer_id: int


class PinIn(BaseModel):
    pinned: bool


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    return editor.serialize(editor.get_campaign(db, campaign_id))


@router.post("/campaigns/{campaign_id}/fetch")
def fetch(campaign_id: int, db: Session = Depends(get_db)):
    return editor.serialize(editor.fetch(db, campaign_id))


@router.post("/streams/{stream_id}/offers")
def add_offer(stream_id: int, body: OfferIn, db: Session = Depends(get_db)):
    return editor.serialize(editor.add_offer(db, stream_id, body.offer_id))


@router.post("/streams/{stream_id}/push")
def push(stream_id: int, db: Session = Depends(get_db)):
    return editor.serialize(editor.push(db, stream_id))


@router.post("/streams/{stream_id}/cancel")
def cancel(stream_id: int, db: Session = Depends(get_db)):
    return editor.serialize(editor.cancel(db, stream_id))


@router.post("/stream_offers/{so_id}/remove")
def remove_offer(so_id: int, db: Session = Depends(get_db)):
    return editor.serialize(editor.remove_offer(db, so_id))


@router.post("/stream_offers/{so_id}/restore")
def restore_offer(so_id: int, db: Session = Depends(get_db)):
    return editor.serialize(editor.restore_offer(db, so_id))


@router.post("/stream_offers/{so_id}/pin")
def pin_offer(so_id: int, body: PinIn, db: Session = Depends(get_db)):
    return editor.serialize(editor.pin_offer(db, so_id, body.pinned))
