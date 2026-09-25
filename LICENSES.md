# Лицензии сторонних материалов

Фиксируются по мере добавления зависимостей (п. 12.2.7 Положения
хакатона). Актуальный список пакетов и их версии — см.
`backend/requirements.txt` и `backend/inference_stub/requirements.txt`;
все перечисленные ниже распространяются под permissive-лицензиями,
совместимыми с использованием в конкурсной работе.

| Пакет | Лицензия |
|---|---|
| FastAPI | MIT |
| Starlette | BSD-3-Clause |
| Uvicorn | BSD-3-Clause |
| Pydantic / pydantic-settings | MIT |
| SQLAlchemy | MIT |
| asyncpg | Apache-2.0 |
| aiosqlite | MIT |
| httpx | BSD-3-Clause |
| redis-py | MIT |
| pandas | BSD-3-Clause |
| websockets | BSD-3-Clause |
| pytest / pytest-asyncio | MIT |

Docker-образы: `postgres:16-alpine` (PostgreSQL License), `redis:7-alpine`
(RSALv2/SSPLv1 — см. условия использования Redis Inc. для соответствующей
версии), `python:3.12-slim` (PSF License + Debian).
