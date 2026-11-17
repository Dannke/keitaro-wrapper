# План реализации: Keitaro wrapper (тестовое Adrobot)

Источник ТЗ: https://app.notion.com/p/mnovikov/Adrobot-2b01eb78a7bb80a1b188c3a4a1cad55e
Видео редактора: https://youtu.be/jNloscEWCjA (6:13)

## Итоговая цель

Публичный репозиторий на GitHub с приложением FastAPI + SQLAlchemy, у которого:

1. **Создаватор кампаний**: форма «Name / Geo / Offer (автокомплит) / Create» создаёт в Keitaro кампанию:
   - имя `test_<фамилия>_<name>`;
   - домен, группа и источник трафика заданы (берутся через API);
   - поток 1: фильтр «страна = Geo», действие «редирект на https://google.com»;
   - поток 2: редирект на выбранный оффер.
2. **Редактор кампании** повторяет логику из видео (см. раздел «Логика редактора»). Он забирает потоки в нашу БД, офферы добавляются и удаляются как черновик, Push отправляет изменения в Keitaro, Cancel откатывает. Удалённые офферы попадают в архив с кнопкой «Bring back», доли можно закреплять (pin). Незакреплённые доли делятся поровну, сумма всегда 100.
3. **README**: установка, `.env`, `alembic upgrade head`, запуск, тесты.

Критерий готовности: в админке Keitaro созданная кампания выглядит как на скриншоте из ТЗ: Flow 1 ведёт на google.com с фильтром по стране, Flow 2 ведёт на оффер; домен, группа и источник заполнены. После правок в редакторе доли офферов в админке совпадают с показанными в UI.

## Ограничения

- **Keitaro боевой и общий**: там реальная статистика компании. Создавать и менять можно только свои кампании с префиксом `test_<фамилия>_`. Редактор отказывается сохранять кампанию без этого префикса (проверка на бэкенде). Не удалять и не менять чужие кампании, офферы, домены, группы и источники.
- Новые группы и источники не создавать, если подходящие уже есть (на скриншоте ТЗ это `FORTESTS`). Создавать только если их нет, и только с префиксом.
- Стек задан: FastAPI + SQLAlchemy (+ Alembic, раз в README нужны миграции). Фронт: Jinja2-шаблоны + vanilla JS/jQuery, без сборщика.
- API-ключ и URL Keitaro хранятся только в `.env`, в git попадает `.env.example`.
- Документация API (Swagger, OpenAPI 3) открыта по адресу `https://keitaro.example.com/admin/?object=adminApi` после входа в админку. Поля запросов сверять с ней, не с памятью.

## API Keitaro (сверено со Swagger 2026-11-17)

Базовый URL `https://keitaro.example.com/admin_api/v1`, заголовок `Api-Key: <ключ>`.

| Зачем | Запрос | Важное |
|---|---|---|
| Автокомплит офферов | `GET /offers` | поля `id`, `name`, `state`, `country` |
| Домен | `GET /domains` | `id`, `name` |
| Группа | `GET /groups?type=campaigns` | `type` обязателен |
| Источник | `GET /traffic_sources` | `id`, `name` |
| Создать кампанию | `POST /campaigns` | **обязательны `name` и `alias`** (alias генерируем, 6–8 символов `[a-zA-Z0-9]`). Также `type: position`, `domain_id` (int), `group_id` (**string**), `traffic_source_id` (int), `state: active` |
| Откат при ошибке | `DELETE /campaigns/{id}` | переносит в архив, а не удаляет насовсем |
| Потоки кампании | `GET /campaigns/{id}/streams` | ответ `Stream[]`, внутри `offers: [{id, offer_id, share, state}]` |
| Создать поток | `POST /streams` | обязательны `campaign_id`, `schema`, `type`, `name`, `action_type` |
| Изменить поток | `PUT /streams/{id}` | `offers: [{offer_id, share, state}]` |
| Справочники | `GET /stream_types`, `/stream_schemas`, `/streams_actions`, `/stream_filters` | точные значения `action_type` и имя фильтра страны |

Поля потока: `type` принимает `forced|regular|default`, `schema` принимает `landings|redirect|action`, `position`. Фильтр: `filters: [{name, mode: accept|reject, payload: [..]}]`. Офферы: `offers: [{offer_id, share, state: active|disabled}]`.

Payload потоков (сверено 2026-11-17 с потоками существующих кампаний на keitaro.example.com, пример в `tests/fixtures/streams_209494.json`):
```jsonc
// поток 1: страна → google
{"campaign_id": 1, "type": "regular", "name": "Geo → Google", "position": 1,
 "schema": "redirect", "action_type": "http", "action_payload": "https://google.com",
 "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}]}
// поток 2: оффер
{"campaign_id": 1, "type": "regular", "name": "Offers", "position": 2,
 "schema": "landings", "action_type": "http",
 "offers": [{"offer_id": 123, "share": 100, "state": "active"}]}
```

Что выяснила разведка (этап 1):
- `action_payload` при создании потока работает: он заполнен у потоков, созданных через API.
- Редирект задаётся как `action_type: "http"`, фильтр страны называется `country`, `payload` содержит список кодов (`["AU","MX"]`).
- Поток 1 у всех `regular` на `position: 1`, не `forced`. Делаем так же.
- У потоков с офферами `action_payload: ""`. Доли бывают неравными (75/25): это закреплённые доли (pin), см. «Логика редактора».
- Эталонной кампании со скриншота ТЗ на keitaro.example.com нет: скриншот сделан на другом трекере.
- Значения по умолчанию на этом трекере: домен `1` (`example.com`, единственный), группа `2` (`FORTESTS`), источник `3` (`FORTESTS`, единственный). Новые не создаём.
- **Не выяснено:** заменяет ли `PUT /streams/{id}` с `offers` весь список. Это проверяется только записью, поэтому на этапе 4 на своей кампании `test_Zaitsev_*`.

## Открытые вопросы (решить до кода)

1. ~~Фамилия для префикса~~ Решено: префикс `test_Zaitsev_` (например `test_Zaitsev_campaign1`).
2. ~~URL админки и ключ~~ Решено: админка `https://keitaro.example.com/admin/`, документация API по адресу `https://keitaro.example.com/admin/?object=adminApi`. Ключ пользователь создаёт сам (Профиль → API ключи) и кладёт в `.env`.
3. **Расхождение ТЗ и эскиза по Geo**: в ТЗ «гео-код страны» (одна страна), в эскизе формы `MX,AU,RO,...` (похоже на список). Предлагаю принимать список кодов через запятую в один фильтр `country`; одна страна при этом тоже работает.
4. **Домен, группа, источник**: в эскизе формы этих полей нет. Предлагаю значения по умолчанию в конфиге (1 / 2 FORTESTS / 3 FORTESTS, переопределяются через `.env`) и необязательные селекты в форме.
5. ~~Логика редактора~~ Решено по расшифровке видео, см. ниже. Колонка Trends на кадре видео в расшифровке не упоминается, её не делаем.

## Логика редактора (по видео)

Кнопки на странице кампании: **Fetch streams from KT** и **View in KT** (ссылка на кампанию в админке). У каждого потока: **Add offer** (автокомплит), **Push**, **Cancel**. У каждого оффера: **Remove** или **Bring back** и **Pin**.

1. **Fetch** забирает потоки кампании из Keitaro в БД.
   - Поток без офферов (как «страна → Google») показывается только именем, содержимое не разбираем.
   - Офферы потока сохраняются с долями из Keitaro.
   - Оффер, который есть у нас, но пропал из Keitaro, не удаляется, а получает статус `removed` (серый, 0%, кнопка «Bring back»), как если бы его удалили у нас.
   - Fetch приводит базу к состоянию Keitaro, неопубликованные правки при этом сбрасываются.
2. **Add offer**: оффер добавляется в поток только у нас.
   - Доли пересчитываются: 4 оффера получают по 25%.
   - Поток становится «жёлтым» (есть неопубликованные изменения).
   - В Keitaro пока ничего не меняется.
3. **Remove**: оффер становится серым с долей 0%, остальные пересчитываются, поток желтеет.
   - После Push оффер исчезает из Keitaro, но остаётся у нас в архиве с кнопкой «Bring back».
4. **Bring back**: оффер снова активен, доли пересчитываются, поток желтеет.
5. **Push** отправляет активные офферы потока с долями в `PUT /streams/{id}`, поток снова «белый».
6. **Cancel** возвращает поток к последнему опубликованному состоянию.
   - Офферы, добавленные после публикации, удаляются из БД (привязка удаляется).
   - У остальных возвращаются прежние доли и статусы.
7. **Pin** фиксирует долю оффера: при любом пересчёте закреплённые доли не меняются.
   - Остаток `100 − Σ pinned` делится поровну между активными незакреплёнными офферами, остаток от деления уходит последнему (3 оффера: 33/33/34).

Модель данных под это:
- `stream_offers` хранит текущее состояние (`share`, `state: active|removed`, `pinned`) и опубликованное (`pub_state: active|removed|NULL`, `pub_share`). `NULL` означает «никогда не был в Keitaro».
- «Жёлтый» поток: хотя бы у одного оффера `(state, share) != (pub_state, pub_share)`.
- Cancel удаляет строки с `pub_state IS NULL`, а у остальных возвращает `state=pub_state` и `share=pub_share`.
- Push записывает `pub_* = текущие`.

Свои допущения (в видео не показано):
- Remove снимает pin.
- Push запрещён, если сумма активных долей не равна 100. Такое бывает, если все офферы закреплены.
- Pin не делает поток жёлтым.

## Этапы

| # | Этап | Результат | Проверка |
|---|------|-----------|----------|
| 0 ✅ | Каркас | `requirements.txt`, `app/`, `.env.example`, `.gitignore`, `git init` | `/health` отвечает |
| 1 ✅ | Клиент Keitaro и разведка | `app/keitaro.py` (sync `httpx.Client`, ошибки → 502), `scripts/recon.py`, справочники в `tests/fixtures/` | 3 теста, разведка на keitaro.example.com |
| 2 | БД + миграции | Таблицы `campaigns` (id из Keitaro, name, alias, geo, created_at), `streams` (id из Keitaro, campaign_id, name, position), `offers` (справочник: id из Keitaro, name, updated_at; пополняется при создании, Fetch и Add offer, это не кэш поиска: поиск всегда идёт в Keitaro), `stream_offers` (stream_id, offer_id → offers, share, state, pinned, pub_state, pub_share; уникальная пара stream+offer). Alembic, SQLite по умолчанию (`DATABASE_URL`) | `alembic upgrade head` на чистой базе |
| 3 | Создаватор | `POST /api/campaigns`: валидация (имя, ISO-коды стран, offer_id существует), затем создание кампании, потока 1 и потока 2. Если поток не создался, удалить созданную кампанию, чтобы не оставлять мусор в Keitaro. Страница `/` с формой; автокомплит офферов через `<datalist>` из `GET /api/offers` | тест на сборку payload (respx), ручная проверка в админке |
| 4 | Редактор | Эндпоинты `POST /api/campaigns/{id}/fetch`, `GET /api/campaigns/{id}`, `POST /api/streams/{id}/offers`, `POST /api/stream_offers/{id}/remove`, `/restore`, `/pin`, `POST /api/streams/{id}/push`, `/cancel`. Чистая функция `rebalance` с учётом pin. Страница `/campaigns/{id}`. Сначала одним Push на своей кампании проверить, что `PUT /streams/{id}` заменяет список офферов | unit-тесты `rebalance` (1, 3, 4 оффера; pin; все закреплены) и сценарий из видео на моках, ручная сверка с админкой |
| 5 | README и сдача | README: требования, `.env`, миграции, запуск, тесты, скриншоты. Пуш на GitHub | проверка с нуля по README в чистой папке |

## Структура

```
app/
  main.py          # FastAPI, подключение роутеров и шаблонов
  config.py        # pydantic-settings: KEITARO_URL, KEITARO_API_KEY, NAME_PREFIX, дефолтные id
  db.py, models.py # SQLAlchemy 2.0 (async не нужен, хватит sync + SQLite)
  keitaro.py       # HTTP-клиент
  services.py      # build_campaign_payload, build_streams, rebalance
  routers/api.py, routers/pages.py
  templates/index.html, templates/editor.html
alembic/
tests/test_services.py
```

## Инструменты

Обязательные: Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic, httpx, pydantic-settings, Jinja2, uvicorn.

Рекомендуемые:
- **pytest + respx**: тесты без обращения к боевому Keitaro (моки HTTP).
- **ruff**: линт и форматирование.
- **uv** или venv + pip: окружение (`uv` быстрее, но не обязателен).
- **Context7 MCP**: актуальные доки FastAPI, SQLAlchemy 2.0, Alembic, httpx.
- **Встроенный браузер / Playwright MCP**: открыть доки API в админке Keitaro, проверить созданную кампанию и UI.
- **Скилл `test-driven-development`**: только для `rebalance` и сборки payload (расчёты и преобразование данных).
- **Агенты (Cursor / Claude Code)**: ТЗ это прямо приветствует. Упомянуть в README.

Не нужны: React и сборщик, Docker (можно добавить в конце как бонус), Postgres (SQLite хватит, `DATABASE_URL` позволит сменить), Celery, авторизация.
