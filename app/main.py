from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Campaign
from app.routers import api

app = FastAPI(title="Keitaro wrapper")
app.include_router(api.router)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    campaigns = db.scalars(select(Campaign).order_by(Campaign.id.desc())).all()
    return templates.TemplateResponse(request, "index.html", {"campaigns": campaigns, "prefix": settings.name_prefix})
