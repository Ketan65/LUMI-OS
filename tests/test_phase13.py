"""Unit & Integration tests for Phase 13: BIOMETRIC-GUARD.

Tests:
  - FaceProfileManager (feature extraction, enrollment, cosine distance match, persistence)
  - PrivacyShield (window minimization, restore, status)
  - PresenceWatcher (state transitions: AWAY, PRESENT_MASTER, PRESENT_UNKNOWN, SHOULDER_SURF, auto-lock)
  - Tools registration and execution
  - FastAPI /api/biometrics endpoints
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from safety.biometrics import FaceProfileManager, PrivacyShield, PresenceWatcher
from tools.biometrics import register_biometrics_tools
from tools.registry import ToolRegistry
from web.server import create_app


@pytest.fixture
def tmp_bio_path(tmp_path: Path) -> Path:
    return tmp_path / "biometrics_test.json"


@pytest.fixture
def profile_manager(tmp_bio_path: Path) -> FaceProfileManager:
    return FaceProfileManager(data_path=tmp_bio_path)


def test_face_profile_manager_enroll_and_match(profile_manager: FaceProfileManager):
    # Create two synthetic 128D feature vectors
    vec_master_1 = np.random.randn(128).astype(np.float32)
    vec_master_1 /= np.linalg.norm(vec_master_1)

    vec_master_2 = vec_master_1 + np.random.normal(0, 0.05, 128).astype(np.float32)
    vec_master_2 /= np.linalg.norm(vec_master_2)

    vec_stranger = np.random.randn(128).astype(np.float32)
    vec_stranger /= np.linalg.norm(vec_stranger)

    # Enroll master profile
    success = profile_manager.enroll("master", [vec_master_1, vec_master_2])
    assert success is True
    assert profile_manager.is_enrolled("master")
    assert "master" in profile_manager.get_profiles()

    # Match test
    is_match, sim = profile_manager.match(vec_master_1, "master", threshold=0.7)
    assert is_match is True
    assert sim > 0.8

    # Stranger test (cosine distance should be low)
    # Cosine between two random 128D vectors is near 0
    is_match_stranger, sim_stranger = profile_manager.match(vec_stranger, "master", threshold=0.7)
    assert is_match_stranger is False
    assert sim_stranger < 0.7


def test_face_profile_manager_persistence(tmp_bio_path: Path):
    mgr1 = FaceProfileManager(data_path=tmp_bio_path)
    sample_vec = np.ones(128, dtype=np.float32) / np.sqrt(128)
    mgr1.enroll("boss", [sample_vec])
    assert mgr1.is_enrolled("boss")

    # Load in new instance
    mgr2 = FaceProfileManager(data_path=tmp_bio_path)
    assert mgr2.is_enrolled("boss")
    assert mgr2.get_profiles() == ["boss"]

    # Delete profile
    deleted = mgr2.delete_profile("boss")
    assert deleted is True
    assert not mgr2.is_enrolled("boss")


def test_privacy_shield_activation_and_deactivation():
    shield = PrivacyShield(sensitive_keywords=["test_secret_window"])
    assert not shield.is_shielded

    # Simulate activation
    shield.activate()
    assert shield.is_shielded
    status = shield.status()
    assert status["is_shielded"] is True

    # Deactivate
    shield.deactivate()
    assert not shield.is_shielded
    assert shield.status()["is_shielded"] is False


def test_presence_watcher_state_transitions(profile_manager: FaceProfileManager):
    sample_vec = np.ones(128, dtype=np.float32) / np.sqrt(128)
    profile_manager.enroll("master", [sample_vec])

    watcher = PresenceWatcher(
        config={"biometrics": {"enabled": True, "auto_lock": True, "lock_timeout_sec": 10}},
        profile_mgr=profile_manager,
    )
    locked_called = False

    def mock_lock():
        nonlocal locked_called
        locked_called = True

    watcher.mock_lock_callback = mock_lock

    # 1. Test PRESENT_MASTER
    watcher.set_test_frame(num_faces=1, is_master=True)
    watcher.tick()
    assert watcher.state == "PRESENT_MASTER"
    assert watcher.active_faces == 1
    assert watcher.master_detected is True
    assert not watcher.shield.is_shielded

    # 2. Test SHOULDER_SURF (>= 2 faces)
    watcher.set_test_frame(num_faces=2, is_master=True)
    watcher.tick()
    assert watcher.state == "SHOULDER_SURF"
    assert watcher.active_faces == 2
    assert watcher.shield.is_shielded is True

    # 3. Test Master Return clears shield
    watcher.set_test_frame(num_faces=1, is_master=True)
    watcher.tick()
    assert watcher.state == "PRESENT_MASTER"
    assert watcher.shield.is_shielded is False

    # 4. Test PRESENT_UNKNOWN (1 face, not master)
    watcher.set_test_frame(num_faces=1, is_master=False)
    watcher.tick()
    assert watcher.state == "PRESENT_UNKNOWN"
    assert watcher.master_detected is False

    # 5. Test AWAY and Auto-lock
    watcher.set_test_frame(num_faces=0, is_master=False)
    watcher.tick()
    assert watcher.state == "AWAY"
    assert not locked_called

    # Fast forward away time past lock timeout
    watcher.away_start_time = time.time() - 20.0
    watcher.tick()
    assert watcher.state == "AWAY"
    assert locked_called is True
    assert watcher.lock_triggered is True


def test_biometrics_tools_registration(profile_manager: FaceProfileManager):
    registry = ToolRegistry()
    watcher = PresenceWatcher(profile_mgr=profile_manager)
    registered_watcher = register_biometrics_tools(registry, watcher=watcher)

    assert registered_watcher is watcher
    assert registry.get("presence_status") is not None
    assert registry.get("configure_biometrics") is not None
    assert registry.get("enroll_master_face") is not None
    assert registry.get("privacy_shield_control") is not None
    assert registry.get("lock_workstation_now") is not None

    # Test presence_status tool call
    status_fn = registry.get("presence_status").handler
    res = status_fn()
    assert "state" in res
    assert "auto_lock_enabled" in res

    # Test configure_biometrics tool call
    config_fn = registry.get("configure_biometrics").handler
    cfg_res = config_fn(auto_lock=True, lock_timeout_sec=45)
    assert cfg_res["auto_lock_enabled"] is True
    assert cfg_res["lock_timeout_sec"] == 45

    # Test privacy_shield_control tool call
    shield_fn = registry.get("privacy_shield_control").handler
    s_res = shield_fn(active=True)
    assert s_res["is_shielded"] is True
    s_off = shield_fn(active=False)
    assert s_off["is_shielded"] is False

    # Test lock_workstation_now tool call
    locked = False
    watcher.mock_lock_callback = lambda: (setattr(watcher, "mock_locked", True))
    lock_fn = registry.get("lock_workstation_now").handler
    lock_res = lock_fn()
    assert lock_res["status"] == "locked"
    assert getattr(watcher, "mock_locked", False) is True


@pytest.mark.asyncio
async def test_biometrics_web_api_endpoints(profile_manager: FaceProfileManager):
    registry = ToolRegistry()
    watcher = PresenceWatcher(profile_mgr=profile_manager)
    register_biometrics_tools(registry, watcher=watcher)

    mock_orch = MagicMock()
    mock_orch.config = {"web": {"allow_remote": True}}
    mock_orch.registry = registry
    mock_orch.biometrics = watcher

    app = create_app(mock_orch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/biometrics/status
        r = await client.get("/api/biometrics/status")
        assert r.status_code == 200
        data = r.json()
        assert "state" in data
        assert "active_faces" in data

        # 2. POST /api/biometrics/config
        r = await client.post("/api/biometrics/config", json={
            "auto_lock": True,
            "lock_timeout_sec": 90,
            "shoulder_surf_shield": True
        })
        assert r.status_code == 200
        cfg = r.json()
        assert cfg["auto_lock_enabled"] is True
        assert cfg["lock_timeout_sec"] == 90

        # 3. POST /api/biometrics/shield
        r = await client.post("/api/biometrics/shield", json={"active": True})
        assert r.status_code == 200
        assert r.json()["is_shielded"] is True

        r = await client.post("/api/biometrics/shield", json={"active": False})
        assert r.status_code == 200
        assert r.json()["is_shielded"] is False

        # 4. POST /api/biometrics/lock
        watcher.mock_lock_callback = lambda: None
        r = await client.post("/api/biometrics/lock")
        assert r.status_code == 200
        assert r.json()["status"] == "locked"

        # 5. POST /api/biometrics/enroll
        r = await client.post("/api/biometrics/enroll", json={"profile_name": "master", "sample_count": 2})
        assert r.status_code == 200
        assert r.json()["success"] is True
