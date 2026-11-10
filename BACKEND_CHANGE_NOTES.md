# Grain Ledger Backend - Phase 1 Update

## Scope

This update adds Miller-owned Commissiondar contact management, farmer-to-contact assignment, per-packet commission snapshots, Commissiondar-owned farmer and grain management, and independent Commissiondar stock delivery with a manually entered mill name.

The Miller-side Mill-to-Commissiondar loan book remains a Miller-only record.

## Important account boundaries

- Miller Commissiondar contacts are `parties` with `party_type='commissiondar'` inside the Miller's own `business_id`.
- A Miller contact is not linked to a Commissiondar login user or the Commissiondar's independent business.
- `mill_commissiondar_loans` remain scoped to the Miller business and are not exposed to Commissiondar login endpoints.
- Commissiondar farmers are stored under the Commissiondar's own `business_id`.
- Commissiondar stock delivery stores `mill_name` as plain text. It has no foreign key to `businesses` and does not create a Miller-side stock movement or transaction.

## New and changed APIs

### Miller

- `POST /api/miller/commissiondars` - create a Miller-local contact.
- `GET /api/miller/commissiondars` - list contacts with visit, packet, quantity, commission, and Mill-loan summaries.
- `GET /api/miller/commissiondars/{contact_id}` - contact intake and Mill-loan history.
- `PUT /api/miller/commissiondars/{contact_id}` - update a contact.
- `POST /api/farmers` - accepts optional `associated_commissiondar_id`.
- `PUT /api/farmers/{farmer_id}` - update a farmer and assign a Miller-local Commissiondar contact.
- `GET /api/farmers` - includes Commissiondar contact ID and name.
- `POST /api/intake` - supports `packet_count`, `packet_price`, `commission_type` (`fixed` or `percentage`), and `commission_rate`. A farmer's associated contact is selected automatically unless an explicit matching contact is provided. Legacy `commission_amount` remains supported.
- `POST /api/payments` - Miller-owner-only.
- `GET /api/dashboard` - adds farmer/contact counts and last-seven-days intake summary and records.
- Existing `/api/mill-loans`, `/api/mill-loans/repay`, and `/api/broker-commissions` remain Miller-side.

### Commissiondar

- `GET /api/commissiondar/farmers` - list own farmers.
- `POST /api/commissiondar/farmers` - create own farmers.
- `GET /api/commissiondar/grain-types` - list global and own grain types.
- `POST /api/commissiondar/grain-types` - create a grain type owned by the Commissiondar business.
- `POST /api/commissiondar-stock/receive` - accepts an own farmer and either own `item_id` or `grain_type_id`.
- `POST /api/commissiondar-stock/deliver` - accepts `mill_name` as plain text and either own `item_id` or `grain_type_id`; no `business_id` is accepted or looked up.
- `GET /api/commissiondar-stock` - adds received, delivered, and on-hand totals, per-grain stock, and deliveries grouped by manually entered mill name.
- Existing `/api/commissiondar-loans` and repayments remain Commissiondar-only; farmer ownership is checked against the Commissiondar's own business.
- Commissiondar dashboard no longer reads Miller-owned `BrokerCommission` rows. `commissions_pending` is currently zero and `latest_commission` is null until a separate Commissiondar-owned commission-receivable workflow is specified.

## Database

- `models.py` and clean-install `schema.sql` include the farmer association, per-packet commission snapshot fields, grain catalogue, and Commissiondar stock ledger fields/table.
- `schema.sql` is for clean database installation only. Do not run it against an existing database.
- For an existing database, use `migrations/2026_11_11_phase1_existing_db_alignment.sql` only after a verified backup and local testing.
- Do not execute `migrations/2026_11_10_phase1_independent_accounts.sql` against the existing database. It does not correctly account for the existing database structure.
- The corrected migration was successfully applied to the local `grain_ledger_test` database.
- Post-migration verification confirmed that existing business IDs, user assignments, and stock/commission record counts were preserved.
- The Render database has not been migrated as part of this task.

## Validation status

- Python syntax compilation passed for `main.py`, `models.py`, and `test_main.py`.
- Local database migration completed successfully on `grain_ledger_test`.
- Post-migration schema and existing data were verified.
- Local pytest result: **38 passed, 1 warning**.
- The warning is a non-fatal Starlette/httpx deprecation warning.
- No Render service or production database was changed during this task.
