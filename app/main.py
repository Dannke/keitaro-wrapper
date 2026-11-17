from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Campaign
from app.routers import api
from app.services import COUNTRIES

app = FastAPI(title="Keitaro wrapper")
app.include_router(api.router)
# Без проверки Host сравнение Origin с Host обходится через DNS rebinding (evil.com → 127.0.0.1)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def asset(path: str) -> str:
    """URL статики с mtime: после правки файла браузер не берёт старую версию из кэша."""
    return f"/static/{path}?v={int((STATIC / path).stat().st_mtime)}"


# чип в шапке напоминает, что действия уходят в общий боевой трекер; адрес только из .env
templates.env.globals.update(
    asset=asset,
    prefix=settings.name_prefix,
    tracker_host=urlsplit(settings.keitaro_url).netloc,
    kt_campaign_url=settings.keitaro_url.rstrip("/") + "/admin/#!/campaign/{id}/main",
)


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
    return templates.TemplateResponse(request, "index.html", {"campaigns": campaigns, "countries": sorted(COUNTRIES)})


@app.get("/campaigns/{campaign_id}")
def editor_page(request: Request, campaign_id: int):
    return templates.TemplateResponse(request, "editor.html", {"campaign_id": campaign_id})
