"""
Supabase database abstraction layer.

All data access goes through this module. If Supabase is not configured
(missing env vars), falls back to local JSON files — so the bot and local
dev still work without a DB.

Swap to any PostgreSQL host by changing SUPABASE_URL / SUPABASE_KEY.
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_supabase_client = None
_use_db = False


def _is_deployed():
    """Check if running in a deployed environment (Streamlit Cloud or GitHub Actions)."""
    # GitHub Actions bot
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    # Streamlit Cloud always mounts code at /mount/src/
    if os.path.exists("/mount/src"):
        return True
    return False


def _get_client():
    """Lazy-init Supabase client. Returns None if not configured."""
    global _supabase_client, _use_db
    if _supabase_client is not None:
        return _supabase_client

    # Local dev: always use JSON/CSV — skip DB entirely
    if not _is_deployed():
        logger.info("Local environment — using JSON/CSV (skipping DB)")
        _use_db = False
        return None

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")

    # Also check Streamlit secrets (for Streamlit Cloud)
    if not url or not key:
        try:
            import streamlit as st

            url = url or st.secrets.get("supabase", {}).get("SUPABASE_URL", "")
            key = key or st.secrets.get("supabase", {}).get("SUPABASE_KEY", "")
        except Exception:
            pass

    if not url or not key:
        logger.info("Supabase not configured — using JSON fallback")
        _use_db = False
        return None

    try:
        from supabase import create_client

        _supabase_client = create_client(url, key)
        _use_db = True
        logger.info("Supabase client initialized — url=%s", url[:40])
        return _supabase_client
    except Exception:
        logger.exception("Failed to create Supabase client")
        _use_db = False
        return None


_db_available_cache = None  # None = not checked, True/False = result


def is_db_available():
    """Check if Supabase is configured and reachable."""
    global _db_available_cache
    if _db_available_cache is not None:
        return _db_available_cache

    client = _get_client()
    if client is None:
        logger.warning("DB connection check: no client configured")
        _db_available_cache = False
        return False
    # Verify actual connectivity (create_client succeeds even if network is down)
    try:
        client.table("portfolio").select("id").limit(1).execute()
        logger.info("DB connection check: OK")
        _db_available_cache = True
        return True
    except Exception as e:
        logger.error("DB connection check: FAILED — %s", e)
        _db_available_cache = False
        return False


def get_service_client():
    """Get a Supabase client using the service-role key (bypasses RLS).
    Used by the bot in GitHub Actions.
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# JSON fallback helpers (existing behaviour)
# ---------------------------------------------------------------------------


def _json_path(filename, user_id=None):
    base = os.path.join(os.path.dirname(__file__), "data")
    if user_id:
        base = os.path.join(base, str(user_id))
    return os.path.join(base, filename)


def _load_json(filename, default=None, user_id=None):
    path = _json_path(filename, user_id=user_id)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def _save_json(filename, data, user_id=None):
    path = _json_path(filename, user_id=user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Portfolio CRUD
# ---------------------------------------------------------------------------


def load_portfolio(user_id=None):
    """Load portfolio rows for a user. Returns list[dict]."""
    logger.debug("load_portfolio — user=%s", user_id or "guest")
    client = _get_client()
    if client and user_id:
        try:
            resp = (
                client.table("portfolio").select("*").eq("user_id", user_id).execute()
            )
            rows = resp.data or []
            # Convert DB rows to the same shape as JSON entries
            for r in rows:
                if isinstance(r.get("transactions"), str):
                    r["transactions"] = json.loads(r["transactions"])
                if isinstance(r.get("sip_pause_periods"), str):
                    r["sip_pause_periods"] = json.loads(r["sip_pause_periods"])
            logger.info("load_portfolio DB success — %d rows", len(rows))
            return rows
        except Exception:
            logger.exception("load_portfolio DB FAILED")
            raise
    return _load_json("portfolio.json", [], user_id=user_id)


def save_portfolio(rows, user_id=None):
    """Replace all portfolio rows for a user."""
    logger.info(
        "save_portfolio — user=%s, rows=%d",
        user_id or "guest",
        len(rows) if rows else 0,
    )
    client = _get_client()
    if client and user_id:
        try:
            # Delete existing rows for user, then insert new ones
            client.table("portfolio").delete().eq("user_id", user_id).execute()
            if rows:
                for r in rows:
                    r["user_id"] = user_id
                    # Ensure required fields have defaults
                    r.setdefault("transactions", [])
                    r.setdefault("sip_pause_periods", [])
                    r.setdefault("ticker", "")
                    r.setdefault("type", "stock")
                    r.setdefault("investment_mode", "lumpsum")
                    r.setdefault("buy_price", 0)
                    r.setdefault("quantity", 0)
                    r.setdefault("buy_date", "")
                    r.setdefault("sip_monthly", 0)
                    r.setdefault("sip_date", 0)
                    r.setdefault("amfi_code", "")
                    # Ensure JSONB fields are dicts/lists, not strings
                    if isinstance(r["transactions"], str):
                        r["transactions"] = json.loads(r["transactions"])
                    if isinstance(r["sip_pause_periods"], str):
                        r["sip_pause_periods"] = json.loads(r["sip_pause_periods"])
                    # Remove fields not in DB schema
                    r.pop("id", None)
                    r.pop("created_at", None)
                client.table("portfolio").insert(rows).execute()
            logger.info("save_portfolio DB success — %d rows", len(rows) if rows else 0)
            return
        except Exception:
            logger.exception("save_portfolio DB FAILED")
            raise
    _save_json("portfolio.json", rows, user_id=user_id)


# ---------------------------------------------------------------------------
# Budget CRUD
# ---------------------------------------------------------------------------


def load_budget(user_id=None):
    """Load budget for a user. Returns dict."""
    default = {
        "income": 0,
        "expenses": 0,
        "investments": 0,
        "expense_categories": {},
        "budget_items": [],
    }
    client = _get_client()
    if client and user_id:
        try:
            resp = (
                client.table("budget")
                .select(
                    "income, expenses, investments, expense_categories, budget_items"
                )
                .eq("user_id", user_id)
                .execute()
            )
            if resp.data:
                row = resp.data[0]
                row.setdefault("expense_categories", {})
                row.setdefault("budget_items", [])
                logger.info("load_budget DB success")
                return row
            logger.info("load_budget DB success — no data yet")
            return default
        except Exception:
            logger.exception("load_budget DB FAILED")
            raise
    return _load_json("budget.json", default, user_id=user_id)


def save_budget(data, user_id=None):
    """Upsert budget for a user."""
    logger.info("save_budget — user=%s", user_id or "guest")
    client = _get_client()
    if client and user_id:
        try:
            row = {
                "user_id": user_id,
                "income": data.get("income", 0),
                "expenses": data.get("expenses", 0),
                "investments": data.get("investments", 0),
                "expense_categories": data.get("expense_categories", {}),
                "budget_items": data.get("budget_items", []),
                "updated_at": datetime.utcnow().isoformat(),
            }
            client.table("budget").upsert(row, on_conflict="user_id").execute()
            logger.info("save_budget DB success")
            return
        except Exception:
            logger.exception("save_budget DB FAILED")
            raise
    _save_json("budget.json", data, user_id=user_id)


# ---------------------------------------------------------------------------
# Goals CRUD
# ---------------------------------------------------------------------------


def load_goals(user_id=None):
    """Load goals for a user. Returns list[dict]."""
    client = _get_client()
    if client and user_id:
        try:
            resp = client.table("goals").select("*").eq("user_id", user_id).execute()
            logger.info("load_goals DB success — %d goals", len(resp.data or []))
            return resp.data or []
        except Exception:
            logger.exception("load_goals DB FAILED")
            raise
    return _load_json("goals.json", [], user_id=user_id)


def save_goal(goal, user_id=None):
    """Insert a single goal. Returns the new goal ID."""
    logger.info(
        "save_goal called — user=%s, name=%s", user_id or "guest", goal.get("name")
    )
    client = _get_client()
    if client and user_id:
        row = {
            "user_id": user_id,
            "name": goal["name"],
            "target": goal["target"],
            "years": goal["years"],
            "expected_return": goal["expected_return"],
            "monthly_sip": goal["monthly_sip"],
            "created_date": goal.get(
                "created_date", datetime.now().strftime("%Y-%m-%d")
            ),
        }
        try:
            resp = client.table("goals").insert(row).execute()
            logger.info(
                "save_goal DB success — id=%s", resp.data[0]["id"] if resp.data else "?"
            )
            return resp.data[0]["id"] if resp.data else 0
        except Exception:
            logger.exception("save_goal DB FAILED")
            raise
    # JSON fallback
    logger.info("Goal saving to JSON fallback (no DB or no user_id)")
    goals = _load_json("goals.json", [], user_id=user_id)
    goal["id"] = max((g.get("id", 0) for g in goals), default=0) + 1
    if "created_date" not in goal:
        goal["created_date"] = datetime.now().strftime("%Y-%m-%d")
    goals.append(goal)
    _save_json("goals.json", goals, user_id=user_id)
    return goal["id"]


def delete_goal(goal_id, user_id=None):
    """Delete a goal by ID."""
    logger.info("delete_goal — id=%s, user=%s", goal_id, user_id or "guest")
    client = _get_client()
    if client and user_id:
        try:
            client.table("goals").delete().eq("id", goal_id).eq(
                "user_id", user_id
            ).execute()
            logger.info("delete_goal DB success — id=%s", goal_id)
            return
        except Exception:
            logger.exception("delete_goal DB FAILED — id=%s", goal_id)
            raise
    goals = _load_json("goals.json", [], user_id=user_id)
    goals = [g for g in goals if g.get("id") != goal_id]
    _save_json("goals.json", goals, user_id=user_id)


# ---------------------------------------------------------------------------
# Predictions (global — no user_id needed)
# ---------------------------------------------------------------------------


def load_predictions(table_name):
    """Load predictions from DB or JSON. table_name is one of:
    gold_predictions, silver_predictions, scanner_predictions,
    gold_buyday_predictions, gold_buyday_weights
    """
    # Tables without a 'date' column — skip ordering
    _no_date_tables = {"gold_buyday_weights"}

    client = _get_client()
    if client:
        try:
            query = client.table(table_name).select("*")
            if table_name not in _no_date_tables:
                query = query.order("date", desc=True)
            resp = query.execute()
            rows = resp.data or []
            for r in rows:
                if isinstance(r.get("factor_scores"), str):
                    r["factor_scores"] = json.loads(r["factor_scores"])
                if isinstance(r.get("buy_reasoning"), str):
                    r["buy_reasoning"] = json.loads(r["buy_reasoning"])
            logger.info(
                "load_predictions DB success — table=%s, rows=%d", table_name, len(rows)
            )
            return rows
        except Exception:
            logger.exception("load_predictions DB FAILED — table=%s", table_name)
            raise
    return _load_json(f"{table_name}.json", [])


def save_prediction(table_name, entry, unique_keys=None):
    """Upsert a prediction row. unique_keys controls dedup (e.g. ['date'] or ['date','ticker'])."""
    client = _get_client()
    if client:
        try:
            if unique_keys:
                conflict_cols = ",".join(unique_keys)
                client.table(table_name).upsert(
                    entry, on_conflict=conflict_cols
                ).execute()
            else:
                client.table(table_name).insert(entry).execute()
            logger.info("save_prediction DB success — table=%s", table_name)
            return entry
        except Exception:
            logger.exception("save_prediction DB FAILED — table=%s", table_name)
            raise

    # JSON fallback: same dedup logic as before
    filename = f"{table_name}.json"
    predictions = _load_json(filename, [])
    if unique_keys:
        predictions = [
            p
            for p in predictions
            if not all(p.get(k) == entry.get(k) for k in unique_keys)
        ]
    predictions.append(entry)
    _save_json(filename, predictions)
    return entry


def update_predictions(table_name, predictions_list):
    """Bulk-update predictions (for verify functions). Writes entire list."""
    client = _get_client()
    if client:
        try:
            for p in predictions_list:
                pid = p.get("id")
                if pid:
                    update_data = {k: v for k, v in p.items() if k != "id"}
                    client.table(table_name).update(update_data).eq("id", pid).execute()
            logger.info(
                "update_predictions DB success — table=%s, count=%d",
                table_name,
                len(predictions_list),
            )
            return
        except Exception:
            logger.exception("update_predictions DB FAILED — table=%s", table_name)
            raise
    _save_json(f"{table_name}.json", predictions_list)


# ---------------------------------------------------------------------------
# Portfolio History (daily snapshots)
# ---------------------------------------------------------------------------


def save_portfolio_snapshot(snapshot, user_id=None):
    """Upsert a daily portfolio snapshot."""
    client = _get_client()
    if client:
        try:
            row = {**snapshot}
            if user_id:
                row["user_id"] = user_id
            client.table("portfolio_history").upsert(
                row, on_conflict="user_id,date" if user_id else "date"
            ).execute()
            logger.debug("save_portfolio_snapshot DB success")
            return
        except Exception:
            logger.exception("save_portfolio_snapshot DB FAILED")
            raise
    # JSON fallback
    history = _load_json("portfolio_history.json", [], user_id=user_id)
    history = [h for h in history if h.get("date") != snapshot["date"]]
    history.append(snapshot)
    # Keep last 365 days
    history = sorted(history, key=lambda x: x["date"])[-365:]
    _save_json("portfolio_history.json", history, user_id=user_id)


def load_portfolio_history(user_id=None, limit=365):
    """Load portfolio history snapshots."""
    client = _get_client()
    if client:
        query = (
            client.table("portfolio_history")
            .select("*")
            .order("date", desc=False)
            .limit(limit)
        )
        if user_id:
            query = query.eq("user_id", user_id)
        resp = query.execute()
        return resp.data or []
    return _load_json("portfolio_history.json", [], user_id=user_id)[-limit:]


# ---------------------------------------------------------------------------
# Dividend Tracking
# ---------------------------------------------------------------------------


def load_dividends(user_id=None):
    """Load dividend records for a user."""
    client = _get_client()
    if client and user_id:
        resp = (
            client.table("dividends")
            .select("*")
            .eq("user_id", user_id)
            .order("date", desc=True)
            .execute()
        )
        return resp.data or []
    return _load_json("dividends.json", [], user_id=user_id)


def save_dividend(dividend, user_id=None):
    """Insert a dividend record."""
    client = _get_client()
    if client and user_id:
        try:
            row = {**dividend, "user_id": user_id}
            row.pop("id", None)
            client.table("dividends").insert(row).execute()
            logger.info("save_dividend DB success")
            return
        except Exception:
            logger.exception("save_dividend DB FAILED")
            raise
    divs = _load_json("dividends.json", [], user_id=user_id)
    dividend["id"] = max((d.get("id", 0) for d in divs), default=0) + 1
    divs.append(dividend)
    _save_json("dividends.json", divs, user_id=user_id)


def delete_dividend(div_id, user_id=None):
    """Delete a dividend record."""
    client = _get_client()
    if client and user_id:
        try:
            client.table("dividends").delete().eq("id", div_id).eq(
                "user_id", user_id
            ).execute()
            logger.info("delete_dividend DB success — id=%s", div_id)
            return
        except Exception:
            logger.exception("delete_dividend DB FAILED — id=%s", div_id)
            raise
    divs = _load_json("dividends.json", [], user_id=user_id)
    divs = [d for d in divs if d.get("id") != div_id]
    _save_json("dividends.json", divs, user_id=user_id)


# ---------------------------------------------------------------------------
# Net Worth Tracking (F1)
# ---------------------------------------------------------------------------


def load_net_worth(user_id=None):
    """Load net worth data for a user."""
    client = _get_client()
    if client and user_id:
        resp = client.table("net_worth").select("*").eq("user_id", user_id).execute()
        if resp.data:
            return resp.data[0]
        return None
    return _load_json("net_worth.json", None, user_id=user_id)


def save_net_worth(data, user_id=None):
    """Upsert net worth data for a user."""
    client = _get_client()
    if client and user_id:
        try:
            row = {
                **data,
                "user_id": user_id,
                "updated_at": datetime.utcnow().isoformat(),
            }
            client.table("net_worth").upsert(row, on_conflict="user_id").execute()
            logger.info("save_net_worth DB success")
            return
        except Exception:
            logger.exception("save_net_worth DB FAILED")
            raise
    _save_json("net_worth.json", data, user_id=user_id)


# ---------------------------------------------------------------------------
# Tax Planning (F6)
# ---------------------------------------------------------------------------


def load_tax_planning(user_id=None):
    """Load tax planning data for a user."""
    client = _get_client()
    if client and user_id:
        resp = client.table("tax_planning").select("*").eq("user_id", user_id).execute()
        if resp.data:
            return resp.data[0]
        return None
    return _load_json("tax_planning.json", None, user_id=user_id)


def save_tax_planning(data, user_id=None):
    """Upsert tax planning data."""
    client = _get_client()
    if client and user_id:
        try:
            row = {
                **data,
                "user_id": user_id,
                "updated_at": datetime.utcnow().isoformat(),
            }
            client.table("tax_planning").upsert(row, on_conflict="user_id").execute()
            logger.info("save_tax_planning DB success")
            return
        except Exception:
            logger.exception("save_tax_planning DB FAILED")
            raise
    _save_json("tax_planning.json", data, user_id=user_id)


# ---------------------------------------------------------------------------
# Fixed Income Instruments — NPS/PPF/FD Tracker (F8)
# ---------------------------------------------------------------------------


def load_fixed_instruments(user_id=None):
    """Load fixed-income instruments for a user."""
    client = _get_client()
    if client and user_id:
        resp = (
            client.table("fixed_instruments")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        return resp.data or []
    return _load_json("fixed_instruments.json", [], user_id=user_id)


def save_fixed_instruments(instruments, user_id=None):
    """Replace all fixed-income instruments for a user."""
    client = _get_client()
    if client and user_id:
        try:
            client.table("fixed_instruments").delete().eq("user_id", user_id).execute()
            if instruments:
                rows = [{**i, "user_id": user_id} for i in instruments]
                for r in rows:
                    r.pop("id", None)
                    r.pop("created_at", None)
                client.table("fixed_instruments").insert(rows).execute()
            logger.info(
                "save_fixed_instruments DB success — %d items",
                len(instruments) if instruments else 0,
            )
            return
        except Exception:
            logger.exception("save_fixed_instruments DB FAILED")
            raise
    _save_json("fixed_instruments.json", instruments, user_id=user_id)


# ---------------------------------------------------------------------------
# Family Profiles — multi-member portfolio management
# ---------------------------------------------------------------------------


def load_family_members(user_id=None):
    """Load family member profiles for a user. Returns list[dict]."""
    client = _get_client()
    if client and user_id:
        resp = (
            client.table("family_members")
            .select("*")
            .eq("owner_id", user_id)
            .order("created_at")
            .execute()
        )
        return resp.data or []
    return _load_json("family_members.json", [], user_id=user_id)


def save_family_member(member, user_id=None):
    """Insert a family member profile."""
    client = _get_client()
    if client and user_id:
        try:
            row = {**member, "owner_id": user_id}
            row.pop("id", None)
            row.pop("created_at", None)
            resp = client.table("family_members").insert(row).execute()
            logger.info(
                "save_family_member DB success — id=%s",
                resp.data[0]["id"] if resp.data else "?",
            )
            return resp.data[0]["id"] if resp.data else 0
        except Exception:
            logger.exception("save_family_member DB FAILED")
            raise
    # JSON fallback
    members = _load_json("family_members.json", [], user_id=user_id)
    member["id"] = max((m.get("id", 0) for m in members), default=0) + 1
    member["owner_id"] = user_id
    members.append(member)
    _save_json("family_members.json", members, user_id=user_id)
    return member["id"]


def delete_family_member(member_id, user_id=None):
    """Delete a family member profile."""
    client = _get_client()
    if client and user_id:
        try:
            client.table("family_members").delete().eq("id", member_id).eq(
                "owner_id", user_id
            ).execute()
            logger.info("delete_family_member DB success — id=%s", member_id)
            return
        except Exception:
            logger.exception("delete_family_member DB FAILED — id=%s", member_id)
            raise
    members = _load_json("family_members.json", [], user_id=user_id)
    members = [m for m in members if m.get("id") != member_id]
    _save_json("family_members.json", members, user_id=user_id)


def load_family_portfolio(member_id, user_id=None):
    """Load portfolio for a specific family member."""
    client = _get_client()
    if client and user_id:
        resp = (
            client.table("family_portfolio")
            .select("*")
            .eq("member_id", member_id)
            .execute()
        )
        rows = resp.data or []
        for r in rows:
            if isinstance(r.get("transactions"), str):
                r["transactions"] = json.loads(r["transactions"])
            if isinstance(r.get("sip_pause_periods"), str):
                r["sip_pause_periods"] = json.loads(r["sip_pause_periods"])
        return rows
    # JSON fallback: filter by member_id
    all_rows = _load_json("family_portfolio.json", [], user_id=user_id)
    return [r for r in all_rows if r.get("member_id") == member_id]


def save_family_portfolio(rows, member_id, user_id=None):
    """Replace all portfolio rows for a family member."""
    client = _get_client()
    if client and user_id:
        try:
            client.table("family_portfolio").delete().eq(
                "member_id", member_id
            ).execute()
            if rows:
                for r in rows:
                    r["member_id"] = member_id
                    # Ensure required fields have defaults
                    r.setdefault("transactions", [])
                    r.setdefault("sip_pause_periods", [])
                    r.setdefault("ticker", "")
                    r.setdefault("type", "stock")
                    r.setdefault("investment_mode", "lumpsum")
                    r.setdefault("buy_price", 0)
                    r.setdefault("quantity", 0)
                    r.setdefault("buy_date", "")
                    r.setdefault("sip_monthly", 0)
                    r.setdefault("sip_date", 0)
                    r.setdefault("amfi_code", "")
                    # Ensure JSONB fields are dicts/lists, not strings
                    if isinstance(r["transactions"], str):
                        r["transactions"] = json.loads(r["transactions"])
                    if isinstance(r["sip_pause_periods"], str):
                        r["sip_pause_periods"] = json.loads(r["sip_pause_periods"])
                    r.pop("id", None)
                    r.pop("created_at", None)
                client.table("family_portfolio").insert(rows).execute()
            logger.info(
                "save_family_portfolio DB success — member=%s, rows=%d",
                member_id,
                len(rows) if rows else 0,
            )
            return
        except Exception:
            logger.exception("save_family_portfolio DB FAILED — member=%s", member_id)
            raise
    # JSON fallback
    all_rows = _load_json("family_portfolio.json", [], user_id=user_id)
    all_rows = [r for r in all_rows if r.get("member_id") != member_id]
    for r in rows:
        r["member_id"] = member_id
    all_rows.extend(rows)
    _save_json("family_portfolio.json", all_rows, user_id=user_id)
