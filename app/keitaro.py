"""Тонкий клиент Keitaro Admin API (Swagger: <KEITARO_URL>/admin/?object=adminApi)."""

import httpx
from fastapi import HTTPException

from app.config import settings

client = httpx.Client(
    base_url=settings.keitaro_url.rstrip("/") + "/admin_api/v1",
    headers={"Api-Key": settings.keitaro_api_key},
    timeout=20,
)


def request(method: str, path: str, **kwargs):
    """Ошибки сети и ответы 4xx/5xx от Keitaro превращаются в 502 с текстом Keitaro, чтобы UI показал причину."""
    if not (settings.keitaro_url and settings.keitaro_api_key):
        raise HTTPException(500, "Не заданы KEITARO_URL и KEITARO_API_KEY в .env (см. README, «Подключение к Keitaro»)")
    try:
        r = client.request(method, path, **kwargs)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Keitaro недоступен: {e}") from e
    if r.is_error:
        raise HTTPException(502, f"Keitaro {r.status_code} {method} {path}: {r.text[:500]}")
    return r.json() if r.content else None


def get(path: str, **params):
    return request("GET", path, params=params or None)


def post(path: str, json: dict):
    return request("POST", path, json=json)


def put(path: str, json: dict):
    return request("PUT", path, json=json)


def delete(path: str):
    return request("DELETE", path)
