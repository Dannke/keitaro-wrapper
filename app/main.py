from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
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


@app.middleware("http")
async def same_origin_only(request: Request, call_next):
    """CSRF: авторизации нет, а Push пишет в общий Keitaro — чужой сайт не должен дёргать наши POST.

    Браузер всегда шлёт Origin на cross-site POST; curl и тесты без Origin проходят.
    """
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlsplit(origin).netloc != request.url.netloc:
        return JSONResponse({"detail": "Запрос с чужого сайта отклонён"}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    campaigns = db.scalars(select(Campaign).order_by(Campaign.id.desc())).all()
    return templates.TemplateResponse(request, "index.html", {"campaigns": campaigns, "prefix": settings.name_prefix})


@app.get("/campaigns/{campaign_id}")
def editor_page(request: Request, campaign_id: int):
    return templates.TemplateResponse(
        request, "editor.html", {"campaign_id": campaign_id, "prefix": settings.name_prefix}
    )
