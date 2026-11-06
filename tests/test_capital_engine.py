"""Test suite for LUMI Autonomous Admin Capital Engine (v41.0)."""

import json
from pathlib import Path
import pytest

from core.capital_engine import CapitalEngine, get_capital_engine
from tools.registry import ToolRegistry


@pytest.fixture
def temp_capital_engine(tmp_path: Path):
    registry = ToolRegistry()
    capital_dir = tmp_path / "capital"
    engine = CapitalEngine(
        registry=registry,
        workspace_root=tmp_path,
        capital_dir=capital_dir,
    )
    return engine, registry


class TestCapitalEngine:
    def test_01_tool_registration(self, temp_capital_engine):
        engine, registry = temp_capital_engine
        tools = registry.list_all()
        tool_names = [t.name for t in tools]

        assert "get_capital_overview" in tool_names
        assert "bid_and_build_gig" in tool_names
        assert "hunt_open_source_bounties" in tool_names
        assert "forge_micro_saas" in tool_names
        assert "scan_quant_alpha" in tool_names

    def test_02_capital_overview(self, temp_capital_engine):
        engine, _ = temp_capital_engine
        overview = engine.get_capital_overview()

        assert overview["status"] == "active"
        assert overview["currency"] == "USD"
        assert overview["realized_revenue_total"] >= 1850.0
        assert "breakdown" in overview
        assert "top_actionable_directives" in overview
        assert len(overview["top_actionable_directives"]) >= 4

    def test_03_bid_and_build_gig_fulfillment(self, temp_capital_engine):
        engine, _ = temp_capital_engine
        res = engine.bid_and_build_gig(
            title="FastAPI JWT Auth Microservice",
            brief="Build secure authentication service with token revocation and sqlite database.",
            client_name="FintechStudio LLC",
            budget_usd=450.0,
        )

        assert res["status"] == "success"
        assert res["budget_usd"] == 450.0
        assert res["client_name"] == "FintechStudio LLC"
        assert len(res["files"]) == 4

        # Verify generated files on disk
        gig_dir = Path(res["deliverable_directory"])
        assert gig_dir.exists()
        assert (gig_dir / "fastapi_jwt_auth_microservice.py").exists()
        assert (gig_dir / "test_fastapi_jwt_auth_microservice.py").exists()
        assert (gig_dir / "README.md").exists()
        assert (gig_dir / "INVOICE.json").exists()

        # Check invoice content
        inv_data = json.loads((gig_dir / "INVOICE.json").read_text(encoding="utf-8"))
        assert inv_data["total_usd"] == 450.0
        assert inv_data["client_name"] == "FintechStudio LLC"

    def test_04_forge_micro_saas(self, temp_capital_engine):
        engine, _ = temp_capital_engine
        res = engine.forge_micro_saas(
            product_name="InvoicePulse AI",
            niche="Automated PDF Invoice OCR API",
            projected_mrr=600.0,
        )

        assert res["status"] == "success"
        assert res["projected_mrr_usd"] == 600.0
        assert "POST /api/v1/webhook/stripe" in res["endpoints"]

        # Check files on disk
        saas_dir = Path(res["asset_directory"])
        assert (saas_dir / "main.py").exists()
        assert (saas_dir / "Dockerfile").exists()

    def test_05_quant_alpha_scan(self, temp_capital_engine):
        engine, _ = temp_capital_engine
        res = engine.scan_quant_alpha(symbol="BTC/USDT", strategy="ema_momentum")

        assert res["status"] == "success"
        assert res["symbol"] == "BTC/USDT"
        assert "win_rate_pct" in res
        assert "sharpe_ratio" in res
        assert "suggested_risk_per_trade" in res

    def test_06_bounty_hunt_integration(self, temp_capital_engine):
        engine, _ = temp_capital_engine
        # Hunt against LUMI core directory
        res = engine.hunt_bounties(target_dir="core")
        assert res["status"] == "success"
        assert "total_estimated_bounty_usd" in res
