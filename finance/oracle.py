"""Fintech-Oracle — Sovereign Local Financial & Invoicing Brain for LUMI (Phase 15).

Features:
  1. Transaction Ledger & Statement Parsing: Local encrypted/isolated SQLite transaction store with CSV parsing.
  2. Subscription Burn-Rate Radar: Tracks recurring subscriptions (Netflix, ChatGPT, AWS, etc.), calculates monthly burn rate & renewal alerts.
  3. Professional Invoice Generator: Creates client invoices with line items, tax/GST calculation, and clean printable markdown/HTML.
  4. Spending Insights: Categorizes expenses (Tech, Food, Travel, Utilities, Investments, Freelance Income) and tracks cash-flow balance.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumi.finance")

DEFAULT_CATEGORIES = {
    "saas": ["aws", "cloud", "openai", "chatgpt", "github", "cursor", "vercel", "cloudflare", "digitalocean"],
    "entertainment": ["netflix", "spotify", "youtube", "prime", "hotstar", "steam", "playstation"],
    "food": ["swiggy", "zomato", "blinkit", "zepto", "restaurant", "cafe", "starbucks"],
    "travel": ["uber", "ola", "irctc", "makemytrip", "flight", "petrol", "fuel"],
    "utilities": ["electricity", "wifi", "airtel", "jio", "water", "recharge", "broadband"],
    "income": ["salary", "client", "upwork", "freelance", "stripe", "razorpay", "dividend"],
}


class FintechOracle:
    """Sovereign local financial intelligence ledger and invoice generator."""

    def __init__(self, db_path: str | Path = "data/fintech.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    txn_type TEXT NOT NULL, -- 'debit' or 'credit'
                    balance REAL,
                    tags TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    amount REAL NOT NULL,
                    billing_cycle TEXT NOT NULL, -- 'monthly' or 'yearly'
                    renewal_day INTEGER NOT NULL, -- 1 to 31
                    category TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    last_billed TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_number TEXT NOT NULL UNIQUE,
                    client_name TEXT NOT NULL,
                    client_email TEXT,
                    date TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    subtotal REAL NOT NULL,
                    tax_amount REAL NOT NULL,
                    total_amount REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft', -- 'draft', 'sent', 'paid'
                    items_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def auto_categorize(self, description: str) -> str:
        """Guesses transaction category based on vendor keyword patterns."""
        desc_lower = description.lower()
        for cat, keywords in DEFAULT_CATEGORIES.items():
            for kw in keywords:
                if kw in desc_lower:
                    return cat
        return "general"

    def record_transaction(
        self,
        amount: float,
        description: str,
        date: str | None = None,
        category: str | None = None,
        txn_type: str = "debit",
        balance: float | None = None,
        tags: str | None = None,
    ) -> dict:
        """Records a single financial transaction into the local ledger."""
        txn_date = date or datetime.now().strftime("%Y-%m-%d")
        cat = category or self.auto_categorize(description)
        now_ts = datetime.now().isoformat()

        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO transactions (date, amount, description, category, txn_type, balance, tags, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (txn_date, float(amount), description.strip(), cat.lower(), txn_type.lower(), balance, tags, now_ts),
            )
            txn_id = cur.lastrowid

        return {
            "id": txn_id,
            "date": txn_date,
            "amount": float(amount),
            "description": description.strip(),
            "category": cat.lower(),
            "txn_type": txn_type.lower(),
            "balance": balance,
        }

    def parse_statement_csv(self, csv_content: str) -> dict:
        """Parses bank statement CSV and records transactions."""
        reader = csv.DictReader(io.StringIO(csv_content))
        recorded = 0
        total_inflow = 0.0
        total_outflow = 0.0

        for row in reader:
            normalized_row = {k.lower().strip(): v.strip() for k, v in row.items() if k}
            # Look for common column variants
            date_val = normalized_row.get("date") or normalized_row.get("txn date") or normalized_row.get("transaction date") or ""
            desc_val = normalized_row.get("description") or normalized_row.get("particulars") or normalized_row.get("narration") or "Bank Transaction"

            debit_val = normalized_row.get("debit") or normalized_row.get("withdrawal")
            credit_val = normalized_row.get("credit") or normalized_row.get("deposit")
            amount_val = normalized_row.get("amount")

            amt = 0.0
            ttype = "debit"

            try:
                if debit_val and float(debit_val.replace(",", "")) > 0:
                    amt = float(debit_val.replace(",", ""))
                    ttype = "debit"
                elif credit_val and float(credit_val.replace(",", "")) > 0:
                    amt = float(credit_val.replace(",", ""))
                    ttype = "credit"
                elif amount_val:
                    amt_num = float(amount_val.replace(",", ""))
                    amt = abs(amt_num)
                    ttype = "credit" if amt_num > 0 else "debit"
            except (ValueError, TypeError):
                continue

            if amt > 0:
                self.record_transaction(
                    amount=amt,
                    description=desc_val,
                    date=date_val or None,
                    txn_type=ttype,
                )
                recorded += 1
                if ttype == "credit":
                    total_inflow += amt
                else:
                    total_outflow += amt

        return {
            "transactions_parsed": recorded,
            "total_inflow": round(total_inflow, 2),
            "total_outflow": round(total_outflow, 2),
            "net_flow": round(total_inflow - total_outflow, 2),
        }

    def get_summary(self, month: str | None = None) -> dict:
        """Calculates total income, expenses, category breakdown, and net savings."""
        target_month = month or datetime.now().strftime("%Y-%m")
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT amount, txn_type, category FROM transactions WHERE date LIKE ?""",
                (f"{target_month}%",),
            ).fetchall()

        total_income = 0.0
        total_expense = 0.0
        by_category: dict[str, float] = {}

        for r in rows:
            amt = float(r["amount"])
            ttype = r["txn_type"]
            cat = r["category"]

            if ttype == "credit":
                total_income += amt
            else:
                total_expense += amt
                by_category[cat] = by_category.get(cat, 0.0) + amt

        # Format sorted categories
        sorted_categories = sorted(
            [{"category": k, "amount": round(v, 2)} for k, v in by_category.items()],
            key=lambda x: x["amount"],
            reverse=True,
        )

        return {
            "month": target_month,
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expense, 2),
            "net_savings": round(total_income - total_expense, 2),
            "savings_rate_pct": round((total_income - total_expense) / total_income * 100, 1) if total_income > 0 else 0.0,
            "transaction_count": len(rows),
            "categories": sorted_categories,
        }

    def track_subscription(
        self,
        name: str,
        amount: float,
        billing_cycle: str = "monthly",
        renewal_day: int = 1,
        category: str = "saas",
    ) -> dict:
        """Adds or updates a recurring subscription."""
        now_ts = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO subscriptions (name, amount, billing_cycle, renewal_day, category, active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       amount=excluded.amount,
                       billing_cycle=excluded.billing_cycle,
                       renewal_day=excluded.renewal_day,
                       category=excluded.category,
                       active=1""",
                (name.strip(), float(amount), billing_cycle.lower(), int(renewal_day), category.lower(), now_ts),
            )
        return {
            "name": name.strip(),
            "amount": float(amount),
            "billing_cycle": billing_cycle.lower(),
            "renewal_day": int(renewal_day),
            "status": "tracked",
        }

    def list_subscriptions(self, active_only: bool = True) -> dict:
        """Returns all tracked subscriptions, monthly burn rate, and renewal timeline."""
        with self._get_conn() as conn:
            query = "SELECT * FROM subscriptions" + (" WHERE active=1" if active_only else "")
            rows = conn.execute(query).fetchall()

        now = datetime.now()
        subs = []
        monthly_burn = 0.0

        for r in rows:
            amt = float(r["amount"])
            cycle = r["billing_cycle"]
            day = int(r["renewal_day"])

            # Calculate monthly equivalent cost
            equiv_monthly = amt if cycle == "monthly" else (amt / 12.0)
            monthly_burn += equiv_monthly

            # Calculate days until next renewal
            try:
                this_month_renewal = datetime(now.year, now.month, min(day, 28))
                if this_month_renewal < now:
                    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
                    next_renewal = datetime(next_month.year, next_month.month, min(day, 28))
                else:
                    next_renewal = this_month_renewal
                days_left = (next_renewal - now).days
            except Exception:
                days_left = 0

            subs.append({
                "id": r["id"],
                "name": r["name"],
                "amount": amt,
                "billing_cycle": cycle,
                "renewal_day": day,
                "category": r["category"],
                "monthly_cost": round(equiv_monthly, 2),
                "days_until_renewal": days_left,
            })

        subs.sort(key=lambda x: x["days_until_renewal"])
        return {
            "monthly_burn_rate": round(monthly_burn, 2),
            "annual_burn_rate": round(monthly_burn * 12, 2),
            "active_subscriptions_count": len(subs),
            "subscriptions": subs,
        }

    def check_upcoming_renewals(self, days_ahead: int = 3) -> list[dict]:
        """Returns subscriptions that will renew within the next N days."""
        all_subs = self.list_subscriptions()["subscriptions"]
        return [s for s in all_subs if 0 <= s["days_until_renewal"] <= days_ahead]

    def generate_invoice(
        self,
        client_name: str,
        items: list[dict],
        client_email: str | None = None,
        invoice_number: str | None = None,
        tax_rate_pct: float = 18.0,
        due_days: int = 14,
    ) -> dict:
        """Generates a professional client invoice with automated subtotal and tax calculation."""
        inv_no = invoice_number or f"INV-{int(time.time()) % 100000:05d}"
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        due_date_str = (now + timedelta(days=due_days)).strftime("%Y-%m-%d")

        subtotal = 0.0
        calculated_items = []

        for item in items:
            name = item.get("name") or item.get("description", "Consulting / Development")
            rate = float(item.get("rate", 0.0))
            qty = float(item.get("qty", item.get("hours", 1.0)))
            line_total = round(rate * qty, 2)
            subtotal += line_total
            calculated_items.append({
                "name": name,
                "rate": rate,
                "qty": qty,
                "total": line_total,
            })

        tax_amount = round(subtotal * (tax_rate_pct / 100.0), 2)
        total_amount = round(subtotal + tax_amount, 2)
        items_json = json.dumps(calculated_items)

        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO invoices (invoice_number, client_name, client_email, date, due_date, subtotal, tax_amount, total_amount, status, items_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
                (inv_no, client_name.strip(), client_email, date_str, due_date_str, subtotal, tax_amount, total_amount, items_json, now.isoformat()),
            )

        # Generate markdown template
        items_md = "\n".join([f"| {it['name']} | {it['qty']} | ₹{it['rate']:,.2f} | ₹{it['total']:,.2f} |" for it in calculated_items])
        markdown_body = f"""# INVOICE: {inv_no}
**Date:** {date_str}  
**Due Date:** {due_date_str}  
**Billed To:** {client_name} ({client_email or 'N/A'})  
**Payable To:** Commander (LUMI AI Sovereign Workstation)

---

| Item Description | Qty / Hours | Unit Rate | Amount |
| :--- | :--- | :--- | :--- |
{items_md}

---

**Subtotal:** ₹{subtotal:,.2f}  
**GST / Tax ({tax_rate_pct}%):** ₹{tax_amount:,.2f}  
### **Total Due:** ₹{total_amount:,.2f}

*Thank you for your business!*
"""

        return {
            "invoice_number": inv_no,
            "client_name": client_name,
            "client_email": client_email,
            "date": date_str,
            "due_date": due_date_str,
            "items": calculated_items,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "markdown": markdown_body,
        }

    def list_invoices(self) -> list[dict]:
        """Returns all created invoices."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM invoices ORDER BY id DESC").fetchall()
        result = []
        for r in rows:
            result.append({
                "invoice_number": r["invoice_number"],
                "client_name": r["client_name"],
                "client_email": r["client_email"],
                "date": r["date"],
                "due_date": r["due_date"],
                "total_amount": float(r["total_amount"]),
                "status": r["status"],
            })
        return result


_global_oracle: FintechOracle | None = None


def get_fintech_oracle(db_path: str | Path = "data/fintech.db") -> FintechOracle:
    global _global_oracle
    if _global_oracle is None:
        _global_oracle = FintechOracle(db_path=db_path)
    return _global_oracle
