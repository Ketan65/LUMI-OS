"""Fintech-Oracle Tools for LUMI (Phase 15).

Provides LLM-callable tools for:
  - record_finance_transaction: records personal income/expense into encrypted/isolated local ledger
  - get_financial_summary: calculates monthly cash-flow, top spending categories, and savings rate
  - track_recurring_subscription: manages SaaS subscriptions, renewal alerts, and monthly burn rate
  - list_active_subscriptions: returns active subscriptions and next renewal countdown
  - generate_client_invoice: generates professional client invoice with GST/tax breakdown
"""

from __future__ import annotations

import logging
from typing import Any

from finance.oracle import FintechOracle, get_fintech_oracle
from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.tools.finance")


def register_finance_tools(
    registry: ToolRegistry,
    oracle: FintechOracle | None = None,
) -> FintechOracle:
    """Registers financial intelligence and invoicing tools into ToolRegistry."""
    active_oracle = oracle or get_fintech_oracle()

    def record_finance_transaction(
        amount: float,
        description: str,
        date: str | None = None,
        category: str | None = None,
        txn_type: str = "debit",
    ) -> dict:
        """Records a single financial transaction (expense or income) into the local private ledger."""
        return active_oracle.record_transaction(
            amount=amount,
            description=description,
            date=date,
            category=category,
            txn_type=txn_type,
        )

    def get_financial_summary(month: str | None = None) -> dict:
        """Calculates total income, expenses, category spending breakdown, and savings rate for a month (e.g. '2026-10')."""
        return active_oracle.get_summary(month=month)

    def track_recurring_subscription(
        name: str,
        amount: float,
        billing_cycle: str = "monthly",
        renewal_day: int = 1,
        category: str = "saas",
    ) -> dict:
        """Registers or updates a recurring monthly or yearly subscription to track burn rate and renewals."""
        return active_oracle.track_subscription(
            name=name,
            amount=amount,
            billing_cycle=billing_cycle,
            renewal_day=renewal_day,
            category=category,
        )

    def list_active_subscriptions() -> dict:
        """Returns all tracked subscriptions, monthly burn rate, and days left until next renewal."""
        return active_oracle.list_subscriptions()

    def generate_client_invoice(
        client_name: str,
        items: list[dict],
        client_email: str | None = None,
        invoice_number: str | None = None,
        tax_rate_pct: float = 18.0,
    ) -> dict:
        """Generates a professional client invoice with automated line totals, GST/tax, and printable markdown."""
        return active_oracle.generate_invoice(
            client_name=client_name,
            items=items,
            client_email=client_email,
            invoice_number=invoice_number,
            tax_rate_pct=tax_rate_pct,
        )

    # Register in ToolRegistry
    registry.register(Tool(
        name="record_finance_transaction",
        description="Records an income or expense transaction in LUMI's private on-device financial ledger.",
        params_schema={
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Transaction amount in local currency (e.g. 1500)"},
                "description": {"type": "string", "description": "Vendor or transaction description (e.g. 'AWS Cloud hosting')"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format (defaults to today)"},
                "category": {"type": "string", "description": "Optional category: saas, food, travel, utilities, income"},
                "txn_type": {"type": "string", "enum": ["debit", "credit"], "description": "'debit' for expense, 'credit' for income"},
            },
            "required": ["amount", "description"],
        },
        handler=record_finance_transaction,
        risk="auto",
    ))

    registry.register(Tool(
        name="get_financial_summary",
        description="Calculates monthly financial breakdown, total income, total expenses, net savings, and category distribution.",
        params_schema={
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "Target month in YYYY-MM format (e.g. '2026-10')"},
            },
        },
        handler=get_financial_summary,
        risk="auto",
    ))

    registry.register(Tool(
        name="track_recurring_subscription",
        description="Tracks recurring SaaS, entertainment, or utility subscriptions to compute burn rate.",
        params_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Service name (e.g. 'ChatGPT Plus')"},
                "amount": {"type": "number", "description": "Subscription charge (e.g. 1999)"},
                "billing_cycle": {"type": "string", "enum": ["monthly", "yearly"], "default": "monthly"},
                "renewal_day": {"type": "integer", "description": "Day of the month the subscription renews (1-31)"},
                "category": {"type": "string", "default": "saas"},
            },
            "required": ["name", "amount"],
        },
        handler=track_recurring_subscription,
        risk="auto",
    ))

    registry.register(Tool(
        name="list_active_subscriptions",
        description="Lists all recurring subscriptions, monthly burn rate, and days until next renewal.",
        params_schema={"type": "object", "properties": {}},
        handler=list_active_subscriptions,
        risk="auto",
    ))

    registry.register(Tool(
        name="generate_client_invoice",
        description="Generates a formatted freelance/client invoice with line items, tax/GST calculation, and printable layout.",
        params_schema={
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client or company name"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Description of work done"},
                            "rate": {"type": "number", "description": "Hourly or unit rate"},
                            "qty": {"type": "number", "description": "Hours or units completed"},
                        },
                        "required": ["name", "rate"],
                    },
                    "description": "List of line items",
                },
                "client_email": {"type": "string", "description": "Optional client email address"},
                "invoice_number": {"type": "string", "description": "Optional invoice ID (e.g. 'INV-00104')"},
                "tax_rate_pct": {"type": "number", "default": 18.0, "description": "GST or tax percentage"},
            },
            "required": ["client_name", "items"],
        },
        handler=generate_client_invoice,
        risk="auto",
    ))

    return active_oracle
