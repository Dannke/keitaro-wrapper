from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id в Keitaro
    name: Mapped[str]
    alias: Mapped[str]
    geo: Mapped[str | None]  # заполнен только у созданных создаватором, например "AU,MX"
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="Stream.position"
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id в Keitaro
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    name: Mapped[str]
    position: Mapped[int]
    # landings — поток с офферами (редактируем); остальные только показываем по имени, как в эталоне
    schema: Mapped[str] = mapped_column(server_default="landings")

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="StreamOffer.id"
    )


class Offer(Base):
    """Справочник офферов, которые встречались в наших потоках. Не кэш поиска: поиск всегда идёт в Keitaro."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id в Keitaro
    name: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class StreamOffer(Base):
    """Оффер в потоке: текущее (черновик) и опубликованное в Keitaro состояние."""

    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"))
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"))
    share: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(default="active")  # active | removed
    pinned: Mapped[bool] = mapped_column(default=False)
    pub_state: Mapped[str | None]  # None — ни разу не публиковался (Cancel удалит строку)
    pub_share: Mapped[int] = mapped_column(default=0)

    stream: Mapped[Stream] = relationship(back_populates="offers")
    offer: Mapped[Offer] = relationship(lazy="joined")
