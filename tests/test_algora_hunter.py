"""Unit tests for LUMI Algora Hunter Daemon (core/algora_hunter.py)."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from core.algora_hunter import AlgoraHunterDaemon, AlgoraBountyCandidate
from core.github_bridge import GitHubBridgeEngine


def test_algora_hunter_initialization(tmp_path: Path):
    mock_bridge = MagicMock(spec=GitHubBridgeEngine)
    mock_bridge.has_token = True
    daemon = AlgoraHunterDaemon(workspace_root=tmp_path, bridge=mock_bridge)
    assert daemon.radar_file == tmp_path / "data" / "capital" / "bounties_radar.json"


def test_algora_hunter_scan_fresh_bounties(tmp_path: Path):
    mock_bridge = MagicMock(spec=GitHubBridgeEngine)
    mock_bridge.has_token = True
    mock_bridge.is_safe_target.return_value = (True, "Target verified safe")

    # Mock response from GitHub Search API
    mock_bridge._request.return_value = (
        200,
        {
            "items": [
                {
                    "html_url": "https://github.com/org/repo/issues/42",
                    "repository_url": "https://api.github.com/repos/org/repo",
                    "title": "Add support for FastAPI OAuth2 with $150 reward",
                    "body": "We are offering a $150 bounty for this feature.",
                    "number": 42,
                    "comments": 1,
                    "created_at": "2026-11-10T12:00:00Z",
                },
                {
                    "html_url": "https://github.com/org/busy-repo/issues/99",
                    "repository_url": "https://api.github.com/repos/org/busy-repo",
                    "title": "Fix React re-render bug with $50 bounty",
                    "body": "Small fix",
                    "number": 99,
                    "comments": 8,
                    "created_at": "2026-11-10T10:00:00Z",
                },
            ]
        },
    )

    daemon = AlgoraHunterDaemon(workspace_root=tmp_path, bridge=mock_bridge)
    candidates = daemon.scan_fresh_bounties()

    assert len(candidates) == 2
    # Fresh target with low comments should be first
    assert candidates[0].status == "FRESH_TARGET"
    assert candidates[0].reward_usd == 150
    assert candidates[0].language == "Python"
    assert candidates[1].status == "HIGH_COMPETITION"

    # Verify radar file written
    assert daemon.radar_file.exists()


def test_algora_hunter_prepare_claim_pr(tmp_path: Path):
    mock_bridge = MagicMock(spec=GitHubBridgeEngine)
    daemon = AlgoraHunterDaemon(workspace_root=tmp_path, bridge=mock_bridge)

    candidate = AlgoraBountyCandidate(
        bounty_id="algora_org_repo_10",
        repo="org/repo",
        issue_number=10,
        title="Fix CSV memory leak",
        reward_usd=100,
        competition_count=0,
        issue_url="https://github.com/org/repo/issues/10",
        status="FRESH_TARGET",
        language="Python",
        created_at="2026-11-10T12:00:00Z",
        summary="Memory issue in CSV reader",
    )

    claim = daemon.prepare_claim_pull_request(
        candidate=candidate,
        solution_code="def read_csv(): pass",
        file_path_in_repo="reader.py",
        solution_summary="Stream reader by chunks to avoid OOM.",
    )

    assert "@algora-pbc /claim #10" in claim["pr_body"]
    assert claim["repo"] == "org/repo"
    assert claim["claim_tag"] == "@algora-pbc /claim #10"
