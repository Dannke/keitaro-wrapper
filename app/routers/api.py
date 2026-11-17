from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import services
from app.db import get_db

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
    return {"id": c.id, "name": c.name, "alias": c.alias, "geo": c.geo}
