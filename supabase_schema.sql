-- =============================================================
-- Supabase Schema for fin-tech-d
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- =============================================================

-- 1. User-specific tables --

-- Portfolio holdings (one row per holding per user)
CREATE TABLE IF NOT EXISTS portfolio (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    ticker      TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT 'stock',
    investment_mode TEXT NOT NULL DEFAULT 'lumpsum',
    buy_price   NUMERIC NOT NULL DEFAULT 0,
    quantity    NUMERIC NOT NULL DEFAULT 0,
    buy_date    TEXT NOT NULL DEFAULT '',
    sip_monthly NUMERIC NOT NULL DEFAULT 0,
    sip_date    INT NOT NULL DEFAULT 0,
    amfi_code   TEXT NOT NULL DEFAULT '',
    transactions JSONB NOT NULL DEFAULT '[]',
    sip_pause_periods JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Budget (one row per user)
CREATE TABLE IF NOT EXISTS budget (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    income      NUMERIC NOT NULL DEFAULT 0,
    expenses    NUMERIC NOT NULL DEFAULT 0,
    investments NUMERIC NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Goals (multiple per user)
CREATE TABLE IF NOT EXISTS goals (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    target      NUMERIC NOT NULL DEFAULT 0,
    years       NUMERIC NOT NULL DEFAULT 5,
    expected_return NUMERIC NOT NULL DEFAULT 12,
    monthly_sip NUMERIC NOT NULL DEFAULT 0,
    created_date TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- 2. Global tables (shared across all users, written by bot) --

CREATE TABLE IF NOT EXISTS gold_predictions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date        TEXT NOT NULL UNIQUE,
    signal      TEXT NOT NULL,
    confidence  INT NOT NULL DEFAULT 0,
    price_at_prediction NUMERIC NOT NULL DEFAULT 0,
    total_score INT NOT NULL DEFAULT 0,
    prediction_text TEXT NOT NULL DEFAULT '',
    factor_scores JSONB NOT NULL DEFAULT '[]',
    verified    BOOLEAN NOT NULL DEFAULT false,
    actual_price_after NUMERIC,
    was_correct BOOLEAN
);

CREATE TABLE IF NOT EXISTS silver_predictions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date        TEXT NOT NULL UNIQUE,
    signal      TEXT NOT NULL,
    confidence  INT NOT NULL DEFAULT 0,
    price_at_prediction NUMERIC NOT NULL DEFAULT 0,
    total_score INT NOT NULL DEFAULT 0,
    prediction_text TEXT NOT NULL DEFAULT '',
    factor_scores JSONB NOT NULL DEFAULT '[]',
    verified    BOOLEAN NOT NULL DEFAULT false,
    actual_price_after NUMERIC,
    was_correct BOOLEAN
);

CREATE TABLE IF NOT EXISTS scanner_predictions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date        TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    signal      TEXT NOT NULL DEFAULT '',
    urgency     TEXT NOT NULL DEFAULT '',
    price_at_prediction NUMERIC NOT NULL DEFAULT 0,
    rsi         NUMERIC,
    from_high_pct NUMERIC,
    buy_verdict TEXT NOT NULL DEFAULT '',
    buy_reasoning JSONB NOT NULL DEFAULT '[]',
    risk_level  TEXT NOT NULL DEFAULT '',
    pe_ratio    NUMERIC,
    sector      TEXT NOT NULL DEFAULT '',
    verified    BOOLEAN NOT NULL DEFAULT false,
    actual_price_7d NUMERIC,
    actual_price_30d NUMERIC,
    was_correct_7d BOOLEAN,
    was_correct_30d BOOLEAN,
    UNIQUE(date, ticker)
);

-- Stock-specific predictions (from holdings analysis)
CREATE TABLE IF NOT EXISTS stock_predictions (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date        TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    signal      TEXT NOT NULL DEFAULT '',
    confidence  INT NOT NULL DEFAULT 0,
    price_at_prediction NUMERIC NOT NULL DEFAULT 0,
    total_score INT NOT NULL DEFAULT 0,
    prediction_text TEXT NOT NULL DEFAULT '',
    factor_scores JSONB NOT NULL DEFAULT '[]',
    verified    BOOLEAN NOT NULL DEFAULT false,
    actual_price_after NUMERIC,
    was_correct BOOLEAN,
    UNIQUE(date, ticker)
);

-- 3. Row Level Security (RLS) --

ALTER TABLE portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget ENABLE ROW LEVEL SECURITY;
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;

-- Users can only see/edit their own data
CREATE POLICY "Users manage own portfolio" ON portfolio
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users manage own budget" ON budget
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users manage own goals" ON goals
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Global prediction tables: everyone can read, service role can write
ALTER TABLE gold_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE silver_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scanner_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_predictions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read gold_predictions" ON gold_predictions
    FOR SELECT USING (true);
CREATE POLICY "Anyone can read silver_predictions" ON silver_predictions
    FOR SELECT USING (true);
CREATE POLICY "Anyone can read scanner_predictions" ON scanner_predictions
    FOR SELECT USING (true);
CREATE POLICY "Anyone can read stock_predictions" ON stock_predictions
    FOR SELECT USING (true);

-- Service role (bot) bypasses RLS automatically, so no insert policy needed for anon

-- 4. Indexes --
CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio(user_id);
CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id);
CREATE INDEX IF NOT EXISTS idx_gold_pred_date ON gold_predictions(date);
CREATE INDEX IF NOT EXISTS idx_silver_pred_date ON silver_predictions(date);
CREATE INDEX IF NOT EXISTS idx_scanner_pred_date ON scanner_predictions(date);
CREATE INDEX IF NOT EXISTS idx_stock_pred_date ON stock_predictions(date);


-- =============================================================
-- 5. Portfolio History (daily snapshots for value-over-time charts)
-- =============================================================

CREATE TABLE IF NOT EXISTS portfolio_history (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    total_invested NUMERIC NOT NULL DEFAULT 0,
    total_current  NUMERIC NOT NULL DEFAULT 0,
    total_pnl      NUMERIC NOT NULL DEFAULT 0,
    total_pnl_pct  NUMERIC NOT NULL DEFAULT 0,
    holdings_count INT NOT NULL DEFAULT 0,
    nifty_close    NUMERIC,
    sensex_close   NUMERIC,
    snapshot_json  JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, date)
);

-- For local/guest mode (user_id NULL)
CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_history_guest
    ON portfolio_history(date) WHERE user_id IS NULL;

ALTER TABLE portfolio_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own portfolio_history" ON portfolio_history
    FOR ALL USING (auth.uid() = user_id OR user_id IS NULL)
    WITH CHECK (auth.uid() = user_id OR user_id IS NULL);

CREATE INDEX IF NOT EXISTS idx_portfolio_history_user_date
    ON portfolio_history(user_id, date);


-- =============================================================
-- 6. Dividend Tracking
-- =============================================================

CREATE TABLE IF NOT EXISTS dividends (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    amount      NUMERIC NOT NULL DEFAULT 0,
    date        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE dividends ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own dividends" ON dividends
    FOR ALL USING (auth.uid() = user_id OR user_id IS NULL)
    WITH CHECK (auth.uid() = user_id OR user_id IS NULL);

CREATE INDEX IF NOT EXISTS idx_dividends_user ON dividends(user_id);


-- =============================================================
-- 7. Net Worth Tracking (F1)
-- =============================================================

CREATE TABLE IF NOT EXISTS net_worth (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    bank_balance    NUMERIC NOT NULL DEFAULT 0,
    fd_amount       NUMERIC NOT NULL DEFAULT 0,
    ppf_balance     NUMERIC NOT NULL DEFAULT 0,
    nps_balance     NUMERIC NOT NULL DEFAULT 0,
    epf_balance     NUMERIC NOT NULL DEFAULT 0,
    real_estate_value NUMERIC NOT NULL DEFAULT 0,
    gold_physical_value NUMERIC NOT NULL DEFAULT 0,
    other_assets    NUMERIC NOT NULL DEFAULT 0,
    home_loan       NUMERIC NOT NULL DEFAULT 0,
    car_loan        NUMERIC NOT NULL DEFAULT 0,
    personal_loan   NUMERIC NOT NULL DEFAULT 0,
    credit_card_debt NUMERIC NOT NULL DEFAULT 0,
    other_liabilities NUMERIC NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE net_worth ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own net_worth" ON net_worth
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- =============================================================
-- 8. Family Account Management
-- =============================================================

CREATE TABLE IF NOT EXISTS family_members (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    profile_type TEXT NOT NULL DEFAULT 'member',  -- spouse, child, parent, sibling, other
    created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE family_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own family_members" ON family_members
    FOR ALL USING (auth.uid() = owner_id)
    WITH CHECK (auth.uid() = owner_id);

CREATE INDEX IF NOT EXISTS idx_family_members_owner ON family_members(owner_id);

-- Family member portfolios (mirrors portfolio table structure)
CREATE TABLE IF NOT EXISTS family_portfolio (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id   BIGINT NOT NULL REFERENCES family_members(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    ticker      TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT 'stock',
    investment_mode TEXT NOT NULL DEFAULT 'lumpsum',
    buy_price   NUMERIC NOT NULL DEFAULT 0,
    quantity    NUMERIC NOT NULL DEFAULT 0,
    buy_date    TEXT NOT NULL DEFAULT '',
    sip_monthly NUMERIC NOT NULL DEFAULT 0,
    sip_date    INT NOT NULL DEFAULT 0,
    amfi_code   TEXT NOT NULL DEFAULT '',
    transactions JSONB NOT NULL DEFAULT '[]',
    sip_pause_periods JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE family_portfolio ENABLE ROW LEVEL SECURITY;
-- Access via family_members ownership chain
CREATE POLICY "Users manage own family_portfolio" ON family_portfolio
    FOR ALL USING (
        member_id IN (SELECT id FROM family_members WHERE owner_id = auth.uid())
    )
    WITH CHECK (
        member_id IN (SELECT id FROM family_members WHERE owner_id = auth.uid())
    );

CREATE INDEX IF NOT EXISTS idx_family_portfolio_member ON family_portfolio(member_id);


-- =============================================================
-- 9. Target Allocation (for rebalancing engine)
-- =============================================================

CREATE TABLE IF NOT EXISTS target_allocation (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    asset_class TEXT NOT NULL,
    target_pct  NUMERIC NOT NULL DEFAULT 0,
    tolerance_pct NUMERIC NOT NULL DEFAULT 5.0,
    label       TEXT NOT NULL DEFAULT '',
    UNIQUE(user_id, asset_class)
);

ALTER TABLE target_allocation ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own target_allocation" ON target_allocation
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- =============================================================
-- 10. Retirement Instruments (extends fixed_instruments)
-- =============================================================

CREATE TABLE IF NOT EXISTS fixed_instruments (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT '',           -- EPF, PPF, NPS, SSY, SCSS, FD, RD
    current_balance NUMERIC NOT NULL DEFAULT 0,
    monthly_contribution NUMERIC NOT NULL DEFAULT 0,
    employer_contribution NUMERIC NOT NULL DEFAULT 0,
    interest_rate NUMERIC NOT NULL DEFAULT 0,
    start_date  TEXT NOT NULL DEFAULT '',
    maturity_date TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE fixed_instruments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own fixed_instruments" ON fixed_instruments
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_fixed_instruments_user ON fixed_instruments(user_id);


-- =============================================================
-- 8. Tax Planning (F6)
-- =============================================================

CREATE TABLE IF NOT EXISTS tax_planning (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    gross_income    NUMERIC NOT NULL DEFAULT 0,
    hra_received    NUMERIC NOT NULL DEFAULT 0,
    rent_paid       NUMERIC NOT NULL DEFAULT 0,
    metro_city      BOOLEAN NOT NULL DEFAULT true,
    section_80c_elss NUMERIC NOT NULL DEFAULT 0,
    section_80c_ppf NUMERIC NOT NULL DEFAULT 0,
    section_80c_epf NUMERIC NOT NULL DEFAULT 0,
    section_80c_lic NUMERIC NOT NULL DEFAULT 0,
    section_80c_tuition NUMERIC NOT NULL DEFAULT 0,
    section_80c_nsc NUMERIC NOT NULL DEFAULT 0,
    section_80c_home_loan_principal NUMERIC NOT NULL DEFAULT 0,
    section_80d_self NUMERIC NOT NULL DEFAULT 0,
    section_80d_parents NUMERIC NOT NULL DEFAULT 0,
    section_80ccd_nps NUMERIC NOT NULL DEFAULT 0,
    home_loan_interest NUMERIC NOT NULL DEFAULT 0,
    other_deductions NUMERIC NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE tax_planning ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own tax_planning" ON tax_planning
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- =============================================================
-- 9. Fixed Income Instruments — NPS/PPF/FD Tracker (F8)
-- =============================================================

CREATE TABLE IF NOT EXISTS fixed_instruments (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type            TEXT NOT NULL DEFAULT 'FD',
    name            TEXT NOT NULL DEFAULT '',
    current_value   NUMERIC NOT NULL DEFAULT 0,
    interest_rate   NUMERIC NOT NULL DEFAULT 0,
    start_date      TEXT NOT NULL DEFAULT '',
    maturity_date   TEXT NOT NULL DEFAULT '',
    monthly_contribution NUMERIC NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE fixed_instruments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own fixed_instruments" ON fixed_instruments
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_fixed_instruments_user ON fixed_instruments(user_id);
