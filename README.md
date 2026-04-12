# 📊 Personal Finance Dashboard & Bot

Track your Indian stocks, gold, silver, and mutual funds — with a Streamlit dashboard, daily WhatsApp alerts, and weekly email recaps. **100% free tools.**

---

## What It Does

### Daily WhatsApp (via Twilio sandbox — free)

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
- **Holdings Analysis**: Per-stock RSI, MA chart, fundamentals, PE, news with impact analysis, buy/sell recommendation (8-factor engine)
- **Market Scanner**: Top movers, "What Should I Buy?" with clear verdicts, "Sell & Replace" tool (pick a stock to sell → see what to buy with that money), sector heatmap
- **News**: 4-category feed with sentiment
- **Budget**: Income/expense tracker

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
cp .env.example .env          # Fill in your Twilio/email credentials
nano data/portfolio.csv        # Add your holdings
```

### Run Locally

```bash
# Dashboard
streamlit run dashboard.py

# WhatsApp message (prints preview without Twilio credentials)
python bot.py

# Weekly email (saves HTML preview without email credentials)
python weekly_email.py
```

---

## Portfolio CSV Format

Edit `data/portfolio.csv`:

```csv
name,ticker,amount,type,sip_monthly,sip_date,amfi_code
Nippon Small Cap Fund,0P0001BAO8.BO,17999,mutual_fund,1000,5,118778
TCS,TCS.NS,10000,stock,0,0,
HDFC Bank,HDFCBANK.NS,6882,stock,0,0,
```

| Column        | Description                                                        |
| ------------- | ------------------------------------------------------------------ |
| `name`        | Display name                                                       |
| `ticker`      | Yahoo Finance ticker (`.NS` for NSE, `.BO` for BSE)                |
| `amount`      | Amount invested (₹)                                                |
| `type`        | `stock`, `mutual_fund`, or `debt`                                  |
| `sip_monthly` | Monthly SIP amount (₹), 0 if none                                  |
| `sip_date`    | Day of month for SIP reminder, 0 if none                           |
| `amfi_code`   | AMFI scheme code for MF NAV (from amfiindia.com), blank for stocks |

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
5. Add secrets in **Advanced settings**:
   ```toml
   # Not needed for dashboard — it reads portfolio.csv directly
   # But if you use .env variables:
   MONTHLY_INCOME = "109000"
   MONTHLY_EXPENSES = "47800"
   ```
6. Click **Deploy** — your dashboard is live with a public URL

### Setting Up Twilio (WhatsApp — free sandbox)

1. Create account at [twilio.com](https://www.twilio.com)
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. Send the join code from WhatsApp to the Twilio sandbox number
4. Copy **Account SID** and **Auth Token** from the console

> **Note:** Twilio sandbox expires after 72 hours of inactivity. Re-send the join code periodically.

### Setting Up Gmail (weekly email — free)

1. Enable **2-Step Verification** at [Google Account → Security](https://myaccount.google.com/security)
2. Go to **App Passwords** → Generate one for "Mail"
3. Use the 16-character app password (not your main password)

---

## Project Structure

```
├── analysis.py        # Core engine — all market analysis, predictions, scanners
├── dashboard.py       # Streamlit dashboard (7 pages)
├── bot.py             # Daily WhatsApp bot (concise alerts only)
├── weekly_email.py    # Weekly HTML email (key highlights only)
├── requirements.txt   # Python dependencies
├── .env.example       # Template for credentials
├── .github/workflows/
│   └── daily.yml      # GitHub Actions automation
└── data/
    ├── portfolio.csv            # Your holdings
    ├── gold_predictions.json    # Prediction history (auto-generated)
    └── silver_predictions.json  # Prediction history (auto-generated)
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
