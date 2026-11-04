"""Console chat loop — text in, LUMI reply out. Slash-commands + y/N gate."""

from __future__ import annotations

from core.orchestrator import Orchestrator

EXIT_WORDS = {"exit", "quit", "q"}


def ask_user(tool_name: str, args: dict) -> bool:
    """SafetyGate prompt — default is NO."""
    try:
        answer = input(f"ALLOW {tool_name}({args})? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt, OSError):
        return False   # no console (web/hidden process) — refuse safely, never hang
    return answer in {"y", "yes"}


def web_asker(tool_name: str, args: dict) -> bool:
    """Web mode: no stdin prompts (Task I me approval flow aayega) — refuse + note."""
    print(f"[web] permission '{tool_name}' abhi approve nahi ho sakti (CLI mode "
          f"me chalao) — refused: {args}")
    return False


def _handle_command(cmd: str, orchestrator: Orchestrator) -> bool:
    """Returns False when the user asked to quit (dispatch lives in orchestrator)."""
    should_exit, text = orchestrator.command(cmd)
    print(f"LUMI: {text}")
    return not should_exit


def run(orchestrator: Orchestrator) -> None:
    print("LUMI ready — (/history /audit /tools /model /projects /use /new "
          "/journal /reflect /backup, exit = band)\n")
    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except EOFError:
                break
            if not user_input:
                continue
            if user_input.lower() in EXIT_WORDS:
                print("LUMI: Chalo, milte hain phir! Bye boss 👋")
                break
            if user_input.startswith("/"):
                if not _handle_command(user_input, orchestrator):
                    break
                continue
            try:
                turn = orchestrator.run_turn(user_input)   # same loop as web
            except ConnectionError as exc:
                print(f"LUMI: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 — never dump a stacktrace
                print(f"LUMI: kuch gadbad ho gayi — {exc}")
                continue
            print(f"LUMI: {turn['reply']}\n")
            orchestrator.maybe_reflect(user_input, turn["reply"])  # reply ke BAAD
    except KeyboardInterrupt:
        print("\nLUMI: Ruk jaate hain. Jab bulaoge, tab hazir.")
    finally:
        orchestrator.session_end_reflect()      # exit pe session_end reflection
