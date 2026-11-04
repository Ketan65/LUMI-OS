"""Tests for Phase 2: Long-Term Memory (Facts, Persistence, Tools, and Injection)."""
from brain.ollama_adapter import build_system_prompt, set_facts
from memory.repo import MemoryRepo
from memory import store
from tools.memory import register_memory_tools
from tools.registry import ToolRegistry


def test_facts_store_lifecycle(tmp_path):
    db = tmp_path / "test.db"
    store.init_db(db)

    # 1. Save facts
    store.save_fact("user_name", "Boss", category="identity", db_path=db)
    store.save_fact("monthly_cap", "5000", category="budget", db_path=db)
    assert store.count_facts(db) == 2

    # 2. Get facts
    all_facts = store.get_facts(db_path=db)
    assert len(all_facts) == 2
    keys = {f["key"] for f in all_facts}
    assert "user_name" in keys and "monthly_cap" in keys

    # Category filter
    id_facts = store.get_facts(category="identity", db_path=db)
    assert len(id_facts) == 1 and id_facts[0]["value"] == "Boss"

    # 3. Search facts
    results = store.search_facts("Bos", db_path=db)
    assert len(results) == 1 and results[0]["key"] == "user_name"

    # 4. Upsert (update existing key)
    store.save_fact("user_name", "Commander", category="identity", db_path=db)
    assert store.count_facts(db) == 2
    updated = store.search_facts("user_name", db_path=db)
    assert updated[0]["value"] == "Commander"

    # 5. Delete fact (soft delete)
    assert store.delete_fact("monthly_cap", db_path=db) is True
    assert store.count_facts(db) == 1
    assert len(store.get_facts(active_only=True, db_path=db)) == 1
    assert store.delete_fact("nonexistent", db_path=db) is False


def test_memory_repo_and_tools(tmp_path):
    cfg = {"memory": {"db_path": str(tmp_path / "repo.db"), "backup_dir": str(tmp_path / "b")}}
    repo = MemoryRepo(cfg)
    reg = ToolRegistry()
    register_memory_tools(reg, repo)

    rem_tool = reg.get("remember").handler
    rec_tool = reg.get("recall").handler
    list_tool = reg.get("list_facts").handler
    forget_tool = reg.get("forget").handler

    # Test remember
    out = rem_tool("framework", "FastAPI", "tech")
    assert "Yaad rakh liya" in out
    assert repo.count_facts() == 1

    # Test recall
    rec_out = rec_tool("fast")
    assert "FastAPI" in rec_out

    # Test list_facts
    l_out = list_tool()
    assert "framework" in l_out

    # Test forget
    f_out = forget_tool("framework")
    assert "bhool gaya" in f_out
    assert repo.count_facts() == 0


def test_facts_injected_into_system_prompt():
    set_facts(["user_name: Boss", "preferred_style: concise"])
    cfg = {
        "persona": {"name": "LUMI", "language": "Hinglish"},
        "allowed_paths": ["C:\\LUMI"]
    }
    prompt = build_system_prompt(cfg)
    assert "USER FACTS" in prompt
    assert "user_name: Boss" in prompt
    assert "preferred_style: concise" in prompt
    set_facts([])  # cleanup


def test_facts_slash_commands(tmp_path):
    from core.orchestrator import Orchestrator
    from conftest import FakeBrain
    cfg = {"memory": {"db_path": str(tmp_path / "orch.db"), "backup_dir": str(tmp_path / "b")}}
    repo = MemoryRepo(cfg)
    orch = Orchestrator(brain=FakeBrain(), config=cfg, memory=repo)

    # Empty facts
    _, text = orch.command("/facts")
    assert "koi facts saved nahi hain" in text

    # Remember command
    _, text = orch.command("/remember favorite_editor: VS Code")
    assert "Yaad rakh liya" in text
    assert repo.count_facts() == 1

    # List facts
    _, text = orch.command("/facts")
    assert "favorite_editor" in text and "VS Code" in text

    # Forget command
    _, text = orch.command("/forget favorite_editor")
    assert "bhool gaya" in text
    assert repo.count_facts() == 0
