# grain-ledger
A ledger and stock management app for rice mills and departmental stores, with an AI agent for OCR data entry and crop disease advisory. Built with FastAPI, PostgreSQL, and React.

## Backend Structure
- `main.py` — Thin ASGI entrypoint for Render (`uvicorn main:app --host 0.0.0.0 --port $PORT`)
- `app/core/` — Configuration, SQLAlchemy database engine/session, security, and auth dependencies
- `app/models/` — SQLAlchemy ORM models
- `app/schemas/` — Pydantic request/response schemas
- `app/routes/` — FastAPI route handlers
- `app/services/` — Business logic and shared DB helpers
- `app/utils/` — Utility helpers
- `sql/` — Canonical schema and incremental SQL migrations
- `scripts/` — Local administrative and setup scripts
- `docs/` — Backend change notes and inspection docs
- `tests/` — Automated pytest suite

<br>
author surya
