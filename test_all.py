"""Quick smoke-test for all major features."""

import json
from analysis import (
    load_portfolio_extended,
    analyze_portfolio,
    analyze_gold_trend,
    get_silver_price,
    analyze_silver_trend,
    fetch_news,
    scan_top_movers,
    scan_oversold_opportunities,
    fetch_mf_nav_batch,
    compute_diversification,
    metal_price_inr,
    is_market_open_today,
    predict_gold_buy,
    predict_stock_buy,
    calculate_portfolio_pnl,
)
from bot import get_stock_data, get_nifty_change, get_gold_price, generate_message

print("=" * 60)
print("FINANCE BOT — FULL SMOKE TEST")
print("=" * 60)

# 1. Market data
print("\n1. Market data...")
nifty = get_stock_data()
change = get_nifty_change()
print(f"   Nifty 50: {nifty} ({change:+.2f}%)" if change else f"   Nifty 50: {nifty}")

# 2. Gold
print("\n2. Gold price...")
gold = get_gold_price()
if gold:
    print(
        f"   OK: ₹{gold['per_gram']:,.2f}/g ({gold['change_pct']:+.2f}%)"
        if gold.get("change_pct")
        else f"   OK: ₹{gold['per_gram']:,.2f}/g"
    )
else:
    print("   SKIP: Could not fetch gold price")

# 3. Silver
print("\n3. Silver price...")
silver = get_silver_price()
if silver:
    print(
        f"   OK: ₹{silver['per_gram']:,.2f}/g ({silver['change_pct']:+.2f}%)"
        if silver.get("change_pct")
        else f"   OK: ₹{silver['per_gram']:,.2f}/g"
    )
else:
    print("   SKIP: Could not fetch silver price")

# 4. Portfolio
print("\n4. Portfolio...")
portfolio = load_portfolio_extended()
print(f"   Loaded {len(portfolio)} holdings")

# 5. Portfolio analysis
print("\n5. Portfolio analysis...")
results = analyze_portfolio(portfolio)
for r in results:
    a = r["analysis"]
    name = r["holding"]["name"]
    if a:
        print(
            f"   {name}: ₹{a['price']:,.2f} ({a['daily_change_pct']:+.2f}%), RSI={a['rsi']:.0f}"
            if a.get("rsi")
            else f"   {name}: ₹{a['price']:,.2f}"
        )
    else:
        print(f"   {name}: no data")

# 6. P&L
print("\n6. P&L...")
pnl = calculate_portfolio_pnl(portfolio, results)
print(f"   Invested: ₹{pnl['total_invested']:,.0f}")
print(f"   Current:  ₹{pnl['total_current']:,.0f}")
print(f"   P&L:      ₹{pnl['total_pnl']:,.0f} ({pnl['total_pnl_pct']:+.2f}%)")

# 7. Diversification
print("\n7. Diversification...")
div = compute_diversification(portfolio, results)
if div:
    print(f"   Score: {div['score']}/100, HHI: {div['hhi']}")
else:
    print("   SKIP: no diversification data")

# 8. Gold prediction
print("\n8. Gold prediction...")
gold_pred = predict_gold_buy(use_news=False)
if gold_pred:
    print(f"   OK: {gold_pred['signal']} ({gold_pred['confidence']}% confidence)")
else:
    print("   SKIP: Could not predict gold")

# 9. Stock prediction
print("\n9. Stock prediction...")
test_ticker = "TATAMOTORS.NS"
pred = predict_stock_buy(test_ticker, "Tata Motors", use_news=False)
if pred:
    print(
        f"   OK: {pred['name']} -> {pred['signal']} ({pred['confidence']}% confidence)"
    )
    sl = pred.get("stop_loss")
    if sl and isinstance(sl, dict):
        print(
            f"   OK: Risk={pred['risk_level']}, ATR%={pred['atr_pct']:.2f}%, Stop-loss=Rs {sl['stop_loss']:,.2f}"
        )
    elif sl is not None:
        print(
            f"   OK: Risk={pred['risk_level']}, ATR%={pred['atr_pct']:.2f}%, Stop-loss=Rs {sl:,.2f}"
        )
    else:
        print(
            f"   OK: Risk={pred['risk_level']}, ATR%={pred['atr_pct']:.2f}%, Stop-loss=N/A"
        )
else:
    print("   SKIP: Could not predict stock")

# 10. Top movers
print("\n10. Top movers...")
try:
    gainers, losers = scan_top_movers(top_n=3)
    for g in gainers[:2]:
        print(f"   🚀 {g['name']}: {g['change_pct']:+.2f}%")
    for l in losers[:2]:
        print(f"   📉 {l['name']}: {l['change_pct']:+.2f}%")
except Exception as e:
    print(f"   SKIP: {e}")

# 11. Buy opportunities
print("\n11. Oversold opportunities...")
try:
    opps = scan_oversold_opportunities()
    for o in opps[:3]:
        print(f"   {o['name']}: ₹{o['price']:,.0f} — {o['buy_verdict']}")
except Exception as e:
    print(f"   SKIP: {e}")

# 12. News
print("\n12. News...")
try:
    news = fetch_news(max_items=3)
    for item in news:
        print(f"   [{item['sentiment']}] {item['title'][:70]}")
except Exception as e:
    print(f"   SKIP: {e}")

# 13. Message generation
print("\n13. Full message generation...")
msg = generate_message()
print(f"   OK: {len(msg)} chars, {msg.count(chr(10))+1} lines")

# 14. Market open check
print("\n14. Market open today...")
market = is_market_open_today()
print(f"   {'Open' if market else 'Closed' if market is False else 'Unknown'}")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)
