CREATE TABLE IF NOT EXISTS commissiondar_mills (
    id BIGSERIAL PRIMARY KEY,
    commissiondar_id BIGINT NOT NULL REFERENCES parties(id),
    business_id BIGINT NOT NULL REFERENCES businesses(id),
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_commissiondar_mill_name
        UNIQUE (commissiondar_id, name),

    CONSTRAINT commissiondar_mill_name_not_empty
        CHECK (length(trim(name)) > 0)
);

-- One farmer can be associated with multiple mills.
CREATE TABLE IF NOT EXISTS commissiondar_mill_farmers (
    id BIGSERIAL PRIMARY KEY,
    commissiondar_id BIGINT NOT NULL REFERENCES parties(id),
    mill_id BIGINT NOT NULL REFERENCES commissiondar_mills(id),
    farmer_id BIGINT NOT NULL REFERENCES parties(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_commissiondar_mill_farmer
        UNIQUE (mill_id, farmer_id)
);

-- Manually recorded commission earned from each mill.
CREATE TABLE IF NOT EXISTS commissiondar_mill_commissions (
    id BIGSERIAL PRIMARY KEY,
    commissiondar_id BIGINT NOT NULL REFERENCES parties(id),
    mill_id BIGINT NOT NULL REFERENCES commissiondar_mills(id),
    commission_amount NUMERIC(14,2) NOT NULL
        CHECK (commission_amount > 0),
    earned_at DATE NOT NULL DEFAULT CURRENT_DATE,
    note TEXT,
    is_void BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Individual full or partial commission payments received.
CREATE TABLE IF NOT EXISTS commissiondar_mill_commission_receipts (
    id BIGSERIAL PRIMARY KEY,
    commissiondar_id BIGINT NOT NULL REFERENCES parties(id),
    commission_id BIGINT NOT NULL
        REFERENCES commissiondar_mill_commissions(id),
    amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    received_at DATE NOT NULL DEFAULT CURRENT_DATE,
    note TEXT,
    is_void BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commissiondar_mills_owner
    ON commissiondar_mills(commissiondar_id, is_active);

CREATE INDEX IF NOT EXISTS idx_commissiondar_mill_farmers_mill
    ON commissiondar_mill_farmers(commissiondar_id, mill_id);

CREATE INDEX IF NOT EXISTS idx_commissiondar_mill_farmers_farmer
    ON commissiondar_mill_farmers(commissiondar_id, farmer_id);

CREATE INDEX IF NOT EXISTS idx_commissiondar_mill_commissions_mill
    ON commissiondar_mill_commissions(commissiondar_id, mill_id, earned_at DESC);

CREATE INDEX IF NOT EXISTS idx_commissiondar_mill_receipts_commission
    ON commissiondar_mill_commission_receipts(commissiondar_id, commission_id);

