"""File tools + project registry guards."""
from pathlib import Path

from tools.files import resolve_within, register_file_tools
from tools.projects import ProjectRegistry, _too_broad
from tools.registry import ToolRegistry


def test_resolve_within_blocks_traversal(home):
    assert resolve_within(str(home / "workspace" / "a.txt"), [str(home)]) is not None
    assert resolve_within(str(home / ".." / "x"), [str(home)]) is None


def test_write_overwrite_makes_backup(home):
    reg = ToolRegistry()
    register_file_tools(reg, [str(home)])
    p = str(home / "workspace" / "n.txt")
    write = reg.get("write_file").handler
    write(p, "one")
    out = write(p, "two")
    assert "purani copy" in out
    assert Path(p).read_text(encoding="utf-8") == "two"


def test_list_files_caps_entries(home):
    for i in range(80):
        (home / "workspace" / f"f{i}.txt").write_text("x", encoding="utf-8")
    reg = ToolRegistry()
    register_file_tools(reg, [str(home)])
    out = reg.get("list_files").handler(str(home / "workspace"))
    assert "aur 20 entries" in out


def test_register_project_is_ask_risk(home, tmp_path):
    from tools.projects import register_project_tools
    reg = ToolRegistry()
    register_project_tools(reg, ProjectRegistry([], str(tmp_path / "p.yaml")))
    assert reg.get("register_project").risk == "ask"


def test_too_broad_paths():
    assert _too_broad(Path("C:\\"))
    assert _too_broad(Path.home())
    assert _too_broad(Path("C:\\Windows"))
    assert not _too_broad(Path(__file__).resolve().parent.parent)


def test_add_refuses_drive_root(tmp_path):
    allowed: list[str] = []
    pr = ProjectRegistry(allowed, str(tmp_path / "p.yaml"))
    msg = pr.add("everything", "C:\\")
    assert "broad" in msg
    assert allowed == [] and pr.projects == []


def test_add_ok_extends_allowlist(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    allowed: list[str] = []
    pr = ProjectRegistry(allowed, str(tmp_path / "p.yaml"))
    assert pr.add("proj", str(proj)).startswith("Registered")
    assert str(proj.resolve()) in allowed
