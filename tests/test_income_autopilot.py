"""Unit tests for LUMI Live Income Autopilot Daemon (core/income_autopilot.py)."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.income_autopilot import IncomeAutopilotDaemon
from tools.registry import ToolRegistry


def test_income_autopilot_tool_registration(tmp_path: Path):
    reg = ToolRegistry()
    daemon = IncomeAutopilotDaemon(registry=reg, workspace_root=tmp_path)
    assert reg.get("run_income_autopilot") is not None
    assert reg.get("get_live_income_leads") is not None
    assert daemon.capital_dir.exists()


def test_income_autopilot_live_lead_harvesting(tmp_path: Path):
    # Create dummy starter tool file
    tools_dir = tmp_path / "data" / "synthesized_tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "stripe_webhook_guard.py").write_text("# guard", encoding="utf-8")

    fake_api_payload = {
        "result": {
            "projects": [
                {
                    "id": 998877,
                    "title": "Build Stripe Webhook Handler in Python FastAPI",
                    "preview_description": "Need Stripe signature verification and async API.",
                    "budget": {"minimum": 250.0, "maximum": 500.0},
                    "currency": {"code": "USD"},
                    "bid_stats": {"bid_count": 4},
                    "seo_url": "python/Build-Stripe-Webhook-Handler-998877",
                },
                {
                    "id": 112233,
                    "title": "Zero budget spam",
                    "budget": {"minimum": 0.0, "maximum": 0.0},
                    "currency": {"code": "USD"},
                },
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(fake_api_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    daemon = IncomeAutopilotDaemon(workspace_root=tmp_path)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        leads = daemon.fetch_live_freelance_leads(queries=["stripe fastapi"], max_per_query=2)

    assert len(leads) == 1
    lead = leads[0]
    assert lead.lead_id == "fl_998877"
    assert lead.recommended_bid_usd == 362.5
    assert lead.matched_skill == "stripe_webhook_guard"
    assert (Path(lead.pitch_dir) / "PROPOSAL.md").exists()
    assert (Path(lead.pitch_dir) / "stripe_webhook_guard.py").exists()
    assert daemon.leads_file.exists()


def test_income_autopilot_commercial_bundle_upgrade():
    daemon = IncomeAutopilotDaemon(workspace_root=Path(__file__).resolve().parent.parent)
    res = daemon.upgrade_commercial_fastapi_bundle()
    zp = Path(res["zip_path"])
    assert zp.exists()
    assert res["zip_bytes"] > 2000
    assert "stripe_webhook_guard.py" in res["bundled_modules"]
    with zipfile.ZipFile(zp, "r") as zf:
        names = zf.namelist()
        assert "app/main.py" in names or "app\\main.py" in names
        assert "Dockerfile" in names
