"""SafetyGate: zones, boundary, traversal, fail-safe policy."""
import pytest

from safety.gate import SafetyGate


def gate(home, downloads, perms=None):
    cfg = {"allowed_paths": [str(home), str(downloads)],
           "permissions": perms or {"write_file": "ask", "delete_file": "ask",
                                    "register_project": "ask"}}
    return SafetyGate(cfg)


def test_write_in_workspace_is_auto(home, downloads):
    g = gate(home, downloads)
    p = str(home / "workspace" / "notes.txt")
    assert g.check("write_file", "ask", args={"path": p}) == (
        "allow", "override:write_in_workspace")


@pytest.mark.parametrize("rel", ["safety/gate.py", "config.yaml", "main.py",
                                 "newfile.txt", "data/lumi.db"])
def test_own_code_and_config_are_blocked(home, downloads, rel):
    g = gate(home, downloads)
    verdict, reason = g.check("write_file", "ask",
                              args={"path": str(home / rel)})
    assert (verdict, reason) == ("block", "protected")
    assert g.check("delete_file", "ask", args={"path": str(home / rel)})[0] == "block"


def test_traversal_out_of_workspace_is_protected(home, downloads):
    g = gate(home, downloads)
    sneaky = str(home / "workspace" / ".." / "safety" / "gate.py")
    assert g.check("write_file", "ask", args={"path": sneaky}) == ("block", "protected")


def test_traversal_out_of_allowed_roots_is_boundary(home, downloads):
    g = gate(home, downloads)
    sneaky = str(home / "workspace" / ".." / ".." / "evil.txt")
    assert g.check("write_file", "ask", args={"path": sneaky}) == ("block", "boundary")


def test_case_insensitive_path_cannot_bypass(home, downloads):
    g = gate(home, downloads)
    p = str(home / "SAFETY" / "GATE.PY")          # Windows is case-insensitive
    assert g.check("write_file", "ask", args={"path": p})[0] == "block"


def test_downloads_follows_policy_ask(home, downloads):
    g = gate(home, downloads)
    assert g.check("write_file", "ask",
                   args={"path": str(downloads / "a.txt")}) == ("ask", "policy:ask")


def test_workspace_delete_still_asks(home, downloads):
    g = gate(home, downloads)
    p = str(home / "workspace" / "a.txt")
    assert g.check("delete_file", "ask", args={"path": p})[0] == "ask"


def test_block_policy_beats_workspace_override(home, downloads):
    g = gate(home, downloads, perms={"write_file": "block"})
    p = str(home / "workspace" / "a.txt")
    assert g.check("write_file", "ask", args={"path": p})[0] == "block"


def test_register_project_asks(home, downloads):
    g = gate(home, downloads)
    assert g.check("register_project", "ask",
                   args={"name": "x", "path": "C:\\"})[0] == "ask"


def test_unknown_policy_value_fails_safe_to_ask(home, downloads):
    g = gate(home, downloads, perms={"read_file": "yolo"})
    assert g.check("read_file", "auto")[0] == "ask"


def test_default_asker_refuses(home, downloads):
    g = gate(home, downloads)
    assert g.confirm("write_file", {"path": "x"}) is False
