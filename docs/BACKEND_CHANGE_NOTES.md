
# Grain Ledger Backend Change Notes

## Milestone 1 — Backend Folder Reorganization

The backend has been reorganized into a modular structure.

### Main structure

- `app/main.py` — FastAPI application entry point
- `app/core/` — Configuration, database, security and dependencies
- `app/models/` — SQLAlchemy models
- `app/schemas/` — Pydantic schemas
- `app/routes/` — API route modules
- `app/services/` — Business service modules
- `app/utils/` — Utility functions
- `sql/schema.sql` — Database schema
- `sql/migrations/` — SQL migration files
- `tests/` — Automated tests
- `scripts/` — Maintenance scripts
- `docs/` — Project documentation

### Authentication

The current authentication flow uses:

1. One password
2. OTP verification
3. JWT-based authenticated sessions

Miller and Commissiondar accounts remain independent.

### API preservation

The original and reorganized backend have matching API operations:

- 57 HTTP endpoint operations
- No missing endpoint paths or methods
- No additional endpoint paths or methods

This comparison verifies endpoint method/path preservation, not every internal implementation detail.

### Test results

Latest verified test result:

- 46 tests passed
- 1 warning
- No test failures

The warning concerns Starlette's deprecated use of `httpx` through its test client.

### Deployment safety

- No production database migrations were executed during this reorganization review.
- No production deployment was performed.
- No Git commit or push was performed.

### Important restrictions

- Miller and Commissiondar accounts must remain fully independent.
- Do not introduce cross-account dependencies.
- Do not change authentication without explicit approval.
- Do not run database migrations without approval.
- Complete local testing before deployment.
