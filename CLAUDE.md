# Keitaro wrapper (тестовое Adrobot)

Обёртка над Admin API трекера Keitaro: создаватор кампаний и редактор офферов в потоках.
План, открытые вопросы и этапы описаны в [PLAN.md](PLAN.md). Перед работой прочитай его и отметь, что сделано.

## Цель

1. Создать кампанию `test_Zaitsev_<name>` с доменом, группой и источником и двумя потоками:
   поток 1: фильтр по стране (Geo), редирект на https://google.com; поток 2: выбранный оффер.
2. Редактор существующей кампании по видео: Fetch из Keitaro → правки черновиком (add / remove / bring back / pin) →
   Push в Keitaro или Cancel. Полная логика описана в PLAN.md, раздел «Логика редактора», это и есть спецификация.
3. README с миграциями и запуском. Сдача ссылкой на GitHub.

## Стек

- Python 3.11, FastAPI, SQLAlchemy 2.x (sync), Alembic, SQLite по умолчанию (`DATABASE_URL`).
- httpx для Keitaro, pydantic-settings для конфига, Jinja2 + vanilla JS/jQuery для фронта. Без сборщика.
- Тесты: pytest + respx. Линт: ruff.

## Команды

```bash
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
copy .env.example .env            # ключ KEITARO_API_KEY вписывает пользователь, не агент
python scripts/recon.py [id ...]  # только GET: справочники и потоки кампаний в tests/fixtures/
alembic upgrade head
uvicorn app.main:app --reload
python -m pytest
ruff check . && ruff format .
```

## Жёсткие правила

- **Keitaro боевой и общий для компании** (`https://keitaro.example.com`, документация API: `https://keitaro.example.com/admin/?object=adminApi`).
  Создавать, менять и удалять разрешено только кампании с префиксом `settings.NAME_PREFIX` = `test_Zaitsev_`. Проверка на бэкенде, не только в UI.
  Чужие кампании, офферы, домены, группы и источники только читать.
- Тесты никогда не ходят в реальный Keitaro, только через respx-моки. Запросы к боевому API делает только ручная проверка.
- Секреты (`KEITARO_URL`, `KEITARO_API_KEY`) лежат только в `.env`. В git попадает `.env.example`. Ключ не логировать.
- Поля API сверяй с документацией в админке Keitaro и с таблицей API в PLAN.md, а не с памятью.
  Известные ловушки: `alias` обязателен при создании кампании; `group_id` строка, `domain_id` и `traffic_source_id` числа;
  `DELETE /campaigns/{id}` только архивирует.
  Неясное поле сначала проверь через `GET` на существующей кампании и посмотри, как Keitaro его хранит.
- Если ТЗ расходится со скриншотами или видео (например, Geo «одна страна» против `MX,AU,RO` в эскизе),
  не выбирай молча: покажи расхождение и спроси.
- Создание кампании идёт в несколько шагов (кампания, затем потоки). Если упал поздний шаг, удали то, что создал
  на ранних шагах (только своё), и верни понятную ошибку.

## Код

- Всё синхронно: `httpx.Client` в `app/keitaro.py` и `def`-эндпоинты (FastAPI сам гоняет их в threadpool).
  Ошибки Keitaro клиент уже превращает в `HTTPException(502)`, в роутерах их не ловить.
- Логика создаватора лежит в `app/services.py` (`campaign_payload`, `stream_payloads`, `create_campaign`),
  логика редактора — в `app/editor.py` (`rebalance`, `fetch`, add/remove/restore/pin, `push`, `cancel`).
  HTTP-код лежит в `app/keitaro.py`, роутеры тонкие. Каждая операция редактора возвращает кампанию целиком (`serialize`).
- `rebalance`: доли целые; закреплённые (pinned) не трогаем; `100 − Σ pinned` делим поровну между активными
  незакреплёнными, остаток раздаём по 1% последним (3 оффера: 33/33/34); у `removed` доля 0. Pin сам доли не пересчитывает.
- `PUT /streams/{id}` с `offers` заменяет весь список, поэтому Push отправляет все активные офферы потока.
- Middleware `same_origin_only` в `app/main.py` отклоняет POST с чужим Origin. Не убирать: авторизации нет.
- Черновик и публикация: в `stream_offers` есть текущие поля (`share`, `state`) и опубликованные (`pub_share`, `pub_state`).
  Keitaro меняет только Push. Fetch, Push и Cancel переписывают `pub_*` или текущие поля целиком, без частичных обновлений.
- Ошибки Keitaro отдаются клиенту как HTTP 502 с текстом ответа Keitaro, без проглатывания.
- Без лишних абстракций: никаких репозиториев, DI-контейнеров и async ORM. Таблицы: `campaigns`, `streams`, `offers`, `stream_offers`
  (id совпадают с id в Keitaro). `offers` — справочник, его пополняет `services.upsert_offer`, когда оффер реально
  встретился. Это не кэш для поиска: автокомплит всегда ходит в Keitaro, как в эталоне.
- Миграции только через Alembic (`alembic revision --autogenerate -m ...`), без `create_all` в проде.
- Коммиты небольшие, по этапам из PLAN.md.

## Полезные инструменты

- Context7 MCP: доки FastAPI, SQLAlchemy, Alembic, httpx, respx.
- Встроенный браузер или Playwright: доки API в админке Keitaro, проверка созданной кампании и UI.
- Скилл `test-driven-development`: для `rebalance` и сборщиков payload.
