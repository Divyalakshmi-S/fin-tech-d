-- =============================================================
-- Supabase Schema for fin-tech-d
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
--
-- Auth: handled by Streamlit (st.login), NOT Supabase Auth.
-- user_id = user's email address (TEXT).
-- App uses SUPABASE_SERVICE_KEY which bypasses RLS.
-- RLS is enabled to block direct anon/public access.
-- =============================================================

-- 1. User-specific tables --

CREATE TABLE IF NOT EXISTS portfolio (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS budget (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT NOT NULL UNIQUE,
    income      NUMERIC NOT NULL DEFAULT 0,
    expenses    NUMERIC NOT NULL DEFAULT 0,
    investments NUMERIC NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS goals (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    target      NUMERIC NOT NULL DEFAULT 0,
    years       NUMERIC NOT NULL DEFAULT 5,
    expected_return NUMERIC NOT NULL DEFAULT 12,
    monthly_sip NUMERIC NOT NULL DEFAULT 0,
    created_date TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- 2. Global tables (shared, written by bot) --

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

CREATE TABLE IF NOT EXISTS portfolio_history (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_history_guest
    ON portfolio_history(date) WHERE user_id IS NULL;

CREATE TABLE IF NOT EXISTS dividends (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    amount      NUMERIC NOT NULL DEFAULT 0,
    date        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS net_worth (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         TEXT NOT NULL UNIQUE,
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

CREATE TABLE IF NOT EXISTS family_members (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    profile_type TEXT NOT NULL DEFAULT 'member',
    created_at  TIMESTAMPTZ DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS target_allocation (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    target_pct  NUMERIC NOT NULL DEFAULT 0,
    tolerance_pct NUMERIC NOT NULL DEFAULT 5.0,
    label       TEXT NOT NULL DEFAULT '',
    UNIQUE(user_id, asset_class)
);

CREATE TABLE IF NOT EXISTS fixed_instruments (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT '',
    current_balance NUMERIC NOT NULL DEFAULT 0,
    monthly_contribution NUMERIC NOT NULL DEFAULT 0,
    employer_contribution NUMERIC NOT NULL DEFAULT 0,
    interest_rate NUMERIC NOT NULL DEFAULT 0,
    start_date  TEXT NOT NULL DEFAULT '',
    maturity_date TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tax_planning (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         TEXT NOT NULL UNIQUE,
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

-- 3. RLS — block direct anon access; app uses service key (bypasses RLS) --

ALTER TABLE portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget ENABLE ROW LEVEL SECURITY;
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dividends ENABLE ROW LEVEL SECURITY;
ALTER TABLE net_worth ENABLE ROW LEVEL SECURITY;
ALTER TABLE family_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE family_portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE target_allocation ENABLE ROW LEVEL SECURITY;
ALTER TABLE fixed_instruments ENABLE ROW LEVEL SECURITY;
ALTER TABLE tax_planning ENABLE ROW LEVEL SECURITY;

-- Prediction tables: anyone can read
ALTER TABLE gold_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE silver_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scanner_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_predictions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read gold_predictions" ON gold_predictions FOR SELECT USING (true);
CREATE POLICY "Anyone can read silver_predictions" ON silver_predictions FOR SELECT USING (true);
CREATE POLICY "Anyone can read scanner_predictions" ON scanner_predictions FOR SELECT USING (true);
CREATE POLICY "Anyone can read stock_predictions" ON stock_predictions FOR SELECT USING (true);

-- 4. Indexes --

CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio(user_id);
CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id);
CREATE INDEX IF NOT EXISTS idx_gold_pred_date ON gold_predictions(date);
CREATE INDEX IF NOT EXISTS idx_silver_pred_date ON silver_predictions(date);
CREATE INDEX IF NOT EXISTS idx_scanner_pred_date ON scanner_predictions(date);
CREATE INDEX IF NOT EXISTS idx_stock_pred_date ON stock_predictions(date);
CREATE INDEX IF NOT EXISTS idx_portfolio_history_user_date ON portfolio_history(user_id, date);
CREATE INDEX IF NOT EXISTS idx_dividends_user ON dividends(user_id);
CREATE INDEX IF NOT EXISTS idx_family_members_owner ON family_members(owner_id);
CREATE INDEX IF NOT EXISTS idx_family_portfolio_member ON family_portfolio(member_id);
CREATE INDEX IF NOT EXISTS idx_fixed_instruments_user ON fixed_instruments(user_id);
