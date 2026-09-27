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
3. **BI-дашборд** (`frontend/`) — карта и список транспорта из `GET /dashboard/snapshot`,
   live-обновления через `ws://.../ws/risk`.

---

## Быстрый старт

```bash
docker compose up --build

curl http://localhost:8000/health
docker compose exec backend curl -fs http://inference:8000/health
open http://localhost:8000/docs     # Swagger backend
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

Сырой NDTP принимает TCP-сервер backend на порту `9201`. Пример конфигурации эмулятора — `emulator_sample_config.json`. Нормализованные JSON-батчи по-прежнему можно отправить через `POST /ingest/telemetry`.

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
  `(10, 15]` минут, эта пара `(tr_id, target_stop_id)` становится «due» —
  по ней делается ровно один «первый» прогноз, максимально рано (в начале
  окна, т.е. ближе к 15 минутам), это и есть раннее предупреждение.
- Раз в ~60с идёт страховочный пересчёт (`APP_SAFETY_RECOMPUTE_INTERVAL_S`),
  но **только** для пар, уже получивших первый прогноз и находящихся в
  риске `HIGH`, и только пока цель находится в окне `(10, 15]` минут. Он никогда не
  создаёт новый «первый» алерт и никогда не срабатывает постфактум.
- Анти-утечка по времени: пары, чьё `target_time_begin <= now`, никогда не
  попадают в батч на прогноз — «прогнозов задним числом» не бывает
  архитектурно, а не по соглашению.
- Если окно пропущено, новый прогноз не создаётся. Резервный прогноз по `cur_dev_s` также разрешён только в `(10, 15]` минут.

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

## Лицензии сторонних материалов

См. `LICENSES.md`.

## Запуск системы

Нужен Docker Compose и локальная папка распакованного датасета. Перед запуском задайте абсолютный путь:

```bash
export DATASET_PATH=/absolute/path/to/dataset
docker compose up --build
```

Дашборд: `http://localhost` (порт 80). Backend API и Swagger: `http://localhost:8000/docs`. Приёмник NDTP: порт `9201`. PostgreSQL, Redis, inference и Airflow наружу не публикуются: к модели с хоста обращаются через сеть Compose, `http://inference:8000`. При первом старте Airflow `standalone` выводит пароль администратора в `docker compose logs airflow`. DAG `delay_retraining` запускается каждые пять минут и допускает ручной запуск.

### Исторический replay

После запуска сервисов:

```bash
docker compose exec backend python -m scripts.replay_csv \
  --schedule /dataset/train/schedule.csv \
  --traffic /dataset/train/traffic.csv \
  --backend http://localhost:8000 --speed 30
```

Replay сохраняет даты датасета и выставляет виртуальные часы backend; входные времена отправляются с московским часовым поясом. Откройте `GET /risk` либо WebSocket `/ws/risk` для прогнозов. В ML API `GET /model/info` показывает текущую версию.

### Эмулятор NDTP

TCP-приёмник backend слушает порт `9201`. Соответствие `unitId` эмулятора и `tr_id` рейса хранится в Redis и задаётся через API, а не переменной окружения:

```bash
curl -X POST http://localhost:8000/ndtp-mapping \
  -H 'content-type: application/json' \
  -d '{"893159":122048}'
```

Ключ — `unitId`, значение — `tr_id`. `GET /ndtp-mapping` возвращает текущую карту, `DELETE /ndtp-mapping` очищает её. Тело конфигурации самого эмулятора лежит в `emulator_sample_config.json`: `targetHost=host.docker.internal`, `targetPort=9201`, у блоков `autoGenerate: true`. Это проверка живого приёма и GPS-трека, а не воспроизведение маршрута из CSV. Для прогноза нужны согласованные с текущим временем плановые остановки в ближайшие 10–15 минут и телеметрия вдоль их маршрута. Исторические факты для обучения поступают через Airflow, поскольку эмулятор их не передаёт.

### Модель и переобучение

Сервис inference читает телеметрию и плановые остановки из PostgreSQL с ролью `inference_ro`, у которой есть только `SELECT`. В начале он использует `model/model.txt`. Airflow постепенно открывает исторические записи `train`, строит признаки готовым кодом `training/train.py`, оценивает кандидата на неизменном `test` и при улучшении записывает `active.json` в общий volume. Сервис подхватывает новую модель при следующем запросе; при ошибке загрузки продолжает использовать предыдущую. Список артефактов версий находится в volume `models`. Для отката на существующую версию: `docker compose exec airflow python -m ml_pipeline.rollback VERSION`.

Для прямой проверки ML API отправьте запрос из сети Compose, например `docker compose exec backend curl -s http://inference:8000/predict`, в формате:

```json
{"items":[{"request_id":"demo-1","tr_id":131672,"T":"2026-01-06T00:35:00Z","cur_dev_s":274,"target_stop_id":53700172828,"target_time_begin":"2026-01-06T00:50:00Z"}]}
```

Времена API и БД — UTC. В исторических CSV время московское, без явного часового пояса; адаптер replay помечает его `Europe/Moscow`. Для расчёта признаков ML-сервис переводит UTC обратно в московское локальное время.

## Диспетчерский интерфейс

После `docker compose up --build` откройте `http://localhost`. Frontend
раздаётся Nginx, который проксирует `/dashboard/snapshot` и `/ws/risk` в backend.
Карта показывает активные ТС и их пройденный за последние 30 минут путь по
валидным GPS-точкам. Пунктиром выделяется приблизительный участок до целевой
остановки при среднем и высоком риске: точной геометрии улиц в CSV нет.
Старые точки и прогнозы скрываются.

Доступны поиск по борту/маршруту, выбор маршрута, фильтр уровня риска и
переключатель «С прогнозом». Для разработки: `cd frontend && npm ci && npm run dev`;
Vite проксирует запросы к backend на `localhost:8000`.

### Сквозная проверка на реальном CSV

Локальный `.env` должен содержать `DATASET_PATH` — абсолютный путь к каталогу
с `train/schedule.csv` и `train/traffic.csv`. Затем:

```bash
docker compose up -d --build backend frontend
docker compose exec backend python -m scripts.smoke_csv_dashboard \
  --schedule /dataset/train/schedule.csv \
  --traffic /dataset/train/traffic.csv \
  --vehicle 133300 \
  --start-at 2026-01-06T17:45:00 \
  --end-at 2026-01-06T18:25:00 \
  --speed 60
```

Скрипт воспроизводит настоящий 40-минутный фрагмент с виртуальными часами,
проверяет ответ модели, горизонт прогноза и наличие ТС, GPS-пути и целевой
остановки в ответе фронтенда. При успехе печатает JSON с `status: passed`.
После replay виртуальные часы останавливаются, чтобы карту можно было изучить.
Для возврата к текущему времени: `curl -X POST http://localhost:8000/ingest/replay-clock/resume-live`.


## Вероятность опоздания более чем на две минуты

ML API `/predict` и backend `/risk`, `/risk/{vehicle_id}`, `/dashboard/snapshot`
и WebSocket `/ws/risk` возвращают `delay_probability`: число от 0 до 1 либо `null`.
Это **P(target_delay_s > 120)** на целевой остановке, не уверенность в регрессии.
Ровно 120 секунд не относится к событию. `confidence` не меняется.
Карточка и подробности показывают округлённый процент рядом с задержкой;
при `null` подпись скрыта. Цвета риска и причины остаются прежними.

Вероятность рассчитывается отдельным LightGBM и сигмоидальным калибратором.
Начальный классификатор использует тот же train + test, синтетику и дополнительные
примеры, что финальная конкурсная регрессия. Калибратор обучен на исходных точках
реальных ТС по OOF-прогнозам: ТС, его синтетические копии и сгенерированные точки
всегда исключаются из обучения вместе. Метрики подгонки калибратора в JSON
не являются независимой оценкой качества. Регрессор и сабмиты не изменяются.

Повторное обучение только вероятности (зависимости `training/requirements.txt`):

```bash
python -m training.train_probability --data /path/to/dataset --out model
```

Комплект: `model.txt`, `classifier.txt`, `calibrator.json`. Старые версии без
классификатора и резервные прогнозы возвращают вероятность `null`. Частично
повреждённый комплект не загружается; работающий inference сохраняет предыдущий.

### Исправленный исторический Airflow

DAG по-прежнему проверяет данные каждые пять минут, часы истории идут ×6.
Обучение не связано с автогенерацией NDTP. Label доступен только когда известны
фактическое прибытие целевой остановки **и** момент прогноза T. Сопоставление —
по `(tr_id, target_stop_id, target_time_begin)`. Отсутствующие, неоднозначные и
некорректные факты исключаются; причины отражены в `label-report.json`.
Дополнительные примеры используют полный план и только факты, известные на T.
Кеш `causal-bundle-v2` отделён от старых результатов; снимок включает также test.

Кандидаты обучаются на доступном train. Для публикации на фиксированном test
нужно строго улучшить MAE и не ухудшить Brier score относительно активного
классификатора, если он есть. В отчёте также сохраняется log loss. При отсутствии
активной версии эталон — встроенная модель, а не `cur_dev_s`.
Встроенная конкурсная модель уже обучалась на test: это техническое сравнение
перед заменой, **не независимая оценка**. Ответы validate остаются у платформы.

Если данных недостаточно для групповой калибровки с двумя классами, публикация
пропускается с причиной. Нефинитные результаты и ошибки комплекта блокируют
публикацию. Весь комплект проверяется и активируется атомарно. Оценка привязана
к содержимому эталона; при его смене перед публикацией сравнение повторяется.
Откат переключает весь комплект под общей блокировкой публикации:

```bash
docker compose exec airflow python -m ml_pipeline.rollback VERSION
```

Существующий `active.json` автоматически не сбрасывается: старая опубликованная
модель может по-прежнему возвращать `null`, пока не активирован комплект с
классификатором. Для использования добавленных встроенных артефактов контейнеры
inference и Airflow необходимо пересобрать. Миграция backend добавляет nullable
колонки без удаления старых записей.

ML-сервис загружает начальный комплект до приёма запросов и использует один поток
LightGBM на модель. Таймаут backend `APP_INFERENCE_TIMEOUT_S=2`; при превышении
возвращается fallback без вероятности. Локальная проверка пакета из 23 ТС дала
1,552 с для первого HTTP-запроса и 0,519/0,481 с для следующих; это проверка
конкретного пакета, а не гарантия времени под произвольной нагрузкой.
