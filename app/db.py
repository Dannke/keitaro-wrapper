from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    # имена ограничений нужны Alembic, чтобы менять FK/unique в SQLite (batch mode)
    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
        }
    )


def get_db():
    with SessionLocal() as db:
        yield db
