-- Generic ledger + stock schema (PostgreSQL)
-- Works for rice mills and departmental stores.
-- Every table carries business_id so each business's data stays separate (multi-tenant).
-- Money and quantities use NUMERIC, never FLOAT.

CREATE TABLE businesses (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    business_type TEXT NOT NULL CHECK (business_type IN ('mill', 'store')),
    phone         TEXT,
    address       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- People who log in (owner, staff, or a farmer/customer viewing their own account)
CREATE TABLE users (
    id          BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(id),
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,          -- OTP login
    role        TEXT NOT NULL CHECK (role IN ('owner', 'staff', 'party')),
    party_id    BIGINT,                         -- set when role = 'party'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Farmers, customers, suppliers, buyers: all "parties"
CREATE TABLE parties (
    id              BIGSERIAL PRIMARY KEY,
    business_id     BIGINT NOT NULL REFERENCES businesses(id),
    name            TEXT NOT NULL,
    phone           TEXT,
    village         TEXT,
    party_type      TEXT NOT NULL CHECK (party_type IN ('farmer', 'customer', 'supplier', 'buyer', 'commissiondar')),
    opening_balance NUMERIC(14,2) NOT NULL DEFAULT 0,  -- +ve = party owes us, -ve = we owe party
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users
    ADD CONSTRAINT users_party_fk FOREIGN KEY (party_id) REFERENCES parties(id);

-- Paddy varieties, rice, broken rice, bran, husk, or store products
CREATE TABLE items (
    id            BIGSERIAL PRIMARY KEY,
    business_id   BIGINT NOT NULL REFERENCES businesses(id),
    name          TEXT NOT NULL,               -- e.g. 'BPT 5204 Paddy', 'Sona Masuri Rice', 'Toor Dal 1kg'
    category      TEXT,                        -- 'paddy', 'rice', 'by-product', 'grocery'
    unit          TEXT NOT NULL,               -- 'quintal', 'kg', 'bag', 'packet', 'litre'
    sku           TEXT,
    sale_price    NUMERIC(12,2),
    gst_rate      NUMERIC(5,2) DEFAULT 0,
    reorder_level NUMERIC(12,3),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (business_id, name)
);

-- Every change in stock is a row. Stock = SUM(quantity).
-- quantity is signed: +ve = stock in, -ve = stock out.
-- party_id says whose stock it is (e.g. a farmer's paddy kept at the mill) or who we traded with.
CREATE TABLE stock_movements (
    id            BIGSERIAL PRIMARY KEY,
    business_id   BIGINT NOT NULL REFERENCES businesses(id),
    item_id       BIGINT NOT NULL REFERENCES items(id),
    party_id      BIGINT REFERENCES parties(id),
    movement_type TEXT NOT NULL CHECK (movement_type IN
                    ('purchase', 'sale', 'milling_in', 'milling_out', 'return', 'adjustment')),
    quantity      NUMERIC(14,3) NOT NULL CHECK (quantity <> 0),
    rate          NUMERIC(12,2),               -- price per unit at that time
    moisture_pct  NUMERIC(5,2),                -- paddy intake only
    moved_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    note          TEXT,
    created_by    BIGINT REFERENCES users(id),
    broker_id     BIGINT REFERENCES parties(id),   -- commissiondar who brokered this intake, NULL if none
    is_void       BOOLEAN NOT NULL DEFAULT FALSE  -- never delete; void and re-enter instead
);

-- Money owed between the business and a party.
-- Balance = SUM(debit) - SUM(credit) (+ opening_balance).
--   debit  = party owes us more   (we sold on credit, or we paid them an advance)
--   credit = party owes us less   (they paid us, or we bought from them and owe them)
CREATE TABLE ledger_entries (
    id           BIGSERIAL PRIMARY KEY,
    business_id  BIGINT NOT NULL REFERENCES businesses(id),
    party_id     BIGINT NOT NULL REFERENCES parties(id),
    entry_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    debit        NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
    credit       NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
    movement_id  BIGINT REFERENCES stock_movements(id),  -- link to the trade that caused it
    payment_id   BIGINT,                                  -- link to a payment (FK added below)
    note         TEXT,
    is_void      BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK ((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))
);

CREATE TABLE payments (
    id          BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(id),
    party_id    BIGINT NOT NULL REFERENCES parties(id),
    direction   TEXT NOT NULL CHECK (direction IN ('paid', 'received')),
    amount      NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    mode        TEXT CHECK (mode IS NULL OR mode IN ('cash', 'upi', 'bank', 'cheque')),  -- optional
    paid_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    note        TEXT,
    created_by  BIGINT REFERENCES users(id),
    is_void     BOOLEAN NOT NULL DEFAULT FALSE
);

ALTER TABLE ledger_entries
    ADD CONSTRAINT ledger_payment_fk FOREIGN KEY (payment_id) REFERENCES payments(id);

-- ---------------------------------------------------------------
-- Commissiondars (broker agents)
-- ---------------------------------------------------------------
-- A commissiondar has TWO separate, unrelated relationships:
--   1. Broker role: brings farmers' paddy to a mill, earns a commission FROM THE MILL.
--      This belongs to the mill's business and the miller is meant to see it.
--   2. Lender role: gives farmers crop loans at interest, BEFORE harvest.
--      This is strictly between the commissiondar and the farmer. The miller
--      must never see this, so these tables intentionally carry no business_id
--      and no query here should ever be joined into a miller-facing endpoint.

-- 1. Broker commission -- visible to the mill, since the mill pays it.
CREATE TABLE broker_commissions (
    id                 BIGSERIAL PRIMARY KEY,
    business_id        BIGINT NOT NULL REFERENCES businesses(id),   -- mill that owes the commission
    commissiondar_id   BIGINT NOT NULL REFERENCES parties(id),
    farmer_id          BIGINT REFERENCES parties(id),               -- original farmer, for traceability only
    movement_id        BIGINT REFERENCES stock_movements(id),       -- the intake this commission is for
    commission_amount  NUMERIC(12,2) NOT NULL CHECK (commission_amount >= 0),
    is_paid            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_void            BOOLEAN NOT NULL DEFAULT FALSE
);

-- 2. Crop loans -- NOT visible to the mill. No business_id, by design.
CREATE TABLE commissiondar_loans (
    id               BIGSERIAL PRIMARY KEY,
    commissiondar_id BIGINT NOT NULL REFERENCES parties(id),
    farmer_id        BIGINT NOT NULL REFERENCES parties(id),
    principal        NUMERIC(14,2) NOT NULL CHECK (principal > 0),
    interest_rate_pa NUMERIC(5,2) NOT NULL DEFAULT 0,   -- annual simple-interest rate, e.g. 18.00 for 18%/year
    issued_at        DATE NOT NULL DEFAULT CURRENT_DATE,
    status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    note             TEXT,
    is_void          BOOLEAN NOT NULL DEFAULT FALSE
);

-- Every repayment is its own row -- never overwrite a running total.
CREATE TABLE commissiondar_loan_repayments (
    id        BIGSERIAL PRIMARY KEY,
    loan_id   BIGINT NOT NULL REFERENCES commissiondar_loans(id),
    amount    NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    paid_at   DATE NOT NULL DEFAULT CURRENT_DATE,
    note      TEXT,
    is_void   BOOLEAN NOT NULL DEFAULT FALSE
);

-- 3. Mill's loan to a commissiondar -- visible to the mill, since the mill is
--    directly a party to this one (unlike the farmer crop loans above).
--    Typically how a mill keeps a commissiondar supplied with cash to buy paddy.
CREATE TABLE mill_commissiondar_loans (
    id               BIGSERIAL PRIMARY KEY,
    business_id      BIGINT NOT NULL REFERENCES businesses(id),   -- the mill lending the money
    commissiondar_id BIGINT NOT NULL REFERENCES parties(id),
    principal        NUMERIC(14,2) NOT NULL CHECK (principal > 0),
    interest_rate_pa NUMERIC(5,2) NOT NULL DEFAULT 0,
    issued_at        DATE NOT NULL DEFAULT CURRENT_DATE,
    status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    note             TEXT,
    is_void          BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE mill_commissiondar_loan_repayments (
    id        BIGSERIAL PRIMARY KEY,
    loan_id   BIGINT NOT NULL REFERENCES mill_commissiondar_loans(id),
    amount    NUMERIC(14,2) NOT NULL CHECK (amount > 0),
    paid_at   DATE NOT NULL DEFAULT CURRENT_DATE,
    note      TEXT,
    is_void   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_mill_loans_business      ON mill_commissiondar_loans(business_id);
CREATE INDEX idx_mill_loans_commissiondar ON mill_commissiondar_loans(commissiondar_id);
CREATE INDEX idx_mill_repayments_loan     ON mill_commissiondar_loan_repayments(loan_id);

-- Same simple-interest, calculated-on-demand approach as the farmer crop loans:
--
-- SELECT
--     l.id, l.principal, l.interest_rate_pa,
--     l.principal * l.interest_rate_pa / 100
--         * (CURRENT_DATE - l.issued_at) / 365.0                AS interest_accrued,
--     COALESCE((SELECT SUM(r.amount) FROM mill_commissiondar_loan_repayments r
--               WHERE r.loan_id = l.id AND NOT r.is_void), 0)    AS total_repaid,
--     l.principal
--       + l.principal * l.interest_rate_pa / 100 * (CURRENT_DATE - l.issued_at) / 365.0
--       - COALESCE((SELECT SUM(r.amount) FROM mill_commissiondar_loan_repayments r
--                   WHERE r.loan_id = l.id AND NOT r.is_void), 0) AS outstanding
-- FROM mill_commissiondar_loans l
-- WHERE l.business_id = :biz AND NOT l.is_void;

CREATE INDEX idx_broker_comm_business ON broker_commissions(business_id);
CREATE INDEX idx_loans_commissiondar  ON commissiondar_loans(commissiondar_id);
CREATE INDEX idx_loans_farmer         ON commissiondar_loans(farmer_id);
CREATE INDEX idx_repayments_loan      ON commissiondar_loan_repayments(loan_id);

-- Interest is simple interest, accrued daily, and is never stored as a fixed
-- number -- it's always calculated fresh from principal, rate, and days elapsed,
-- the same "never store a derived number" rule the rest of this schema follows.
--
-- Outstanding balance on a loan (principal + accrued interest - repayments):
--
-- SELECT
--     l.id,
--     l.principal,
--     l.interest_rate_pa,
--     l.principal * l.interest_rate_pa / 100
--         * (CURRENT_DATE - l.issued_at) / 365.0                AS interest_accrued,
--     COALESCE((SELECT SUM(r.amount) FROM commissiondar_loan_repayments r
--               WHERE r.loan_id = l.id AND NOT r.is_void), 0)    AS total_repaid,
--     l.principal
--       + l.principal * l.interest_rate_pa / 100 * (CURRENT_DATE - l.issued_at) / 365.0
--       - COALESCE((SELECT SUM(r.amount) FROM commissiondar_loan_repayments r
--                   WHERE r.loan_id = l.id AND NOT r.is_void), 0) AS outstanding
-- FROM commissiondar_loans l
-- WHERE l.commissiondar_id = :commissiondar_id AND NOT l.is_void;

-- Indexes for the queries the app runs most
CREATE INDEX idx_parties_business   ON parties(business_id);
CREATE INDEX idx_items_business     ON items(business_id);
CREATE INDEX idx_stock_item         ON stock_movements(business_id, item_id);
CREATE INDEX idx_stock_party        ON stock_movements(business_id, party_id);
CREATE INDEX idx_ledger_party       ON ledger_entries(business_id, party_id);
CREATE INDEX idx_payments_party     ON payments(business_id, party_id);

-- ---------------------------------------------------------------
-- Useful queries (replace :biz with the business id)
-- ---------------------------------------------------------------

-- 1. Total stock per item
-- SELECT i.name, SUM(m.quantity) AS in_stock, i.unit
-- FROM stock_movements m JOIN items i ON i.id = m.item_id
-- WHERE m.business_id = :biz AND NOT m.is_void
-- GROUP BY i.name, i.unit;

-- 2. Stock held for each farmer, per item
-- SELECT p.name AS farmer, i.name AS item, SUM(m.quantity) AS stock
-- FROM stock_movements m
-- JOIN parties p ON p.id = m.party_id
-- JOIN items i   ON i.id = m.item_id
-- WHERE m.business_id = :biz AND NOT m.is_void
-- GROUP BY p.name, i.name;

-- 3. Balance per party (+ve = party owes us, -ve = we owe party)
-- SELECT p.name,
--        p.opening_balance + COALESCE(SUM(l.debit - l.credit), 0) AS balance
-- FROM parties p
-- LEFT JOIN ledger_entries l ON l.party_id = p.id AND NOT l.is_void
-- WHERE p.business_id = :biz
-- GROUP BY p.id, p.name, p.opening_balance;

-- 4. Low-stock items
-- SELECT i.name, SUM(m.quantity) AS in_stock, i.reorder_level
-- FROM items i JOIN stock_movements m ON m.item_id = i.id AND NOT m.is_void
-- WHERE i.business_id = :biz
-- GROUP BY i.id HAVING SUM(m.quantity) <= i.reorder_level;
