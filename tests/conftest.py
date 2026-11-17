import os

# Тесты не зависят от .env разработчика: переменные окружения важнее .env, выставляем их до импорта app
os.environ.update(
    KEITARO_URL="https://keitaro.test",
    KEITARO_API_KEY="test-key",
    NAME_PREFIX="test_Zaitsev_",
    DEFAULT_DOMAIN_ID="1",
    DEFAULT_GROUP_ID="2",
    DEFAULT_SOURCE_ID="3",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)  # в тестах вместо миграций
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, base_url="http://localhost")  # localhost есть в allowed_hosts
    app.dependency_overrides.clear()
