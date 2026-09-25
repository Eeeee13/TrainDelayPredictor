# Предиктор задержек городского транспорта — Backend

Реализация Backend-модуля хакатона «Предиктор изменений в графике движения
городского транспорта»: приём телеметрии, Matching Engine, планировщик
обращений к ML (по календарю прогнозных моментов из расписания), Risk
Aggregator, REST + WebSocket для дашборда. Postgres как БД, событийная шина
(Redis Streams с деградацией до in-process asyncio-очереди) между
телеметрией/фичами/предсказаниями/алертами.

Архитектурно — 3 независимых модуля:

1. **Backend** (`backend/`, этот репозиторий) — приём данных, Matching
   Engine, планировщик предсказаний, Risk Aggregator, REST/WebSocket API.
2. **ML Inference Service** — отдельный контейнер, `POST /predict`.
   `backend/inference_stub/` — заглушка с тем же контрактом
   (`predictor.predict(tr_id, T, cur_dev_s, target_stop_id, target_time_begin)`),
   чтобы стенд поднимался и демонстрировался end-to-end уже сейчас; когда
   будет готов реальный образ модели — просто подменяется build-контекст
   сервиса `inference` в `docker-compose.yml`.
3. **BI-дашборд** — не реализован в этом репозитории (backend-only задача
   по вашей формулировке); контракт для него готов: `GET /risk` для
   первичной загрузки + `ws://.../ws/risk` для live-обновлений.

---

## Быстрый старт

```bash
docker compose up --build

curl http://localhost:8000/health
curl http://localhost:8001/health   # inference stub
open http://localhost:8000/docs     # Swagger
```

### Демо без датасета (для быстрой проверки логики за секунды)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed_demo --backend http://localhost:8000
# подождать ~5с (один тик планировщика) и посмотреть:
curl http://localhost:8000/risk
curl http://localhost:8000/vehicles/bus-101/deviation
```

`seed_demo.py` намеренно ставит целевую остановку так, чтобы она сразу
попадала в окно 10–15 минут до наступления — прогноз появится в течение
одного тика планировщика (~5с), не дожидаясь полного проигрывания маршрута.

### Проигрывание реального датасета

```bash
python -m scripts.replay_csv --traffic traffic.csv --schedule schedule.csv \
    --backend http://localhost:8000 --speed 30
```

Скрипт сдвигает временные метки датасета так, чтобы они оказались в
реальном "сейчас" (иначе все `scheduled_time` были бы в прошлом и окно
10–15 минут никогда бы не наступило), и проигрывает поток с ускорением.
**Названия колонок CSV зависят от реального датасета** — они вынесены в
константы `TRAFFIC_COLUMNS` / `SCHEDULE_COLUMNS` в
`app/adapters/csv_telemetry_adapter.py`; поправьте их под фактические
заголовки `traffic.csv`/`schedule.csv` — остальной пайплайн не зависит от
формата CSV (Matching Engine получает уже нормализованные сущности).

Готового NDTP-эмулятора хакатона в репозитории нет (выдаётся
организаторами на старте) — вместо него backend принимает уже
нормализованные JSON-батчи через `POST /ingest/telemetry`. Под сырой
бинарный NDTP нужен отдельный парсер-адаптер перед этим эндпоинтом (или
внутри него) — самое изолированное место для его добавления, не
затрагивающее остальной пайплайн.

---

## Где что смотреть

- `GET /risk` — последний risk-статус по каждому ТС (для первичной
  загрузки дашборда). Отдаётся из in-memory кэша, без похода в БД.
- `GET /risk/{vehicle_id}` — статус по одному ТС.
- `POST /risk/recompute` — принудительно прогнать один тик планировщика
  прямо сейчас (для демо жюри; иначе тики идут сами каждые
  `APP_SCHEDULER_TICK_S`, по умолчанию 5с).
- `ws://localhost:8000/ws/risk` — live-поток `RiskAssessment` в JSON.
- `GET /vehicles/{vehicle_id}/deviation` — «сырое», не-ML отклонение от
  графика (то же значение, на которое деградирует ML-fallback).
- Swagger: `http://localhost:8000/docs`, ReDoc: `/redoc`, схема:
  `/openapi.json`.

---

## Как и когда вызывается ML (ключевое требование задачи)

Не по таймеру и не по факту прибытия на остановку, а **по календарю
прогнозных моментов**, вычисляемому из расписания:

- Для каждой остановки, ещё не пройденной ТС, известно `target_time_begin`
  из эталонного расписания.
- В момент, когда `target_time_begin - now` **впервые** попадает в окно
  `[10, 15]` минут, эта пара `(tr_id, target_stop_id)` становится «due» —
  по ней делается ровно один «первый» прогноз, максимально рано (в начале
  окна, т.е. ближе к 15 минутам), это и есть раннее предупреждение.
- Раз в ~60с идёт страховочный пересчёт (`APP_SAFETY_RECOMPUTE_INTERVAL_S`),
  но **только** для пар, уже получивших первый прогноз и находящихся в
  риске `HIGH`, и только пока событие ещё не наступило. Он никогда не
  создаёт новый «первый» алерт и никогда не срабатывает постфактум.
- Анти-утечка по времени: пары, чьё `target_time_begin <= now`, никогда не
  попадают в батч на прогноз — «прогнозов задним числом» не бывает
  архитектурно, а не по соглашению.
- Если телеметрия прервалась и окно 10–15 мин было пропущено, но событие
  ещё не наступило (`remaining_s >= APP_LATE_FIRE_FLOOR_S`) — прогноз всё
  равно делается один раз (деградация горизонта лучше, чем отсутствие
  прогноза), это фиксируется в `predictions_log` для последующего анализа.

Реализация — `app/services/prediction_scheduler.py`, юнит-тесты на все
перечисленные случаи — `backend/tests/test_prediction_scheduler.py`.

## Частота фич / очереди

- Фичи (`cur_dev_s`, средняя скорость сегмента, признак стоянки) строятся
  **на каждый NDTP-пакет** (~12–15с), полностью in-memory
  (`app/services/state_cache.py`, `app/services/matching_engine.py`) — без
  похода в БД на горячем пути.
- Очередь есть на обеих границах: `POST /ingest/telemetry` только
  валидирует и публикует в топик `telemetry` (сотые доли мс на пакет,
  независимо от загрузки пайплайна), фоновый `TelemetryWorker` уже
  персистит и считает фичи, публикуя `features` для наблюдаемости.
  `predictions`/`alerts` — топики, в которые публикует планировщик.
- Топики бэкенда живут на `EventBus` (`app/bus/event_bus.py`): по
  умолчанию — Redis Streams (consumer group `backend`, восстанавливаемая
  очередь между Backend и потенциально отдельными воркерами/ML), при
  недоступности Redis — деградация до in-process `asyncio.Queue`-шины без
  падения сервиса (тот же принцип, что и для ML-инференса).

## Деградация без падения сервиса

- ML недоступен/таймаут/ошибка → `ResilientInferenceClient`
  (Strategy + Decorator, простой circuit breaker) переключается на
  `predicted_delay_s = cur_dev_s` — тот же бейзлайн, что и
  `sample_submission.csv` датасета (~0.40 по метрике соревнования).
- Redis недоступен на старте → откат на in-process шину, лог-предупреждение,
  сервис поднимается и работает.
- Обрыв телеметрии по ТС → `cur_dev_s` не сбрасывается, а держит последнее
  известное значение (не выдумываем данные), риск-статус остаётся
  последним известным, пока `APP_STALE_VEHICLE_AFTER_S` не исключит ТС из
  активного календаря.

---

## Документация API / кода

```bash
open http://localhost:8000/docs        # Swagger UI (FastAPI, автогенерация)
open http://localhost:8000/redoc       # ReDoc

pip install sphinx
sphinx-build -b html backend/docs backend/docs/_build   # PyDoc/Sphinx (см. ниже)
```

> В этой сборке присутствует код с докстрингами по каждому модулю
> (`app/domain`, `app/services`, `app/repositories`, `app/api`), но
> `docs/` со сконфигурированным Sphinx-проектом в этот заход не входит —
> добавляется типовым `sphinx-quickstart` с `autodoc`/`napoleon`
> extensions, указывающими на `backend/app`.

---

## Тесты

```bash
cd backend
pytest            # 18 тестов: unit (matching engine, inference client,
                   # risk aggregator, prediction scheduler) + API smoke-тесты
pytest --cov=app
```

Тесты работают на изолированной in-memory SQLite (async, `aiosqlite`) и
in-process шине событий — без Docker, Postgres или Redis; ORM-модели
идентичны тем, что используются с Postgres в проде (никаких
диалект-специфичных типов в `app/db/models.py`), поэтому это честная
проверка бизнес-логики, а не только "оно импортируется".

---

## Архитектура и структура кода

```
backend/
  app/
    domain/        # framework-free сущности и value objects
    db/             # ORM-модели (Postgres/SQLite-совместимые), engine/session
    bus/            # EventBus: Redis Streams | in-process asyncio bus
    repositories/   # TelemetryRepository, ScheduleRepository, PredictionRepository
    services/       # MatchingEngine, FeatureBuilder, InferenceClient(+fallback),
                    # RiskAggregator, PredictionScheduler, StateCache, WebSocketHub
    adapters/       # csv_telemetry_adapter (реальный датасет), synthetic_adapter (demo)
    api/            # Pydantic-схемы + FastAPI-роуты
    workers/        # TelemetryWorker (фоновый consumer топика telemetry)
    core/           # config (pydantic-settings), logging, DI-контейнер (composition root)
    main.py         # сборка приложения, lifespan, фоновые задачи, CORS
  inference_stub/   # отдельный контейнер-заглушка ML Inference Service
  scripts/          # seed_demo.py (демо за секунды), replay_csv.py (проигрывание датасета)
  tests/            # pytest: unit + API smoke-тесты
```

**Применённые паттерны (без фанатизма — только там, где реально меняется
поведение):**

- **Strategy + Decorator** — `HttpInferenceClient` /
  `HeuristicFallbackInferenceClient`, скомпонованные в
  `ResilientInferenceClient` (единственное место, где полиморфизм реально
  нужен: реализация ML-клиента меняется по конфигу/обстоятельствам).
- **Repository** — `TelemetryRepository`/`ScheduleRepository`/`PredictionRepository`
  инкапсулируют SQLAlchemy; домен и сервисы не знают, что БД — Postgres.
- **Composition root / DI** — `app/core/container.py`: все зависимости
  собираются в одном месте и раздаются через `FastAPI.Depends`, а не
  создаются по месту использования.
- **Single Responsibility** — каждый сервис (`MatchingEngine`,
  `FeatureBuilder`, `PredictionScheduler`, `RiskAggregator`,
  `WebSocketHub`) отвечает ровно за одну вещь; `PredictionScheduler` —
  единственный оркестратор, а не размазанная по роутам логика.

Сознательно **не** введено: абстрактных портов для БД (один Repository на
таблицу — этого достаточно, лишний интерфейс не даст переносимости,
которая реально нужна), generic message-broker обёртки (нужны ровно
`publish`/`subscribe`, не universal pub-sub framework), отдельного слоя
UseCase/CQRS — при таком размере сервиса это добавило бы файлы, а не
понятность.

## Что реализовано / что за рамками backend-задачи

Реализовано: приём и нормализация телеметрии/расписания, Matching Engine,
календарный планировщик обращений к ML со strict-horizon и safety-net,
устойчивый ML-клиент с деградацией, Risk Aggregator с порогами,
REST + WebSocket API, событийная шина с топиками
telemetry/features/predictions/alerts, Docker Compose, тесты.

Не реализовано (по вашей формулировке — не входит в backend-задачу):
собственно ML-модель (используется `inference_stub` до готовности вашего
образа — просто передайте нам контейнер с тем же `/predict`-контрактом),
парсер бинарного NDTP (входная точка для него —
`app/adapters/`/`POST /ingest/telemetry`, изолирована от остального
пайплайна), React-дашборд (backend отдаёт всё через REST/WebSocket,
вёрстка не входит в объём).

## Лицензии сторонних материалов

См. `LICENSES.md`.
