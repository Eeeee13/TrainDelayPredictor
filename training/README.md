# Пайплайн обучения

Тот же скрипт, которым собрана модель со скором 1.0. На выходе два бустера:

| Файл | Обучение | Скор на validate |
|---|---|---|
| `model_with_synthetic.txt` | реальные метки + точки каждую минуту + синтетические ТС | **1.0** |
| `model.txt` | то же без синтетических ТС | 0.891 |

В репозиторий для бэкенда положен первый файл: `model/model.txt`.

Факты расписания (`time_fact_begin`) используются только как ответы при обучении. В признаки идут план, `manual_fill`, телеметрия с `event_time <= T` и подсказка `cur_dev_s`.

## Данные

CSV хакатона в git не лежат. Нужен корень датасета:

```
dataset/
  train/schedule.csv
  train/traffic.csv
  test/schedule.csv
  test/traffic.csv
  validate/schedule_plan.csv
  validate/traffic.csv
  validate/points.csv
  labels/labels_train.csv
  labels/labels_test.csv
  sample_submission.csv
```

## Запуск

```bash
pip install -r training/requirements.txt
python training/train.py --data /path/to/dataset --out training/artifacts
```

Скрипт печатает честную leave-vehicle-out кросс-валидацию и пишет в `--out`:

- `model_with_synthetic.txt` — модель для бэкенда
- `model.txt`
- `submission_with_synthetic.csv`, `submission.csv`
- `oof.csv` — прогнозы кросс-валидации на реальных метках

Чтобы обновить модель в репозитории, замените `model/model.txt` файлом `model_with_synthetic.txt`.
