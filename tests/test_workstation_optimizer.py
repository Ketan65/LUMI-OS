"""Test suite for LUMI Workstation Optimizer (v42.0)."""

from pathlib import Path
import sqlite3
import pytest

from core.workstation_optimizer import WorkstationOptimizer
from tools.registry import ToolRegistry


@pytest.fixture
def temp_optimizer(tmp_path: Path):
    registry = ToolRegistry()
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = data_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy sqlite db
    db_file = data_dir / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE t (id INT, v TEXT);")
    conn.execute("INSERT INTO t VALUES (1, 'alpha'), (2, 'beta');")
    conn.commit()
    conn.close()

    # Create old dummy audio file
    dummy_wav = audio_dir / "old_audio.wav"
    dummy_wav.write_bytes(b"RIFF" + b"\x00" * 100)

    opt = WorkstationOptimizer(registry=registry, workspace_root=tmp_path)
    return opt, registry


class TestWorkstationOptimizer:
    def test_01_tool_registration(self, temp_optimizer):
        opt, registry = temp_optimizer
        tools = registry.list_all()
        names = [t.name for t in tools]
        assert "optimize_workstation_performance" in names
        assert "get_workstation_vitals" in names

    def test_02_get_vitals(self, temp_optimizer):
        opt, _ = temp_optimizer
        vitals = opt.get_vitals()
        assert vitals["status"] == "healthy"
        assert "cpu_usage_pct" in vitals
        assert "ram_used_gb" in vitals
        assert "ram_total_gb" in vitals
        assert "top_consumers" in vitals

    def test_03_optimize_all(self, temp_optimizer):
        opt, _ = temp_optimizer
        # Set max age to 0 to force purge
        res = opt.optimize_all(max_audio_age_seconds=0)
        assert res["status"] == "optimal"
        assert "ram_freed_mb" in res
        assert "test.db" in res["sqlite_vacuumed"]
        assert res["temp_files_pruned"] >= 1
        assert res["elapsed_ms"] > 0
