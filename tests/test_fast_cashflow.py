"""Test suite for LUMI Rapid Cashflow Dispatcher (v41.1)."""

from pathlib import Path
import pytest
from core.fast_cashflow import FastCashflowDispatcher
from tools.registry import ToolRegistry


@pytest.fixture
def temp_dispatcher(tmp_path: Path):
    registry = ToolRegistry()
    disp = FastCashflowDispatcher(registry=registry, workspace_root=tmp_path)
    return disp, registry


class TestFastCashflowDispatcher:
    def test_01_tool_registration(self, temp_dispatcher):
        disp, registry = temp_dispatcher
        tools = registry.list_all()
        names = [t.name for t in tools]
        assert "fetch_live_market_bounties" in names
        assert "solve_bounty_and_generate_pr" in names
        assert "pitch_and_build_freelance_gig" in names
        assert "package_commercial_digital_product" in names

    def test_02_solve_bounty(self, temp_dispatcher):
        disp, _ = temp_dispatcher
        res = disp.solve_bounty(
            issue_title="Fix CommandRegistrationError on startup",
            issue_url="https://github.com/example/repo/issues/4",
            issue_description="Startup crashes when custom slash commands are registered.",
            reward_amount="$500",
        )
        assert res["status"] == "success"
        assert res["reward_amount"] == "$500"
        sol_dir = Path(res["directory"])
        assert (sol_dir / "patch_solution.py").exists()
        assert (sol_dir / "test_patch_solution.py").exists()
        assert (sol_dir / "PULL_REQUEST.md").exists()

    def test_03_pitch_and_build_gig(self, temp_dispatcher):
        disp, _ = temp_dispatcher
        res = disp.pitch_and_build_gig(
            job_title="Build Real-time Python Webhook Receiver",
            job_description="Create a FastAPI webhook listener with SQLite queue and async dispatch.",
            client_platform="Upwork",
            rate_usd=500.0,
        )
        assert res["status"] == "success"
        assert res["quoted_rate_usd"] == 500.0
        assert Path(res["working_code_file"]).exists()
        assert Path(res["test_file"]).exists()
        assert Path(res["proposal_file"]).exists()

    def test_04_package_digital_product(self, temp_dispatcher):
        disp, _ = temp_dispatcher
        res = disp.package_digital_product(
            product_name="FastAPI Enterprise Starter",
            product_type="micro_saas",
            price_usd=49.0,
        )
        assert res["status"] == "success"
        assert res["sale_price_usd"] == 49.0
        assert Path(res["zip_package"]).exists()
        assert Path(res["sales_copy_file"]).exists()
