-- Grain Ledger Phase 1 account and workflow additions.
-- BACK UP the database before running. Apply to the intended database only.
-- This migration adds columns/tables; it does not merge or delete existing records.

-- Business types and admin role supported by current application code.
ALTER TABLE businesses DROP CONSTRAINT IF EXISTS businesses_business_type_check;
ALTER TABLE businesses ADD CONSTRAINT businesses_business_type_check
    CHECK (business_type IN ('mill', 'store', 'commissiondar', 'system'));

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('owner', 'staff', 'party', 'admin'));
ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE users ADD COLUMN IF NOT EXISTS reviewed_by BIGINT REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_approval_status_check;
ALTER TABLE users ADD CONSTRAINT users_approval_status_check
    CHECK (approval_status IN ('pending', 'approved', 'rejected'));

-- A farmer may be associated with one Commissiondar contact in the same Miller account.
-- The API validates same-business ownership; this FK is not a login-account link.
ALTER TABLE parties ADD COLUMN IF NOT EXISTS associated_commissiondar_id BIGINT REFERENCES parties(id);

-- Per-intake packet and commission snapshot. Historical values remain unchanged.
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS packet_count NUMERIC(14,3);
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS packet_price NUMERIC(12,2);
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS commission_type VARCHAR(20);
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS commission_rate NUMERIC(12,2);
ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS commission_per_packet NUMERIC(12,2);
ALTER TABLE stock_movements ADD CONSTRAINT stock_movements_commission_type_check
    CHECK (commission_type IS NULL OR commission_type IN ('fixed', 'percentage'));

ALTER TABLE broker_commissions ADD COLUMN IF NOT EXISTS packet_count NUMERIC(14,3);
ALTER TABLE broker_commissions ADD COLUMN IF NOT EXISTS packet_price NUMERIC(12,2);
ALTER TABLE broker_commissions ADD COLUMN IF NOT EXISTS commission_type VARCHAR(20);
ALTER TABLE broker_commissions ADD COLUMN IF NOT EXISTS commission_rate NUMERIC(12,2);
ALTER TABLE broker_commissions ADD COLUMN IF NOT EXISTS commission_per_packet NUMERIC(12,2);
ALTER TABLE broker_commissions ADD CONSTRAINT broker_commissions_commission_type_check
    CHECK (commission_type IS NULL OR commission_type IN ('fixed', 'percentage'));

-- Private/global grain catalogue. Commissiondar-created types are scoped to their own business.
CREATE TABLE IF NOT EXISTS grain_types (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'quintal',
    owner_business_id BIGINT REFERENCES businesses(id) ON DELETE RESTRICT,
    created_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT grain_types_name_not_empty CHECK (length(trim(name)) > 0),
    CONSTRAINT grain_types_unit_not_empty CHECK (length(trim(unit)) > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_grain_types_global_name
    ON grain_types (lower(name)) WHERE owner_business_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_grain_types_business_name
    ON grain_types (owner_business_id, lower(name)) WHERE owner_business_id IS NOT NULL;

-- Commissiondar stock ledger. mill_name is plain text, not a foreign key or business link.
CREATE TABLE IF NOT EXISTS commissiondar_stock_movements (
    id BIGSERIAL PRIMARY KEY,
    commissiondar_id BIGINT NOT NULL REFERENCES parties(id),
    farmer_id BIGINT REFERENCES parties(id),
    business_id BIGINT REFERENCES businesses(id),
    item_id BIGINT REFERENCES items(id),
    grain_type_id BIGINT REFERENCES grain_types(id) ON DELETE RESTRICT,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('received_from_farmer', 'delivered_to_mill')),
    mill_name VARCHAR(200),
    quantity NUMERIC(14,3) NOT NULL CHECK (quantity <> 0),
    rate NUMERIC(12,2),
    movement_id BIGINT REFERENCES stock_movements(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_void BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (item_id IS NOT NULL OR grain_type_id IS NOT NULL)
);
ALTER TABLE commissiondar_stock_movements ADD COLUMN IF NOT EXISTS grain_type_id BIGINT REFERENCES grain_types(id) ON DELETE RESTRICT;
ALTER TABLE commissiondar_stock_movements ADD COLUMN IF NOT EXISTS mill_name VARCHAR(200);
ALTER TABLE commissiondar_stock_movements ALTER COLUMN item_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_commissiondar_stock_owner
    ON commissiondar_stock_movements(commissiondar_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commissiondar_stock_mill
    ON commissiondar_stock_movements(commissiondar_id, mill_name);

-- Operational tables referenced by the current SQLAlchemy models.
CREATE TABLE IF NOT EXISTS login_logs (
    id BIGSERIAL PRIMARY KEY,
    phone TEXT NOT NULL,
    user_id BIGINT REFERENCES users(id),
    success BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS issue_reports (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_parties_associated_commissiondar
    ON parties(associated_commissiondar_id);
