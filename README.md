# 📊 Personal Finance Dashboard & Bot

Track your Indian stocks, gold, silver, and mutual funds — with a Streamlit dashboard, daily WhatsApp alerts, and weekly email recaps. **100% free tools.**

---

## What It Does

### Daily WhatsApp (via Twilio — free $15 credit)

A short morning message with only what matters:

- Nifty 50, gold, silver prices
- Alerts if your stocks are overbought/oversold or had a big move
- Top market gainer/loser
- Strong buy opportunities (if any)
- 2 news headlines
- SIP reminders on due dates

### Weekly Email (via Gmail SMTP — free)

A compact recap with:

- Market/gold/silver weekly change
- Alerts for your holdings (big moves, trend changes)
- Top movers and strong buy signals
- 3 news headlines

### Streamlit Dashboard (run locally or deploy free)

Full deep-dive analysis:

- **Overview**: Nifty, Sensex, gold/silver charts
- **Gold & Silver**: Price trends, buy predictions (7-factor engine), self-learning from past predictions
- **Portfolio**: All holdings with value, type breakdown, diversification score
- **Holdings Analysis**: Per-stock RSI, MA chart, fundamentals, PE, news with impact analysis, buy/sell recommendation (8-factor engine), portfolio rebalancing with drift detection
- **Market Scanner**: Top movers, "What Should I Buy?" with clear verdicts, "Sell & Replace" tool (pick a stock to sell → see what to buy with that money), sector heatmap
- **News**: 4-category feed with sentiment and actionable allocation-based advice
- **Goals**: Education planner, SIP calculator, goal tracking with portfolio alignment, asset allocation with no-fund-reuse
- **Budget**: Income/expense tracker
- **Family**: Family member profiles with combined portfolio view
- **Financial Health**: Health scoring + guided checkup wizard
- **Calculators**: Step-up SIP, Loan/EMI impact analysis
- **Tax Planning**: Old vs New regime comparison, LTCG/STCG breakdown

---

## Quick Start

```bash
# Clone and set up
git clone https://github.com/YOUR_USERNAME/finance-bot.git
cd finance-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env          # Fill in your Supabase, Telegram, and email credentials
```

Your portfolio is managed through the dashboard UI — go to **⚙️ Manage Portfolio** to add your stocks and mutual funds.

### Run Locally

```bash
# Dashboard
streamlit run dashboard.py

# Telegram message (prints preview without Telegram credentials)
python bot.py

# Weekly email (saves HTML preview without email credentials)
python weekly_email.py
```

---

## Portfolio Management

Your portfolio is managed entirely through the dashboard UI:

1. Run `streamlit run dashboard.py`
2. Go to **⚙️ Manage Portfolio** in the sidebar
3. Add stocks/mutual funds with:
   - **Name** — auto-resolves ticker (NSE/BSE) or AMFI code
   - **Buy Price** — price you paid per unit
   - **Quantity** — number of shares/units
   - **Buy Date** — when you bought
   - **SIP** (optional) — monthly SIP amount and date

The app automatically calculates:

- **Holding period** — days/years held
- **P&L** — profit/loss vs current market price
- **Tax status** — LTCG (>1 year, 10%) vs STCG (≤1 year, 15%)
- **Days to LTCG** — countdown to long-term tax benefit
- **XIRR** — annualized returns using actual buy dates

Data is stored in `data/portfolio.json` (auto-created).

---

## Database Setup (Supabase — free tier)

The app uses **Supabase** for multi-user auth and cloud data storage. Without it, data is stored locally in JSON files (single-user mode).

1. Create a project at [supabase.com](https://supabase.com) (free tier)
2. Go to **SQL Editor** → paste and run the contents of `supabase_schema.sql`
3. Go to **Settings → API** → copy your **Project URL** and **anon (public) key**
4. For the bot (GitHub Actions), also copy the **service_role key** from the same page
5. Add to your `.env`:
   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your_anon_key
   SUPABASE_SERVICE_KEY=your_service_role_key
   ```
6. For Streamlit Cloud, add these to `.streamlit/secrets.toml`:
   ```toml
   [supabase]
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_KEY = "your_anon_key"
   ```

> **Without Supabase**: The app still works in single-user mode using local JSON files in `data/`. Auth is skipped, and you get full functionality as a personal tool.

---

## Deployment (Free)

### Option 1: GitHub Actions (recommended — runs automatically)

1. Push your code to GitHub
2. Add secrets: **Settings → Secrets → Actions**

   | Secret           | Value                         |
   | ---------------- | ----------------------------- |
   | `TWILIO_SID`     | Twilio Account SID            |
   | `TWILIO_AUTH`    | Twilio Auth Token             |
   | `TO_NUMBER`      | `whatsapp:+91XXXXXXXXXX`      |
   | `EMAIL_FROM`     | Gmail address                 |
   | `EMAIL_PASSWORD` | Gmail App Password (16 chars) |
   | `EMAIL_TO`       | Recipient email               |

3. Go to **Actions** tab → Enable workflows
4. Schedule: Daily bot at 7:00 AM IST, weekly email on Sundays 9:30 AM IST

### Option 2: Streamlit Community Cloud (free dashboard hosting)

1. Push to GitHub (public or private repo)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Sign in with GitHub → **New app**
4. Select your repo, branch `main`, file `dashboard.py`
5. Click **Deploy** — your dashboard is live with a public URL

### Setting Up Twilio WhatsApp (free $15 credit — lasts ~8 years)

1. Create account at [twilio.com](https://www.twilio.com) — get **$15 free credit** (no card needed)
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. Send the join code from your WhatsApp to the Twilio sandbox number
4. Copy **Account SID** and **Auth Token** from the Twilio console
5. Add `TWILIO_SID`, `TWILIO_AUTH`, `TO_NUMBER` to `.env` or GitHub Secrets

> **Cost**: ~$0.005/msg → $15 credit = ~3,000 messages = **~8 years** of daily alerts.
> **Sandbox note**: If you don't send for 72h, re-send the join code. With daily GitHub Actions, this won't happen.

### Setting Up Gmail (weekly email — free)

1. Enable **2-Step Verification** at [Google Account → Security](https://myaccount.google.com/security)
2. Go to **App Passwords** → Generate one for "Mail"
3. Use the 16-character app password (not your main password)

---

## Project Structure

```
├── analysis/
│   ├── __init__.py            # Public API re-exports
│   ├── _core.py               # Core engine — analysis, predictions, scanners (6600+ lines)
│   ├── _technicals.py         # Technical indicators (RSI, MACD, Bollinger, ATR, etc.)
│   └── _data_sources.py       # Multi-source price fetcher (yfinance → NSE → BSE → cache)
├── views/
│   ├── overview.py            # Market overview (Nifty, Sensex, gold, silver)
│   ├── gold_silver.py         # Gold/Silver trends, 7-factor predictions
│   ├── portfolio.py           # Portfolio tracker with P&L, tax status, history
│   ├── holdings.py            # Per-stock deep analysis, 8-factor signals, rebalancing
│   ├── scanner.py             # Market scanner, "What to Buy", "Sell & Replace"
│   ├── news.py                # 4-category news with sentiment
│   ├── goals.py               # Financial goals, education planner, goal tracking & allocation
│   ├── budget.py              # Income/expense tracker
│   ├── tax_planning.py        # Old vs New regime comparison, LTCG/STCG
│   ├── calculators.py         # Step-up SIP, Loan/EMI impact calculators
│   ├── family.py              # Family member profiles + combined portfolio
│   ├── financial_health.py    # Financial health scoring
│   ├── checkup.py             # Health checkup wizard
│   ├── predictions.py         # Prediction accuracy scorecard
│   ├── learn.py               # Educational content & glossary
│   └── manage.py              # Add/edit/delete portfolio holdings
├── dashboard.py               # Streamlit dashboard (16 pages)
├── bot.py                     # Daily Telegram bot (market alerts)
├── weekly_email.py            # Weekly HTML email recap
├── auth.py                    # Supabase auth with guest fallback
├── db.py                      # Database layer (Supabase + per-user JSON fallback)
├── ui_helpers.py              # UI components, PDF export, disclaimers
├── supabase_schema.sql        # Full database schema with RLS policies
├── requirements.txt           # Python dependencies
├── .env.example               # Template for all credentials
└── data/                      # Local data (gitignored, per-user isolation)
    ├── portfolio.json
    ├── gold_predictions.json
    └── silver_predictions.json
```

---

## Data Sources (all free)

| Data                  | Source                           |
| --------------------- | -------------------------------- |
| Stock prices, indices | Yahoo Finance (yfinance)         |
| Gold & Silver         | Yahoo Finance (GC=F, SI=F)       |
| USD/INR exchange      | Yahoo Finance (USDINR=X)         |
| Mutual Fund NAVs      | AMFI India API                   |
| News headlines        | Google News RSS                  |
| WhatsApp delivery     | Twilio (free sandbox)            |
| Email delivery        | Gmail SMTP (free)                |
| Automation            | GitHub Actions (free tier)       |
| Dashboard hosting     | Streamlit Community Cloud (free) |

---

## Schedule

| Job            | Cron (UTC)   | IST Time | Frequency    |
| -------------- | ------------ | -------- | ------------ |
| Daily WhatsApp | `30 1 * * *` | 7:00 AM  | Every day    |
| Weekly Email   | `0 4 * * 0`  | 9:30 AM  | Every Sunday |
