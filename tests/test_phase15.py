"""Unit & Integration tests for Phase 15: FINTECH-ORACLE.

Tests:
  - Transaction ledger, auto-categorization, and monthly summary calculation
  - Bank statement CSV parsing and net cash-flow computation
  - Subscription tracking, monthly burn-rate radar, and renewal alerts
  - Client invoice generation with GST/tax calculation and formatted markdown
  - Tool registration and execution in ToolRegistry
  - FastAPI /api/finance/* endpoints
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from finance.oracle import FintechOracle
from tools.finance import register_finance_tools
from tools.registry import ToolRegistry
from web.server import create_app


@pytest.fixture
def temp_oracle(tmp_path: Path) -> FintechOracle:
    db_file = tmp_path / "fintech_test.db"
    return FintechOracle(db_path=db_file)


def test_transaction_recording_and_auto_categorize(temp_oracle: FintechOracle):
    # Test auto categorization
    assert temp_oracle.auto_categorize("AWS cloud computing bill") == "saas"
    assert temp_oracle.auto_categorize("Swiggy food delivery") == "food"
    assert temp_oracle.auto_categorize("Netflix Premium subscription") == "entertainment"
    assert temp_oracle.auto_categorize("Client Upwork payment") == "income"

    # Record debit
    t1 = temp_oracle.record_transaction(
        amount=1499.0,
        description="ChatGPT Plus subscription",
        date="2026-10-05",
        txn_type="debit",
    )
    assert t1["amount"] == 1499.0
    assert t1["category"] == "saas"
    assert t1["txn_type"] == "debit"

    # Record credit
    t2 = temp_oracle.record_transaction(
        amount=45000.0,
        description="Freelance Client payment",
        date="2026-10-08",
        txn_type="credit",
    )
    assert t2["amount"] == 45000.0
    assert t2["txn_type"] == "credit"

    # Summary
    summary = temp_oracle.get_summary(month="2026-10")
    assert summary["total_income"] == 45000.0
    assert summary["total_expenses"] == 1499.0
    assert summary["net_savings"] == 43501.0
    assert summary["transaction_count"] == 2
    assert len(summary["categories"]) > 0
    assert summary["categories"][0]["category"] == "saas"


def test_parse_statement_csv(temp_oracle: FintechOracle):
    csv_data = """Date,Particulars,Debit,Credit,Balance
2026-10-01,Opening Balance,0,50000,50000
2026-10-02,Zomato Food Order,450,0,49550
2026-10-03,GitHub Copilot,820,0,48730
2026-10-04,Consulting Fee,0,15000,63730
"""
    res = temp_oracle.parse_statement_csv(csv_data)
    assert res["transactions_parsed"] == 4
    assert res["total_inflow"] == 65000.0
    assert res["total_outflow"] == 1270.0
    assert res["net_flow"] == 63730.0


def test_subscription_burn_rate_radar(temp_oracle: FintechOracle):
    # Track monthly sub
    temp_oracle.track_subscription(
        name="ChatGPT Plus",
        amount=1999.0,
        billing_cycle="monthly",
        renewal_day=15,
        category="saas",
    )
    # Track yearly sub (12000 / 12 = 1000/mo)
    temp_oracle.track_subscription(
        name="AWS Cloud Reserved",
        amount=12000.0,
        billing_cycle="yearly",
        renewal_day=20,
        category="saas",
    )

    subs = temp_oracle.list_subscriptions()
    assert subs["active_subscriptions_count"] == 2
    # 1999 + 1000 = 2999/mo
    assert subs["monthly_burn_rate"] == 2999.0
    assert subs["annual_burn_rate"] == 35988.0

    # Test upcoming renewals check
    upcoming = temp_oracle.check_upcoming_renewals(days_ahead=31)
    assert len(upcoming) >= 1


def test_generate_client_invoice(temp_oracle: FintechOracle):
    items = [
        {"name": "Backend FastAPI Development", "rate": 2000.0, "qty": 10},
        {"name": "Database Architecture & Optimization", "rate": 2500.0, "qty": 4},
    ]
    # Subtotal = 20000 + 10000 = 30000
    # 18% GST = 5400
    # Total = 35400
    inv = temp_oracle.generate_invoice(
        client_name="Acme Corp",
        client_email="billing@acme.com",
        items=items,
        invoice_number="INV-2026-001",
        tax_rate_pct=18.0,
    )

    assert inv["invoice_number"] == "INV-2026-001"
    assert inv["subtotal"] == 30000.0
    assert inv["tax_amount"] == 5400.0
    assert inv["total_amount"] == 35400.0
    assert "Acme Corp" in inv["markdown"]
    assert "₹35,400.00" in inv["markdown"]

    # Verify invoice listing
    invoices = temp_oracle.list_invoices()
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == "INV-2026-001"


def test_finance_tools_registration(temp_oracle: FintechOracle):
    registry = ToolRegistry()
    registered_oracle = register_finance_tools(registry, oracle=temp_oracle)
    assert registered_oracle is temp_oracle

    assert registry.get("record_finance_transaction") is not None
    assert registry.get("get_financial_summary") is not None
    assert registry.get("track_recurring_subscription") is not None
    assert registry.get("list_active_subscriptions") is not None
    assert registry.get("generate_client_invoice") is not None

    # Test tool handler
    rec_fn = registry.get("record_finance_transaction").handler
    res = rec_fn(amount=500.0, description="Uber cab ride", category="travel")
    assert res["amount"] == 500.0
    assert res["category"] == "travel"


@pytest.mark.asyncio
async def test_finance_web_api(temp_oracle: FintechOracle):
    registry = ToolRegistry()
    register_finance_tools(registry, oracle=temp_oracle)

    mock_orch = MagicMock()
    mock_orch.config = {"web": {"allow_remote": True}}
    mock_orch.registry = registry
    mock_orch.finance = temp_oracle

    app = create_app(mock_orch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /api/finance/transaction
        r = await client.post("/api/finance/transaction", json={
            "amount": 2500.0,
            "description": "Starbucks Coffee & Snacks",
            "category": "food",
            "txn_type": "debit"
        })
        assert r.status_code == 200
        assert r.json()["amount"] == 2500.0

        # 2. GET /api/finance/summary
        r = await client.get("/api/finance/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_expenses" in data
        assert data["total_expenses"] == 2500.0

        # 3. POST /api/finance/subscription
        r = await client.post("/api/finance/subscription", json={
            "name": "GitHub Copilot",
            "amount": 850.0,
            "billing_cycle": "monthly",
            "renewal_day": 12,
            "category": "saas"
        })
        assert r.status_code == 200
        assert r.json()["status"] == "tracked"

        # 4. GET /api/finance/subscriptions
        r = await client.get("/api/finance/subscriptions")
        assert r.status_code == 200
        subs_data = r.json()
        assert subs_data["monthly_burn_rate"] == 850.0

        # 5. POST /api/finance/invoice
        r = await client.post("/api/finance/invoice", json={
            "client_name": "Vertex AI Labs",
            "items": [{"name": "AI Integration", "rate": 5000.0, "qty": 2}],
            "tax_rate_pct": 18.0
        })
        assert r.status_code == 200
        inv_data = r.json()
        assert inv_data["subtotal"] == 10000.0
        assert inv_data["total_amount"] == 11800.0
