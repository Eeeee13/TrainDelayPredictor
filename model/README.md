# Модель прогноза задержки

Это модель, которая набрала **скор 1.0** в разделе Data Science (`submission_with_synthetic.csv`). LightGBM предсказывает поправку к `cur_dev_s`. Файл весов — `model.txt`.

Прогноз — задержка в секундах на остановке, плановое прибытие на которую через 10–15 минут. Плюс — опоздание, минус — опережение.

## Установка

```bash
pip install -r model/requirements.txt
```

Корень репозитория должен быть в `PYTHONPATH` (так и есть, если запускать из корня).

## Вызов

```python
from model import DelayPredictor

predictor = DelayPredictor()  # грузит model/model.txt
predictor.load_schedule("path/to/schedule_plan.csv")
predictor.set_telemetry("path/to/traffic.csv")

result = predictor.predict(tr_id=131672, T="2026-01-06 03:35:00", cur_dev_s=274)
# result["predicted_delay_s"] == 17.7
```

`cur_dev_s` — задержка на последней уже пройденной остановке, в секундах. Её считает бэкенд и передаёт в модель. Если подсказки нет, передайте `0`.

Если целевая остановка уже известна, передайте её явно:

```python
predictor.predict(
    tr_id=131672,
    T="2026-01-06 03:35:00",
    cur_dev_s=274,
    target_stop_id=53700172828,
    target_time_begin="2026-01-06 03:50:00",
)
```

Иначе цель выбирается сама: первая остановка с планом в интервале `(T+10, T+15]` минут.

## Поток телеметрии

Пакеты NDTP разбирает бэкенд. В модель отдаётся уже разобранная точка:

```python
predictor.add_fix(
    tr_id=131672,
    event_time=1767670500,  # unix-секунды или строка времени
    lon=37.62,
    lat=55.75,
    speed=18.0,
    location_valid=True,
)
```

Берутся только точки с `event_time <= T`. Точки в радиусе 3 км от Шереметьево и скачки быстрее 150 км/ч помечаются невалидными внутри модели.

## Колонки файлов

Расписание (`load_schedule`): `tr_id`, `time_begin`, `tt_action_item_id`, `manual_fill`, `geom` в виде `POINT (lon lat)`. Колонка `time_fact_begin` не нужна и в признаки не идёт.

Телеметрия (`set_telemetry`): `tr_id`, `event_time`, `location_valid`, `lon`, `lat`, `speed`.

Пакетный прогноз по таблице точек (`predict_points`): `tr_id`, `T`, `target_stop_id`, `target_time_begin`, `cur_dev_s`. Возвращает массив секунд в том же порядке.
