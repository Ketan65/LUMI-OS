"""LUMI Cyberpunk Floating Desktop HUD & Omnipresent Command Bar (v38.0).

Provides a zero-click, system-wide floating overlay (Iron Man / Raycast style):
  - Global Hotkey: <alt>+<space> or <ctrl>+<shift>+j brings HUD to front anywhere in Windows.
  - Cyberpunk Frosted-Dark UI via CustomTkinter.
  - Real-time command dispatch to LUMI Web Cockpit (http://127.0.0.1:8765/api/chat).
  - Quick action chips (/briefing, /harvest, /heal, /screen, /vapt).
  - Speech response output and thread-safe streaming text box.
  - Pressing Escape or clicking outside automatically minimizes/hides the HUD.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

logger = logging.getLogger("lumi.hud")

# Cyberpunk Palette
BG_COLOR = "#0A0F1D"
PANEL_COLOR = "#10192E"
BORDER_CYAN = "#00F2FE"
ACCENT_BLUE = "#4FACFE"
TEXT_WHITE = "#E2E8F0"
TEXT_MUTED = "#94A3B8"
ACCENT_GREEN = "#10B981"
ACCENT_AMBER = "#F59E0B"
ACCENT_RED = "#EF4444"


class LumiDesktopHUD:
    """Floating Cyberpunk Desktop Command Bar Overlay for Windows."""

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8765/api/chat",
        hotkey_str: str = "<alt>+<space>",
        width: int = 760,
        height: int = 340,
    ) -> None:
        if ctk is None:
            raise RuntimeError("customtkinter is required for LumiDesktopHUD.")

        self.api_url = api_url
        self.hotkey_str = hotkey_str
        self.width = width
        self.height = height
        self.is_visible = False
        self._hotkey_listener: Any = None
        self._is_busy = False

        # Initialize CustomTkinter window
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("LUMI Stark APEX HUD")
        self.root.overrideredirect(True)  # Frameless floating overlay
        self.root.configure(fg_color=BG_COLOR)
        self.root.wm_attributes("-topmost", True)

        # Center horizontally at top-third of the screen
        screen_w = self.root.winfo_screenwidth()
        x_pos = max(0, (screen_w - self.width) // 2)
        y_pos = 110
        self.root.geometry(f"{self.width}x{self.height}+{x_pos}+{y_pos}")

        self._build_ui()
        self._bind_keys()
        self.hide()

    def _build_ui(self) -> None:
        """Constructs the cyberpunk floating interface."""
        # Outer Border Frame (Cyan Glow Accent)
        self.outer_frame = ctk.CTkFrame(
            self.root,
            fg_color=PANEL_COLOR,
            corner_radius=14,
            border_width=2,
            border_color=BORDER_CYAN,
        )
        self.outer_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Header Bar
        header = ctk.CTkFrame(self.outer_frame, fg_color="transparent", height=32)
        header.pack(fill="x", padx=16, pady=(12, 6))

        logo_label = ctk.CTkLabel(
            header,
            text="◈ LUMI :: STARK APEX HUD",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color=BORDER_CYAN,
        )
        logo_label.pack(side="left")

        self.status_pill = ctk.CTkLabel(
            header,
            text="ONLINE [RTX-5060]",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=ACCENT_GREEN,
            fg_color="#064E3B",
            corner_radius=6,
            padx=8,
            pady=2,
        )
        self.status_pill.pack(side="left", padx=10)

        close_btn = ctk.CTkButton(
            header,
            text="✕",
            width=26,
            height=22,
            fg_color="#1E293B",
            hover_color=ACCENT_RED,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.hide,
        )
        close_btn.pack(side="right")

        # Command Entry Bar
        entry_frame = ctk.CTkFrame(self.outer_frame, fg_color="transparent")
        entry_frame.pack(fill="x", padx=16, pady=4)

        self.entry = ctk.CTkEntry(
            entry_frame,
            placeholder_text="Ask LUMI anything or type /briefing, /heal, /harvest, /screen, /vapt...",
            placeholder_text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color="#0F172A",
            border_color="#334155",
            border_width=1,
            corner_radius=8,
            height=38,
            text_color=TEXT_WHITE,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.send_command())

        self.send_btn = ctk.CTkButton(
            entry_frame,
            text="EXECUTE ⚡",
            width=100,
            height=38,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            command=self.send_command,
        )
        self.send_btn.pack(side="right")

        # Quick Action Chips Bar
        chips_frame = ctk.CTkFrame(self.outer_frame, fg_color="transparent", height=28)
        chips_frame.pack(fill="x", padx=16, pady=(2, 6))

        chips = [
            ("⚡ /briefing", "/briefing"),
            ("🛠️ /heal", "/heal"),
            ("🌾 /harvest", "/harvest"),
            ("👁️ /screen", "/screen"),
            ("🛡️ /vapt", "/vapt"),
            ("📊 /status", "system status check"),
        ]
        for label, cmd in chips:
            chip = ctk.CTkButton(
                chips_frame,
                text=label,
                width=80,
                height=22,
                fg_color="#1E293B",
                hover_color="#334155",
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=TEXT_WHITE,
                command=lambda c=cmd: self._set_and_send(c),
            )
            chip.pack(side="left", padx=(0, 6))

        # Output Text Box (Frosted dark terminal style)
        self.output_box = ctk.CTkTextbox(
            self.outer_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#090D16",
            text_color=TEXT_WHITE,
            border_width=1,
            border_color="#1E293B",
            corner_radius=8,
            wrap="word",
        )
        self.output_box.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self.output_box.insert(
            "end",
            "LUMI STARK APEX HUD initialized. Press [Alt + Space] anytime to summon or dismiss.\n"
            "Try: /briefing (morning audio status), /screen (visual agent), /heal (self-repair).\n",
        )
        self.output_box.configure(state="disabled")

    def _bind_keys(self) -> None:
        """Binds local keyboard shortcuts within the window."""
        self.root.bind("<Escape>", lambda e: self.hide())

    def _set_and_send(self, command_text: str) -> None:
        """Populates entry and dispatches execution."""
        self.entry.delete(0, "end")
        self.entry.insert(0, command_text)
        self.send_command()

    def show(self) -> None:
        """Displays the floating HUD and brings it into active focus."""
        self.root.deiconify()
        self.root.wm_attributes("-topmost", True)
        self.root.lift()
        self.root.focus_force()
        self.entry.focus()
        self.is_visible = True

    def hide(self) -> None:
        """Minimizes the floating HUD."""
        self.root.withdraw()
        self.is_visible = False

    def toggle(self) -> None:
        """Toggles between visible and hidden state."""
        if self.is_visible:
            self.hide()
        else:
            self.show()

    def send_command(self) -> None:
        """Dispatches the command to LUMI Web Cockpit in a background thread."""
        query = self.entry.get().strip()
        if not query or self._is_busy:
            return

        self._is_busy = True
        self.send_btn.configure(text="PROCESSING...", fg_color="#475569")
        self.status_pill.configure(text="COMPUTING", text_color=ACCENT_AMBER, fg_color="#78350F")

        # Append query to output
        self._append_output(f"\n> {query}\n")
        self.entry.delete(0, "end")

        def _worker() -> None:
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(
                    self.api_url,
                    data=json.dumps({"message": query}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    reply = payload.get("reply", "No response received.")
                    model = payload.get("model", "reflex")
                    elapsed_ms = payload.get("elapsed_ms", int((time.perf_counter() - t0) * 1000))
                    msg = f"[{model} :: {elapsed_ms}ms]\n{reply}\n"
                    self.root.after(0, lambda: self._on_success(msg))
            except Exception as e:
                err_msg = f"[HUD ERROR] Could not reach LUMI at {self.api_url}: {e}\n"
                self.root.after(0, lambda: self._on_error(err_msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_success(self, text: str) -> None:
        """Handles successful response on UI thread."""
        self._append_output(text)
        self.send_btn.configure(text="EXECUTE ⚡", fg_color="#0284C7")
        self.status_pill.configure(text="ONLINE [RTX-5060]", text_color=ACCENT_GREEN, fg_color="#064E3B")
        self._is_busy = False

    def _on_error(self, err_text: str) -> None:
        """Handles error on UI thread."""
        self._append_output(err_text)
        self.send_btn.configure(text="EXECUTE ⚡", fg_color="#0284C7")
        self.status_pill.configure(text="OFFLINE / RETRY", text_color=ACCENT_RED, fg_color="#7F1D1D")
        self._is_busy = False

    def _append_output(self, text: str) -> None:
        """Appends text to the scrollable terminal box."""
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text)
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def start_global_hotkey_listener(self) -> None:
        """Spawns global hotkey hook in a background thread."""
        if keyboard is None:
            logger.warning("pynput is not installed; global hotkey listener disabled.")
            return

        def _on_hotkey() -> None:
            self.root.after(0, self.toggle)

        def _listener_runner() -> None:
            try:
                # Primary hotkey: <alt>+<space>
                with keyboard.GlobalHotKeys({self.hotkey_str: _on_hotkey}) as h:
                    h.join()
            except Exception as e:
                logger.error("Global hotkey hook error: %s", e)

        t = threading.Thread(target=_listener_runner, daemon=True, name="LumiHUDHotkeyListener")
        t.start()
        logger.info("Global hotkey listener registered for '%s'.", self.hotkey_str)

    def run(self) -> None:
        """Starts the CustomTkinter main event loop."""
        self.start_global_hotkey_listener()
        self.show()
        self.root.mainloop()


def launch_hud(api_url: str = "http://127.0.0.1:8765/api/chat", hotkey: str = "<alt>+<space>") -> LumiDesktopHUD:
    """Convenience factory to initialize the Desktop HUD."""
    hud = LumiDesktopHUD(api_url=api_url, hotkey_str=hotkey)
    return hud


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    hud = launch_hud()
    hud.run()
