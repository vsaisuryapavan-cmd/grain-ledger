-- Grain Ledger Phase 1: schema alignment for existing databases.
-- Apply to grain_ledger_test only after reviewing and backing up.
-- Does not recreate businesses, users, grain_types, login_logs or issue_reports.

BEGIN;

-- 1. Miller-local Commissiondar contacts.

ALTER TABLE parties
    ADD COLUMN IF NOT EXISTS associated_commissiondar_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'parties'::regclass
          AND conname = 'parties_associated_commissiondar_id_fkey'
    ) THEN
        ALTER TABLE parties
            ADD CONSTRAINT parties_associated_commissiondar_id_fkey
            FOREIGN KEY (associated_commissiondar_id)
            REFERENCES parties(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_parties_associated_commissiondar
    ON parties(associated_commissiondar_id);


-- 2. Miller stock movement commission snapshots.

ALTER TABLE stock_movements
    ADD COLUMN IF NOT EXISTS packet_count NUMERIC(14,3),
    ADD COLUMN IF NOT EXISTS packet_price NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS commission_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS commission_rate NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS commission_per_packet NUMERIC(12,2);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'stock_movements'::regclass
          AND conname = 'stock_movements_commission_type_check'
    ) THEN
        ALTER TABLE stock_movements
            ADD CONSTRAINT stock_movements_commission_type_check
            CHECK (
                commission_type IS NULL
                OR commission_type IN ('fixed', 'percentage')
            ) NOT VALID;
    END IF;
END $$;

ALTER TABLE stock_movements
    VALIDATE CONSTRAINT stock_movements_commission_type_check;


-- 3. Broker commission snapshots.

ALTER TABLE broker_commissions
    ADD COLUMN IF NOT EXISTS packet_count NUMERIC(14,3),
    ADD COLUMN IF NOT EXISTS packet_price NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS commission_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS commission_rate NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS commission_per_packet NUMERIC(12,2);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'broker_commissions'::regclass
          AND conname = 'broker_commissions_commission_type_check'
    ) THEN
        ALTER TABLE broker_commissions
            ADD CONSTRAINT broker_commissions_commission_type_check
            CHECK (
                commission_type IS NULL
                OR commission_type IN ('fixed', 'percentage')
            ) NOT VALID;
    END IF;
END $$;

ALTER TABLE broker_commissions
    VALIDATE CONSTRAINT broker_commissions_commission_type_check;


-- 4. Commissiondar custom grain types and manual mill-name history.

ALTER TABLE commissiondar_stock_movements
    ADD COLUMN IF NOT EXISTS grain_type_id BIGINT,
    ADD COLUMN IF NOT EXISTS mill_name VARCHAR(200);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'commissiondar_stock_movements'::regclass
          AND conname = 'commissiondar_stock_grain_type_fk'
    ) THEN
        ALTER TABLE commissiondar_stock_movements
            ADD CONSTRAINT commissiondar_stock_grain_type_fk
            FOREIGN KEY (grain_type_id)
            REFERENCES grain_types(id)
            ON DELETE RESTRICT;
    END IF;
END $$;

-- Allow a custom grain type without an items-table record.
ALTER TABLE commissiondar_stock_movements
    ALTER COLUMN item_id DROP NOT NULL;


-- 5. Validate stock movement types and grain references.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'commissiondar_stock_movements'::regclass
          AND conname = 'commissiondar_stock_movement_type_check'
    ) THEN
        ALTER TABLE commissiondar_stock_movements
            ADD CONSTRAINT commissiondar_stock_movement_type_check
            CHECK (
                movement_type IN (
                    'received_from_farmer',
                    'delivered_to_mill'
                )
            ) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'commissiondar_stock_movements'::regclass
          AND conname = 'commissiondar_stock_item_or_grain_check'
    ) THEN
        ALTER TABLE commissiondar_stock_movements
            ADD CONSTRAINT commissiondar_stock_item_or_grain_check
            CHECK (item_id IS NOT NULL OR grain_type_id IS NOT NULL)
            NOT VALID;
    END IF;
END $$;

ALTER TABLE commissiondar_stock_movements
    VALIDATE CONSTRAINT commissiondar_stock_movement_type_check;

ALTER TABLE commissiondar_stock_movements
    VALIDATE CONSTRAINT commissiondar_stock_item_or_grain_check;

CREATE INDEX IF NOT EXISTS idx_commissiondar_stock_owner
    ON commissiondar_stock_movements(commissiondar_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_commissiondar_stock_mill
    ON commissiondar_stock_movements(commissiondar_id, mill_name);

COMMIT;