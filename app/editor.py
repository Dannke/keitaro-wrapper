"""Редактор офферов в потоках: черновик в нашей БД, Push в Keitaro. Логика описана в PLAN.md, «Логика редактора»."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import keitaro
from app.config import settings
from app.models import Campaign, Stream, StreamOffer
from app.services import ensure_ours, upsert_offer

ACTIVE, REMOVED = "active", "removed"


def rebalance(offers: list[StreamOffer]) -> None:
    """Закреплённые доли не трогаем, остаток до 100 делим поровну между активными незакреплёнными.

    Остаток от деления раздаём по 1 последним офферам: 3 → 33/33/34, 7 → 14×5/15/15.
    """
    active = [o for o in offers if o.state == ACTIVE]
    for o in offers:
        if o.state != ACTIVE:
            o.share = 0
    free = [o for o in active if not o.pinned]
    if not free:
        return
    rest = max(0, 100 - sum(o.share for o in active if o.pinned))
    base, extra = divmod(rest, len(free))
    for i, o in enumerate(free):
        o.share = base + (1 if i >= len(free) - extra else 0)


def is_dirty(stream: Stream) -> bool:
    return any((o.state, o.share) != (o.pub_state, o.pub_share) for o in stream.offers)


def serialize(campaign: Campaign) -> dict:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "editable": campaign.name.startswith(settings.name_prefix),
        "keitaro_url": f"{settings.keitaro_url.rstrip('/')}/admin/#!/campaign/{campaign.id}/main",
        "streams": [
            {
                "id": s.id,
                "name": s.name,
                "position": s.position,
                "has_offers": s.schema == "landings",
                "dirty": is_dirty(s),
                "total": sum(o.share for o in s.offers if o.state == ACTIVE),
                "offers": [
                    {
                        "id": o.id,
                        "offer_id": o.offer_id,
                        "name": o.offer.name,
                        "share": o.share,
                        "state": o.state,
                        "pinned": o.pinned,
                        "published": o.pub_state is not None,
                    }
                    for o in s.offers
                ],
            }
            for s in campaign.streams
        ],
    }


def get_campaign(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(404, "Кампания ещё не загружена: нажмите Fetch streams")
    return campaign


def fetch(db: Session, campaign_id: int) -> Campaign:
    """Приводит БД к состоянию Keitaro. Офферы, которых в Keitaro больше нет, уходят в архив (removed)."""
    kt = keitaro.get(f"/campaigns/{campaign_id}")
    campaign = db.get(Campaign, campaign_id) or Campaign(id=campaign_id, alias=kt["alias"], name=kt["name"])
    campaign.name, campaign.alias = kt["name"], kt["alias"]
    db.add(campaign)

    names = {o["id"]: o["name"] for o in keitaro.get("/offers")}
    kt_streams = keitaro.get(f"/campaigns/{campaign_id}/streams")
    kt_ids = {s["id"] for s in kt_streams}
    for s in list(campaign.streams):
        if s.id not in kt_ids:
            campaign.streams.remove(s)

    for ks in kt_streams:
        stream = db.get(Stream, ks["id"]) or Stream(id=ks["id"])
        stream.name, stream.position, stream.schema = ks["name"], ks["position"], ks["schema"]
        if stream not in campaign.streams:
            campaign.streams.append(stream)

        kt_offers = {o["offer_id"]: o["share"] for o in ks.get("offers", [])}
        for o in list(stream.offers):
            if o.pub_state is None:  # неопубликованный черновик Fetch сбрасывает
                stream.offers.remove(o)
            elif o.offer_id in kt_offers:
                o.state = o.pub_state = ACTIVE
                o.share = o.pub_share = kt_offers.pop(o.offer_id)
            else:
                o.state = o.pub_state = REMOVED
                o.share = o.pub_share = 0
                o.pinned = False
        for offer_id, share in kt_offers.items():
            upsert_offer(db, {"id": offer_id, "name": names.get(offer_id, f"#{offer_id}")})
            stream.offers.append(
                StreamOffer(offer_id=offer_id, share=share, state=ACTIVE, pub_state=ACTIVE, pub_share=share)
            )
    db.commit()
    return campaign


def _offer_stream(db: Session, stream_id: int) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None or stream.schema != "landings":
        raise HTTPException(404, "Поток с офферами не найден")
    return stream


def _stream_offer(db: Session, so_id: int) -> StreamOffer:
    so = db.get(StreamOffer, so_id)
    if so is None:
        raise HTTPException(404, "Оффер в потоке не найден")
    return so


def _save(db: Session, stream: Stream) -> Campaign:
    rebalance(stream.offers)
    db.commit()
    return stream.campaign


def add_offer(db: Session, stream_id: int, offer_id: int) -> Campaign:
    stream = _offer_stream(db, stream_id)
    existing = next((o for o in stream.offers if o.offer_id == offer_id), None)
    if existing and existing.state == ACTIVE:
        raise HTTPException(409, f"Оффер {offer_id} уже в потоке")
    if existing:
        existing.state = ACTIVE  # был в архиве — то же, что Bring back
    else:
        offer = next((o for o in keitaro.get("/offers") if o["id"] == offer_id), None)
        if offer is None:
            raise HTTPException(422, f"Оффер {offer_id} не найден в Keitaro")
        upsert_offer(db, offer)
        stream.offers.append(StreamOffer(offer_id=offer_id, state=ACTIVE, pub_state=None))
    return _save(db, stream)


def remove_offer(db: Session, so_id: int) -> Campaign:
    so = _stream_offer(db, so_id)
    so.state, so.pinned = REMOVED, False
    return _save(db, so.stream)


def restore_offer(db: Session, so_id: int) -> Campaign:
    so = _stream_offer(db, so_id)
    so.state = ACTIVE
    return _save(db, so.stream)


def pin_offer(db: Session, so_id: int, pinned: bool) -> Campaign:
    so = _stream_offer(db, so_id)
    if so.state != ACTIVE:
        raise HTTPException(422, "Закрепить можно только активный оффер")
    so.pinned = pinned  # без пересчёта: по видео pin лишь фиксирует долю для следующих операций
    db.commit()
    return so.stream.campaign


def _ensure_unchanged_in_keitaro(stream: Stream) -> None:
    """PUT заменяет весь список офферов, поэтому Push не должен затереть правки, сделанные в Keitaro после Fetch."""
    ensure_ours(keitaro.get(f"/campaigns/{stream.campaign_id}")["name"])  # имя в БД могло устареть с последнего Fetch
    ks = next((s for s in keitaro.get(f"/campaigns/{stream.campaign_id}/streams") if s["id"] == stream.id), None)
    if ks is None:
        raise HTTPException(409, "Поток удалён в Keitaro: нажмите Fetch streams")
    kt_offers = ks.get("offers") or []
    disabled = [o["offer_id"] for o in kt_offers if o.get("state", ACTIVE) != ACTIVE]
    if disabled:  # Push отправляет все офферы активными и включил бы их обратно
        raise HTTPException(409, f"В Keitaro в потоке выключены офферы {disabled}: редактор их не поддерживает")
    published = {o.offer_id: o.pub_share for o in stream.offers if o.pub_state == ACTIVE}
    if {o["offer_id"]: o["share"] for o in kt_offers} != published:
        raise HTTPException(409, "Поток изменён в Keitaro после Fetch: нажмите Fetch streams и повторите правки")


def push(db: Session, stream_id: int) -> Campaign:
    stream = _offer_stream(db, stream_id)
    active = [o for o in stream.offers if o.state == ACTIVE]
    if active and sum(o.share for o in active) != 100:
        raise HTTPException(422, "Сумма долей должна быть 100%: снимите закрепление с одного из офферов")
    _ensure_unchanged_in_keitaro(stream)
    # PUT с offers заменяет весь список офферов потока (проверено на реальном трекере), остальные поля не трогает
    keitaro.put(
        f"/streams/{stream.id}",
        {"offers": [{"offer_id": o.offer_id, "share": o.share, "state": ACTIVE} for o in active]},
    )
    for o in stream.offers:
        o.pub_state, o.pub_share = o.state, o.share
    db.commit()
    return stream.campaign


def cancel(db: Session, stream_id: int) -> Campaign:
    stream = _offer_stream(db, stream_id)
    for o in list(stream.offers):
        if o.pub_state is None:
            stream.offers.remove(o)
        else:
            o.state, o.share = o.pub_state, o.pub_share
    db.commit()
    return stream.campaign
